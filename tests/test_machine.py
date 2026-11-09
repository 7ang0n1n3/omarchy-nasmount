import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
h = load('helper', ROOT / 'machine/omarchy-nas-helper.py')
setup = load('setup', ROOT / 'machine/setup.py')

class MachineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / 'config.json'; self.creds = self.root / 'credentials'
        self.addCleanup(patch.stopall)
        patch.object(h, 'CONFIG', self.config).start(); patch.object(h, 'CREDS', self.creds).start()
        patch.object(h, 'mounted', return_value=False).start()
        self.data = dict(id='media', name='メディア <img src=x>', type='cifs', server='nas.test', share='media', mountpoint='/mnt/nas/media', owner=pwd.getpwuid(os.getuid()).pw_name, networks=['Home', 'VPN'], options=['vers=3.0'], username='fictional', password='fixture-secret')
    def save(self, data=None):
        with contextlib.redirect_stdout(io.StringIO()): h.save_entry(json.dumps(data or self.data).encode())
    def test_unicode_and_private_storage(self):
        self.save()
        config = json.loads(self.config.read_text())
        self.assertNotIn('fixture-secret', self.config.read_text())
        self.assertEqual(config['mounts'][0]['name'], self.data['name'])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.creds.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.creds/'media.credentials').stat().st_mode & 0o777, 0o600)
    def test_edit_preserves_credentials_and_options(self):
        self.save(); before=(self.creds/'media.credentials').read_bytes()
        data=dict(self.data, old_id='media', username='', password=''); data.pop('options')
        self.save(data)
        self.assertEqual((self.creds/'media.credentials').read_bytes(), before)
        self.assertEqual(h.load_config()['mounts'][0]['options'], ['vers=3.0'])
        self.assertEqual(h.load_config()['mounts'][0]['networks'], ['Home','VPN'])
    def test_rename_then_delete(self):
        self.save(); self.save(dict(self.data, old_id='media', id='renamed', username='', password=''))
        self.assertFalse((self.creds/'media.credentials').exists())
        self.assertTrue((self.creds/'renamed.credentials').exists())
        with contextlib.redirect_stdout(io.StringIO()): h.delete_entry('renamed')
        self.assertEqual(h.load_config()['mounts'], [])
        self.assertFalse((self.creds/'renamed.credentials').exists())
    def test_reject_traversal_mount_paths_and_options(self):
        for data in [dict(self.data, id='../escape'), dict(self.data, old_id='../escape'), dict(self.data, mountpoint='/etc'), dict(self.data, options=['credentials=/etc/shadow']), dict(self.data, password='secret\nusername=root')]:
            with self.subTest(data=list(data.keys())):
                with self.assertRaises(h.NasError): self.save(data)
        self.assertFalse(self.config.exists())
    def test_malformed_and_overflow(self):
        for payload in [b'no json', b'[]', b'x'*16385, b'"secret"']:
            with self.assertRaises(h.NasError): h.decode_payload(payload)
    def test_no_mutation_on_invalid_rename(self):
        self.save(); before=self.config.read_bytes()
        with self.assertRaises(h.NasError): self.save(dict(self.data, old_id='media', id='new', username='', password='secret'))
        self.assertEqual(self.config.read_bytes(), before)
        self.assertTrue((self.creds/'media.credentials').exists())
    def test_cannot_change_mounted_share(self):
        self.save()
        with patch.object(h, 'mounted', return_value=True), self.assertRaises(h.NasError):
            self.save(dict(self.data, old_id='media', share='other'))
    def test_status_does_not_disclose_credentials(self):
        self.save()
        with patch.object(h, 'active_connections', return_value=[]), patch.object(h, 'known_connections', return_value=['Home']):
            result=h.status(h.load_config())
        self.assertEqual(result['protocol_version'],1)
        self.assertTrue(result['mounts'][0]['has_credentials'])
        self.assertNotIn('fixture-secret', json.dumps(result))
    def test_reconcile_continues_after_failure(self):
        first=dict(self.data); second=dict(self.data,id='second')
        with patch.object(h,'active_connections',return_value=['Home']), patch.object(h,'do_mount',side_effect=[h.NasError('failed'),None]) as mount:
            with self.assertRaises(h.NasError): h.reconcile({'mounts':[first,second]})
            self.assertEqual(mount.call_count,2)
    def test_offline_auto_unmount(self):
        with patch.object(h,'active_connections',return_value=[]), patch.object(h,'do_unmount') as unmount:
            h.reconcile({'mounts':[self.data,dict(self.data,id='stay',auto_unmount=False)]})
            unmount.assert_called_once()
    def test_lock_and_permission_upgrade(self):
        self.save(); self.config.chmod(0o644)
        with h.machine_lock():
            with self.assertRaises(h.NasError):
                with h.machine_lock(): pass
        self.assertEqual(self.config.stat().st_mode & 0o777,0o600)
    def test_command_timeout(self):
        with patch.object(h.time, 'monotonic', side_effect=[0, 21]), self.assertRaises(h.NasError):
            h.run_command(['/usr/bin/python3', '-c', 'import time; time.sleep(30)'])
    def test_legacy_save_rejected_without_echo(self):
        with patch.object(h.signal,'signal'), patch.object(h.signal,'alarm'), patch.object(h.sys,'argv',['nas','save','fictional-secret']):
            with self.assertRaises(h.NasError) as error: h.main()
        self.assertNotIn('fictional-secret',str(error.exception))
    def test_invalid_cli_does_not_echo_payload(self):
        with patch.object(h.signal,'signal'), patch.object(h.signal,'alarm'), patch.object(h.sys,'argv',['nas','fictional-secret']):
            with self.assertRaises(h.NasError) as error: h.main()
        self.assertNotIn('fictional-secret',str(error.exception))
    def test_process_output_limit(self):
        with self.assertRaises(h.NasError): h.run_command(['/usr/bin/python3','-c','print("x"*70000)'])
    def test_mount_does_not_modify_stored_options(self):
        self.save(); entry=h.load_config()['mounts'][0]; before=list(entry['options'])
        with patch.object(h,'ensure_mountpoint',return_value='/mnt/nas/media'), patch.object(h,'run_command',return_value=type('Result',(),{'returncode':0})()) as command:
            h.do_mount(entry)
        self.assertEqual(entry['options'],before)
        self.assertNotIn('fixture-secret',repr(command.call_args))
    def test_nfs_does_not_require_credentials(self):
        self.save(dict(self.data,type='nfs',username='',password=''))
        self.assertFalse(self.creds.exists())
        self.assertTrue(h.public_mount(h.load_config()['mounts'][0])['has_credentials'])
    def test_setup_upgrade_and_removal(self):
        stage=self.root/'stage'; data=stage/'etc/omarchy-nas'; data.mkdir(parents=True)
        (data/'config.json').write_text('{"mounts":[]}')
        (data/'credentials').mkdir(); secret=data/'credentials/existing.credentials'; secret.write_text('fictional')
        for _ in range(2): setup.install(stage,'fixture', ROOT/'machine')
        self.assertEqual((data/'config.json').read_text(),'{"mounts":[]}')
        self.assertEqual(secret.read_text(),'fictional')
        self.assertEqual(secret.stat().st_mode & 0o777,0o600)
        setup.remove(stage); setup.remove(stage)
        self.assertTrue(secret.exists()); self.assertTrue((data/'config.json').exists())
        self.assertFalse((stage/'etc/NetworkManager/dispatcher.d/90-omarchy-nas').exists())
    def test_unmanaged_sudoers_is_preserved(self):
        stage=self.root/'stage'; rule=stage/setup.RULE; rule.parent.mkdir(parents=True); rule.write_text('unmanaged')
        with self.assertRaises(RuntimeError): setup.install(stage,'fixture',ROOT/'machine')
        with self.assertRaises(RuntimeError): setup.remove(stage)
        self.assertEqual(rule.read_text(),'unmanaged')

if __name__ == '__main__': unittest.main()
