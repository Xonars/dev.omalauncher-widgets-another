import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class GitCountsTests(unittest.TestCase):
 def test_tracks_modified_and_untracked_files_with_spaces(self):
  with tempfile.TemporaryDirectory() as tmp:
   repo=Path(tmp)
   def git(*args):return subprocess.run(['git','-C',tmp,*args],check=True,capture_output=True)
   git('init'); (repo/'tracked file.txt').write_text('before\n')
   git('add','.'); git('-c','user.name=Store Test','-c','user.email=store-test@example.invalid','commit','-m','fixture')
   (repo/'tracked file.txt').write_text('after\nextra\n');(repo/'new file.txt').write_text('new\n')
   output=subprocess.check_output([sys.executable,str(ROOT/'tools/store-omagit-counts.py'),tmp],text=True)
   lines=output.splitlines()
   self.assertEqual(lines[0],tmp)
   self.assertIn('2\t1\ttracked file.txt',lines)
   self.assertTrue(any(line.startswith('1\t0\t') and 'new file.txt' in line for line in lines))

if __name__=='__main__':unittest.main()
