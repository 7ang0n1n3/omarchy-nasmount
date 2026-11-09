#!/usr/bin/env python3
"""Explicit machine install/remove; --root stages files without touching the host."""
import argparse
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tempfile

FILES = {
    'omarchy-nasctl': 'usr/local/bin/omarchy-nasctl',
    'omarchy-nas-helper.py': 'usr/local/lib/omarchy-nas/omarchy-nas-helper.py',
    '90-omarchy-nas': 'etc/NetworkManager/dispatcher.d/90-omarchy-nas',
}
RULE = 'etc/sudoers.d/omarchy-nas'
MARKER = '# Managed by omarchy-nas setup\n'


def destination(root, name):
    path = root / name
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise RuntimeError('Refusing a symlink destination')
    return path


def install_file(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream: stream.write(content)
        os.chmod(tmp, mode)
        if os.geteuid() == 0: os.chown(tmp, 0, 0)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def install(root, username, source):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', username): raise RuntimeError('Invalid local username')
    if root == Path('/'):
        pwd.getpwnam(username)
        for command in ('python3', 'sudo', 'visudo', 'nmcli', 'findmnt', 'mount', 'umount', 'mount.cifs', 'mount.nfs'):
            if not shutil.which(command): raise RuntimeError('Missing prerequisite: ' + command)
    rule = (MARKER + username + ' ALL=(root) NOPASSWD: /usr/local/lib/omarchy-nas/omarchy-nas-helper.py\n').encode()
    rule_path = destination(root, RULE)
    if rule_path.exists() and not rule_path.read_text().startswith(MARKER):
        raise RuntimeError('Existing sudoers rule needs administrator review; no files changed')
    if root == Path('/'):
        with tempfile.NamedTemporaryFile() as candidate:
            candidate.write(rule); candidate.flush()
            subprocess.run(['visudo', '-cf', candidate.name], check=True)
    for name, target in FILES.items():
        path = destination(root, target)
        if root == Path('/'):
            for parent in path.parents:
                if parent.exists():
                    st = parent.stat()
                    if st.st_uid != 0 or st.st_mode & 0o022:
                        raise RuntimeError('Executable ancestors must be root-owned and not writable by other users')
    config_dir = destination(root, 'etc/omarchy-nas')
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(config_dir, 0o700)
    if root == Path('/'): os.chown(config_dir, 0, 0)
    for name in ('config.json',):
        path = destination(root, 'etc/omarchy-nas/' + name)
        if path.exists():
            os.chmod(path, 0o600)
            if root == Path('/'): os.chown(path, 0, 0)
    creds = destination(root, 'etc/omarchy-nas/credentials')
    if creds.exists():
        os.chmod(creds, 0o700)
        if root == Path('/'): os.chown(creds, 0, 0)
        for path in creds.glob('*.credentials'):
            if path.is_symlink(): raise RuntimeError('Credential store contains a symlink')
            os.chmod(path, 0o600)
            if root == Path('/'): os.chown(path, 0, 0)
    for name, target in FILES.items(): install_file(destination(root, target), (source / name).read_bytes(), 0o755)
    install_file(rule_path, rule, 0o440)


def remove(root):
    rule = destination(root, RULE)
    if rule.exists() and not rule.read_text().startswith(MARKER):
        raise RuntimeError('Refusing to remove an unmanaged sudoers rule')
    # Disable automatic reconciliation first. Keep all data and existing mounts.
    for target in (FILES['90-omarchy-nas'], RULE, FILES['omarchy-nasctl'], FILES['omarchy-nas-helper.py']):
        destination(root, target).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'remove'])
    parser.add_argument('--user')
    parser.add_argument('--root', type=Path, default=Path('/'))
    args = parser.parse_args()
    root = args.root.absolute()
    if root == Path('/') and os.geteuid() != 0: parser.error('Machine setup requires root')
    if args.action == 'install':
        if not args.user: parser.error('--user is required for install')
        install(root, args.user, Path(__file__).parent)
    else: remove(root)
    print('Machine ' + args.action + ' complete; NAS data and existing mounts retained.')


if __name__ == '__main__': main()
