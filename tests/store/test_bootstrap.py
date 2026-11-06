import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('bootstrap',ROOT/'tools/store-bootstrap.py')
bootstrap=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)

class BootstrapTests(unittest.TestCase):
 def payload(self,name='widgets/helper/main.py'):
  buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,'w') as z:z.writestr(name,'print("test")\n')
  return buffer.getvalue()
 def run_install(self,payload,digest=None,entry='test-entry'):
  response=io.BytesIO(payload)
  with patch.object(bootstrap.urllib.request,'urlopen',return_value=response) as request:
   bootstrap.install('https://example.test/resources.zip',digest or hashlib.sha256(payload).hexdigest(),entry)
  return request
 def test_fresh_install_then_offline(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(Path,'home',return_value=Path(tmp)):
   payload=self.payload(); self.run_install(payload)
   root=Path(tmp)/'.local/share/omalauncher-store/test-entry'
   self.assertEqual((root/'widgets/helper/main.py').read_text(),'print("test")\n')
   self.assertFalse(self.run_install(payload).called)
 def test_wrong_digest_writes_no_payload(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(Path,'home',return_value=Path(tmp)):
   with self.assertRaisesRegex(ValueError,'SHA-256'):self.run_install(self.payload(),'0'*64)
   self.assertFalse(list(Path(tmp).rglob('main.py')))
 def test_traversal_rejected(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(Path,'home',return_value=Path(tmp)):
   with self.assertRaisesRegex(ValueError,'Invalid store resource path'):self.run_install(self.payload('widgets/../../escape'))
   self.assertFalse((Path(tmp)/'escape').exists())
 def test_symlink_destination_rejected(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(Path,'home',return_value=Path(tmp)):
   root=Path(tmp)/'.local/share/omalauncher-store/test-entry';root.mkdir(parents=True)
   outside=Path(tmp)/'outside';outside.mkdir();(root/'widgets').symlink_to(outside,target_is_directory=True)
   with self.assertRaisesRegex(ValueError,'Symlink'):self.run_install(self.payload())
   self.assertFalse(list(outside.rglob('main.py')))
 def test_all_published_packages_install_in_isolation(self):
  for archive in sorted((ROOT/'resources').glob('*.zip')):
   with self.subTest(archive=archive.name),tempfile.TemporaryDirectory() as tmp,patch.object(Path,'home',return_value=Path(tmp)):
    self.run_install(archive.read_bytes())
    root=Path(tmp)/'.local/share/omalauncher-store/test-entry'
    with zipfile.ZipFile(archive) as z:
     for name in z.namelist():
      self.assertEqual((root/name).read_bytes(),z.read(name))
 def test_invalid_entry_rejected(self):
  with self.assertRaisesRegex(ValueError,'Invalid store entry'): self.run_install(self.payload(),entry='../escape')

if __name__=='__main__':unittest.main()
