#!/usr/bin/env python3
import argparse, json, os, pwd, subprocess, sys, tempfile, re, fcntl, contextlib, signal, time, selectors
from pathlib import Path

PROTOCOL = 1
MAX_REQUEST = 16384

CONFIG = Path('/etc/omarchy-nas/config.json')
CREDS = Path('/etc/omarchy-nas/credentials')


class NasError(Exception):
    pass


def die(msg, code=1):
    raise NasError(msg)


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', value) is not None and '..' not in value


def load_config(create=True):
    if not CONFIG.exists():
        if create:
            return {'mounts': []}
        die(f'Missing {CONFIG}')
    try:
        data = json.loads(CONFIG.read_text())
    except Exception as e:
        die('Cannot read NAS configuration')
    mounts = data.get('mounts', [])
    if not isinstance(mounts, list):
        die('Invalid configuration: mounts must be an array')
    if len(mounts) > 128: die('Too many shares')
    for m in mounts:
        if not isinstance(m, dict) or not valid_id(m.get('id')): die('Invalid stored share')
    return {'mounts': mounts}


def atomic_write_json(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
            f.write('\n')
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def run_command(args, **kwargs):
    # Drain both pipes incrementally, bounding retained output and total output.
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    except OSError:
        die('Required machine dependency is unavailable')
    result = {"out": bytearray(), "err": bytearray()}
    deadline = time.monotonic() + 20
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ, 'out')
            selector.register(proc.stderr, selectors.EVENT_READ, 'err')
            while selector.get_map():
                if time.monotonic() >= deadline: die('NAS command timed out')
                for key, _ in selector.select(0.1):
                    chunk = os.read(key.fileobj.fileno(), 4096)
                    if not chunk: selector.unregister(key.fileobj); continue
                    result[key.data].extend(chunk)
                    if len(result[key.data]) > 65536: die('NAS command output exceeded its limit')
            code = proc.wait(timeout=max(0.1, deadline - time.monotonic()))
    finally:
        if proc.poll() is None: proc.kill()
        proc.wait()
        proc.stdout.close(); proc.stderr.close()
    return subprocess.CompletedProcess(args, code, result['out'].decode('utf-8', 'replace'), result['err'].decode('utf-8', 'replace'))


def active_connections():
    p = run_command(['nmcli','-t','-f','NAME','connection','show','--active'], text=True, capture_output=True)
    if p.returncode != 0: die('NetworkManager unavailable')
    return [x.replace('\\:', ':').strip() for x in p.stdout.splitlines() if x.strip()]


def known_connections():
    p = run_command(['nmcli','-t','-f','NAME','connection','show'], text=True, capture_output=True)
    if p.returncode != 0: die('NetworkManager unavailable')
    out = []
    for x in p.stdout.splitlines():
        name = x.replace('\\:', ':').strip()
        if name and name not in out: out.append(name)
    return out


def mounted(path):
    if not path: return False
    return run_command(['findmnt','-rn','--mountpoint',path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def lookup(data, mid):
    for m in data.get('mounts', []):
        if str(m.get('id')) == mid: return m
    die(f'Unknown mount id: {mid}')


def ensure_mountpoint(m):
    path = checked_mountpoint(m['mountpoint'])
    path.mkdir(parents=True, exist_ok=True)
    owner = m.get('owner')
    if owner:
        pw = pwd.getpwnam(owner)
        os.chown(path, pw.pw_uid, pw.pw_gid)
    return str(path)


def do_mount(m):
    path = str(checked_mountpoint(m['mountpoint']))
    if mounted(path): return
    path = ensure_mountpoint(m)
    proto = str(m.get('type','cifs')).lower()
    server = str(m.get('server','')).strip()
    share = str(m.get('share','')).strip().lstrip('/')
    if not server or not share: die(f"{m['id']}: server/share missing")
    opts = validate_options(m.get('options', []))
    if not all(isinstance(x, str) and ',' not in x for x in opts):
        die(f"{m['id']}: each option must be a string without commas")

    if proto in ('cifs','smb'):
        source = f'//{server}/{share}'
        cred = CREDS / f"{m['id']}.credentials"
        if not cred.exists(): die(f'Credentials have not been saved for {m["name"]}')
        opts.insert(0, f'credentials={cred}')
        opts += ['nosuid', 'nodev', 'noexec']
        owner = m.get('owner')
        if owner:
            pw = pwd.getpwnam(owner)
            opts += [f'uid={pw.pw_uid}', f'gid={pw.pw_gid}']
        if not any(o.startswith('vers=') for o in opts): opts.append('vers=3.0')
        cmd = ['mount','-t','cifs',source,path,'-o',','.join(opts)]
    elif proto == 'nfs':
        source = f'{server}:/{share}'
        opts += ['nosuid', 'nodev', 'noexec']
        cmd = ['mount','-t','nfs',source,path]
        if opts: cmd += ['-o', ','.join(opts)]
    else:
        die(f"{m['id']}: unsupported type {proto}")
    p = run_command(cmd, text=True, capture_output=True)
    if p.returncode != 0:
        die('Mount failed; check network, credentials and server permissions')


def do_unmount(m):
    path = str(checked_mountpoint(m.get('mountpoint','')))
    if mounted(path):
        p = run_command(['umount', path], text=True, capture_output=True)
        if p.returncode != 0: die('Unmount failed; the share may be busy')


def network_matches(m, active):
    nets = m.get('networks', [])
    if isinstance(nets, str): nets = [nets]
    return bool(set(str(x) for x in nets) & set(active))


def reconcile(data):
    active = active_connections()
    errors = []
    for m in data.get('mounts', []):
        try:
            if network_matches(m, active): do_mount(m)
            elif m.get('auto_unmount', True): do_unmount(m)
        except NasError as e:
            errors.append(f"{m.get('name',m.get('id'))}: {e}")
    if errors: die('; '.join(errors))


def public_mount(m):
    out = {k: m[k] for k in ('id','name','type','server','share','mountpoint','owner','networks','auto_unmount','options') if k in m}
    out['has_credentials'] = (CREDS / f"{m['id']}.credentials").exists() if m.get('type') in ('cifs','smb') else True
    return out


def status(data):
    active = active_connections()
    mounts = []
    for m in data.get('mounts', []):
        item = public_mount(m)
        item.update({'network_match': network_matches(m, active), 'mounted': mounted(str(m.get('mountpoint','')))})
        mounts.append(item)
    return {
        'protocol_version': PROTOCOL,
        'network': ', '.join(active) if active else 'Disconnected',
        'active_connections': active,
        'known_connections': known_connections(),
        'mounts': mounts
    }


def decode_payload(payload):
    if len(payload) > MAX_REQUEST: die('Settings payload is too large')
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeError):
        die('Invalid settings payload')
    if not isinstance(data, dict): die('Settings must be an object')
    return data


def checked_mountpoint(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or path == Path('/mnt/nas'):
        die('Mount point must be below /mnt/nas')
    if not path.is_relative_to('/mnt/nas') or path.resolve() != path:
        die('Mount point must be below /mnt/nas without symlinks')
    for parent in path.parents:
        if parent.exists():
            st = parent.stat()
            if st.st_uid != 0 or st.st_mode & 0o022: die('Mount point ancestors must be root-owned and not writable by other users')
    return path


def validate_options(options):
    if not isinstance(options, list) or len(options) > 32: die('Invalid mount options')
    allowed = r'(ro|rw|soft|hard|intr|nointr|nounix|noperm|noserverino|serverino|nosuid|nodev|noexec|vers=[0-9.]+|sec=(ntlmssp|ntlmsspi|krb5|krb5i|sys)|(rsize|wsize|timeo|retrans|actimeo)=[0-9]+|file_mode=0?[0-7]{3}|dir_mode=0?[0-7]{3})'
    if any(not isinstance(x, str) or not re.fullmatch(allowed, x) for x in options):
        die('Unsupported mount option; review machine configuration')
    return list(options)


def normalize_entry(raw, existing=None):
    mid = str(raw.get('id','')).strip()
    if not valid_id(mid): die('NAS id must use letters, numbers, dot, underscore or dash')
    proto = str(raw.get('type','cifs')).lower().strip()
    if proto == 'smb': proto = 'cifs'
    if proto not in ('cifs','nfs'): die('Protocol must be SMB or NFS')
    name = str(raw.get('name','')).strip() or mid
    server = str(raw.get('server','')).strip()
    share = str(raw.get('share','')).strip().lstrip('/')
    mountpoint = str(raw.get('mountpoint','')).strip()
    owner = str(raw.get('owner','')).strip()
    networks = raw.get('networks', [])
    if isinstance(networks, str): networks = [networks]
    if not isinstance(networks, list) or len(networks) > 32: die('Invalid network associations')
    networks = [str(x).strip() for x in networks if str(x).strip()]
    if len(name) > 256 or any(len(x) > 256 for x in networks): die('Name or network association is too long')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:%_-]{0,252}', server): die('Invalid server/IP')
    if not share or len(share) > 1024 or any(c in share for c in '\r\n\x00'): die('Invalid share/export')
    checked_mountpoint(mountpoint)
    if not owner: die('Local owner is required')
    try: pwd.getpwnam(owner)
    except KeyError: die(f'Local user does not exist: {owner}')
    if not networks: die('At least one NetworkManager connection is required')
    options = raw.get('options', existing.get('options', []) if existing else [])
    if not isinstance(options, list): options = []
    options = validate_options(options)
    if not all(',' not in x and '\n' not in x for x in options): die('Invalid mount option')
    return {
        'id': mid, 'name': name, 'type': proto, 'server': server, 'share': share,
        'mountpoint': mountpoint, 'owner': owner, 'networks': networks,
        'auto_unmount': bool(raw.get('auto_unmount', True)), 'options': options
    }


def save_entry(payload):
    raw = decode_payload(payload)
    data = load_config()
    old_id = str(raw.get('old_id','')).strip()
    if old_id and not valid_id(old_id): die('Invalid previous share ID')
    existing = None
    if old_id:
        existing = next((m for m in data['mounts'] if str(m.get('id')) == old_id), None)
    if old_id and existing is None: die('Original share no longer exists')
    for key in ('username','password','domain'):
        value = raw.get(key, '')
        if not isinstance(value, str) or len(value) > 4096 or any(c in value for c in '\r\n\x00'): die('Invalid credential field')
    entry = normalize_entry(raw, existing)
    if existing and any(existing.get(k) != entry.get(k) for k in ('id','type','server','share','mountpoint','owner','options')) and mounted(existing['mountpoint']):
        die('Unmount this share before changing its mount configuration')
    if len(data['mounts']) >= 128 and not existing: die('Too many shares')
    if any(m.get('mountpoint') == entry['mountpoint'] and m.get('id') != old_id for m in data['mounts']): die('Mount point is already configured')
    if entry['type'] == 'cifs' and raw.get('password') and not raw.get('username'): die('SMB username is required when saving credentials')
    if any(str(m.get('id')) == entry['id'] and str(m.get('id')) != old_id for m in data['mounts']):
        die(f'Another NAS already uses id {entry["id"]}')

    if old_id and old_id != entry['id']:
        old_cred = CREDS / f'{old_id}.credentials'
        new_cred = CREDS / f'{entry["id"]}.credentials'
        if new_cred.exists(): die('Target credential file already exists')
        if old_cred.exists():
            # Copy first; keep the original until the config commit succeeds.
            fd, tmp = tempfile.mkstemp(dir=str(CREDS))
            with os.fdopen(fd, 'wb') as stream: stream.write(old_cred.read_bytes())
            os.chmod(tmp, 0o600); os.replace(tmp, new_cred)

    replaced = False
    new_mounts = []
    for m in data['mounts']:
        if old_id and str(m.get('id')) == old_id:
            new_mounts.append(entry); replaced = True
        elif not old_id and str(m.get('id')) == entry['id']:
            new_mounts.append(entry); replaced = True
        else:
            new_mounts.append(m)
    if not replaced: new_mounts.append(entry)
    data['mounts'] = new_mounts

    username = str(raw.get('username','')).replace('\n','').replace('\r','')
    password = str(raw.get('password','')).replace('\n','').replace('\r','')
    domain = str(raw.get('domain','')).replace('\n','').replace('\r','')
    if entry['type'] == 'cifs' and (username or password):
        if not username: die('SMB username is required when saving credentials')
        CREDS.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(CREDS, 0o700)
        cp = CREDS / f'{entry["id"]}.credentials'
        text = f'username={username}\npassword={password}\n'
        if domain: text += f'domain={domain}\n'
        fd, tmp = tempfile.mkstemp(prefix=cp.name + '.', dir=str(CREDS))
        try:
            with os.fdopen(fd, 'w') as f: f.write(text)
            os.chmod(tmp, 0o600)
            os.replace(tmp, cp)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    atomic_write_json(CONFIG, data, mode=0o600)
    if old_id and old_id != entry['id']:
        (CREDS / f'{old_id}.credentials').unlink(missing_ok=True)
    print(json.dumps({'ok': True, 'id': entry['id']}))


def delete_entry(mid):
    data = load_config()
    m = lookup(data, mid)
    do_unmount(m)
    data['mounts'] = [x for x in data['mounts'] if str(x.get('id')) != mid]
    atomic_write_json(CONFIG, data, mode=0o600)
    cp = CREDS / f'{mid}.credentials'
    if cp.exists(): cp.unlink()
    print(json.dumps({'ok': True}))


@contextlib.contextmanager
def machine_lock():
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(CONFIG.parent, 0o700)
    if CONFIG.exists(): os.chmod(CONFIG, 0o600)
    if CREDS.exists():
        os.chmod(CREDS, 0o700)
        for credential in CREDS.glob('*.credentials'):
            if credential.is_symlink(): die('Invalid credential store')
            os.chmod(credential, 0o600)
    with (CONFIG.parent / '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            die('Another NAS operation is running; retry shortly')
        yield


def deadline_expired(signum, frame):
    raise TimeoutError('NAS operation timed out')


def main():
    signal.signal(signal.SIGALRM, deadline_expired)
    signal.alarm(40)
    class SafeParser(argparse.ArgumentParser):
        def error(self, message): die("Invalid NAS command; use save --stdin for settings")
    ap = SafeParser()
    ap.add_argument('action', choices=['status','mount','unmount','mount-all','unmount-all','reconcile','save','delete'])
    ap.add_argument('value', nargs='?')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--stdin', action='store_true')
    args = ap.parse_args()
    with machine_lock():
        if args.action == 'save':
            if not args.stdin or args.value: die('Use save --stdin; command-line credentials are unsupported')
            return save_entry(sys.stdin.buffer.read(MAX_REQUEST + 1))
        if args.action == 'delete': return delete_entry(args.value or '')
        data = load_config()
        if args.action == 'status': print(json.dumps(status(data)))
        elif args.action == 'mount': do_mount(lookup(data, args.value or ''))
        elif args.action == 'unmount': do_unmount(lookup(data, args.value or ''))
        elif args.action == 'reconcile': reconcile(data)
        else:
            errors = []
            for m in data['mounts'] if args.action == 'mount-all' else reversed(data['mounts']):
                try:
                    (do_mount if args.action == 'mount-all' else do_unmount)(m)
                except NasError as e: errors.append(f"{m['id']}: {e}")
            if errors: die('; '.join(errors))


if __name__ == '__main__':
    try:
        main()
    except (NasError, OSError, ValueError, KeyError, TypeError):
        # Never expose raw payloads, subprocess output or credentials.
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, NasError) else 'NAS operation failed; check machine setup', file=sys.stderr)
        sys.exit(1)
