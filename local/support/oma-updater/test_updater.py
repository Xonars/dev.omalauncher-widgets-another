"""Real Git workflow with conflicting local history; Android tools are stubbed."""
import importlib.util, json, subprocess, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('updater',Path(__file__).with_name('updater.py'))
u=importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
class MainBuild(unittest.TestCase):
 def test_upstream_only_and_preserve_previous_artifact_on_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   with patch.multiple(u,**{k:root/k for k in ['BASE','CACHE','REPO','BACKUPS','CONFIG','KEY','OUTPUT']},STATE=root/'CACHE/status.json'):
    for p in (u.BASE,u.CACHE,u.REPO,u.CONFIG):p.mkdir()
    u.KEY.write_text('stub')
    def git(*args):return subprocess.check_output(['git',*args],cwd=u.REPO,text=True,stderr=subprocess.PIPE).strip()
    git('init','-b','main');git('config','user.name','Test');git('config','user.email','test@localhost')
    (u.REPO/'app').mkdir();(u.REPO/'scripts').mkdir()
    (u.REPO/'app/build.gradle.kts').write_text('    ndkVersion = prootNdk\ncmake { path = file("src/main/cpp/CMakeLists.txt") }\nversionName = "1.0"\n')
    (u.REPO/'scripts/fetch-proot.sh').write_text('NDK_VERSION=old\nTC=old\n')
    (u.REPO/'local.properties').write_text('sdk.dir=test\n');(u.BASE/'build-main.sh').write_text('stub')
    (u.REPO/'feature').write_text('upstream');git('add','.');git('commit','-m','upstream');remote=git('rev-parse','HEAD')
    git('remote','add','origin',str(u.REPO));git('checkout','-b','local')
    (u.REPO/'feature').write_text('local PR');git('add','.');git('commit','-m','local PR');local=git('rev-parse','HEAD')
    (u.REPO/'feature').write_text('uncommitted local edits')
    u.save(pending_merge={'old':'conflict'})
    real=u.run
    def run(args,**kw):
     if 'keytool' in str(args[0]) or 'apksigner' in str(args[0]):return u.CERT
     if args[:2]==['bash','scripts/fetch-proot.sh']:return ''
     if args[:2]==['bash','build-local.sh']:
      folder=Path(kw['cwd']);self.assertEqual((folder/'feature').read_text(),'upstream')
      apk=folder/'app/build/outputs/apk/debug/app-debug.apk';apk.parent.mkdir(parents=True)
      with zipfile.ZipFile(apk,'w') as z:
       for name in ('proot','proot-loader','talloc','android-shmem','wlbridge'):z.writestr('lib/arm64-v8a/lib'+name+'.so',b'stub')
      return ''
     return real(args,**kw)
    with patch.object(u,'run',side_effect=run):u.worker('build')
    state=u.read();self.assertEqual(state['phase'],'ready',state)
    self.assertEqual(state['source_commit'],remote);self.assertIsNone(state['pending_merge'])
    self.assertEqual(git('rev-parse','HEAD'),local);self.assertEqual((u.REPO/'feature').read_text(),'uncommitted local edits')
    apk=Path(state['apk']);self.assertTrue(apk.exists())
    meta=json.loads(apk.with_suffix('.apk.json').read_text());self.assertEqual(meta['local_changes'],'');self.assertEqual(meta['build_mode'],'upstream-main')
    with patch.object(u,'run',side_effect=RuntimeError('network failure')):u.worker('build')
    self.assertEqual(u.read()['phase'],'error');self.assertEqual(u.read()['apk'],str(apk));self.assertTrue(apk.exists())
 def test_adaptation_fails_closed(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);(folder/'app').mkdir();p=folder/'app/build.gradle.kts';p.write_text('changed upstream format')
   with self.assertRaisesRegex(RuntimeError,'формат upstream'):u.adapt_build(folder)
   self.assertEqual(p.read_text(),'changed upstream format')
if __name__=='__main__':unittest.main(verbosity=2)
