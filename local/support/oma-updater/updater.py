#!/usr/bin/env python3
"""Local OMA build worker. Builds APKs for installation through the host bridge; source checkout stays unchanged."""
import fcntl, hashlib, json, os, re, shutil, signal, subprocess, sys, time, uuid
from pathlib import Path
BASE=Path('/root/.local/share/oma-updater')
CACHE=Path('/root/.cache/oma-updater'); CACHE.mkdir(parents=True,exist_ok=True)
REPO=Path('/root/omalauncher')
STATE=CACHE/'status.json'
SELF=Path(__file__).resolve()
CERT='42d3ac1683f9eade8ecba1e4bc8137c4e39c8eab199b83803a5e4efb9ec6f1cf'
TOOLS=Path('/root/android-sdk/build-tools/37.0.0')
BACKUPS=Path('/root/OMA-RESTORE')
CONFIG=Path('/root/.config/omalauncher')
KEY=Path('/root/.android/debug.keystore')
OUTPUT=Path('/root/APK')
os.umask(0o077)
def read():
    try: return json.loads(STATE.read_text())
    except (FileNotFoundError,ValueError): return {}
def save(**kw):
    s=read(); s.update(kw); s['updated']=time.time()
    p=STATE.with_suffix('.tmp'); p.write_text(json.dumps(s,ensure_ascii=False)); p.replace(STATE)
def run(args,cwd=None,timeout=180,env=None):
    cwd = REPO if cwd is None else cwd
    with (CACHE/'build.log').open('a+') as log:
        log.write('$ '+' '.join(map(str,args))+'\n'); log.flush()
        offset=log.tell()
        p=subprocess.Popen(list(map(str,args)),cwd=cwd,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        try: p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL); p.wait()
            raise RuntimeError(f'Превышено время ожидания: {args[0]}')
        log.seek(offset); output=log.read()
    if p.returncode: raise RuntimeError(output[-1800:] or f'Код ошибки {p.returncode}')
    return output.strip()

def git_read(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd or REPO, text=True, stderr=subprocess.PIPE).strip()

def changes():
    """Read-only comparison against the last fetched main, including cherry-pick equivalence."""
    try:
        local = git_read('rev-parse', 'HEAD')
        remote = git_read('rev-parse', 'origin/main')
        commits = git_read('log', '--format=%h %s', 'origin/main..HEAD')
        patches = git_read('cherry', 'origin/main', 'HEAD').splitlines()
        return dict(local=local[:7], remote=remote[:7], commits=commits,
                    count=len(commits.splitlines()), patches=sum(row.startswith('+') for row in patches),
                    dirty=bool(git_read('status', '--porcelain')), error='')
    except (OSError, subprocess.CalledProcessError) as exc:
        return dict(error=str(exc), commits='', count=0, patches=0)

def prepare_main(folder, remote):
    """Pin pristine upstream sources; local branches never participate."""
    run(['git','worktree','add','--detach',folder,remote])
    save(worktree=str(folder), build_inputs=dict(worktree=str(folder), remote=remote),
         pending_merge=None, conflict_files=[], generated_files={})

def adapt_build(folder):
    """Phone toolchain only; no launcher feature patches."""
    gradle = folder/'app/build.gradle.kts'
    text = gradle.read_text()
    replacements = {
        '    ndkVersion = prootNdk': '    buildToolsVersion = "37.0.0"\n    ndkVersion = "28.2.13676358"',
        'cmake { path = file("src/main/cpp/CMakeLists.txt") }': 'cmake { path = file("src/main/cpp/CMakeLists.txt"); version = "4.4.4" }',
    }
    for old, new in replacements.items():
        if text.count(old) != 1:
            raise RuntimeError('Изменился формат upstream Gradle: требуется проверить адаптацию инструментов: '+old)
        text = text.replace(old, new)
    gradle.write_text(text)


def stage(number, text):
    save(phase='busy',stage=number,message=text,
         stage_started=read().get('stage_started', int(time.time())) if read().get('stage') == number else int(time.time()))
def worker(action):
    with (CACHE/'launch.lock').open('w') as launch:
        fcntl.flock(launch,fcntl.LOCK_EX)
    with (CACHE/'worker.lock').open('w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        try:
            save(pid=os.getpid(),phase='busy',action=action,stage=1,stage_started=int(time.time()),
                 started_at=read().get('started_at') if read().get('pid') == os.getpid() else int(time.time()),
                 finished_at=None,message='Проверка upstream main',error='')
            run(['git','fetch','--no-tags','origin','main'],timeout=120)
            remote=run(['git','rev-parse','refs/remotes/origin/main'])
            local=remote
            previous=read().get('built_commit')
            source_changed=read().get('build_mode') != 'upstream-main'
            available=remote!=previous or source_changed
            apk_path=read().get('apk')
            apk_exists=bool(apk_path and Path(apk_path).is_file())
            save(local=local[:7],remote=remote[:7],checked=int(time.time()),available=available,apk=apk_path if apk_exists else None)
            if action=='check' or (action in ('update','auto') and not available and apk_exists):
                pending=read().get('pending_merge')
                save(phase='conflict' if pending else 'idle',stage=0,finished_at=int(time.time()),message='Ожидается разрешение конфликта' if pending else ('Есть обновление' if available else ('Последняя версия собрана · APK готов' if apk_exists else 'Новых коммитов нет · APK отсутствует'))); return
            stage(2, 'Резервная копия виджетов и настроек')
            backup=BACKUPS/('auto-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:6])
            backup.mkdir(parents=True,exist_ok=False)
            for source, name in [(CONFIG,'omalauncher')]:
                if Path(source).is_dir(): shutil.copytree(source,backup/name,symlinks=True)
            (backup/'source-commit.txt').write_text(local+'\n')
            hashes={str(p.relative_to(backup)):hashlib.sha256(p.read_bytes()).hexdigest() for p in backup.rglob('*') if p.is_file() and not p.is_symlink()}
            (backup/'sha256.json').write_text(json.dumps(hashes,indent=2))
            save(config_backup=str(backup))
            stage(3, 'Подготовка исходников '+remote[:7])
            key=KEY
            if not key.is_file(): raise RuntimeError('Нет сохранённого ключа подписи')
            cert=run(['/usr/lib/jvm/java-25-openjdk/bin/keytool','-list','-keystore',key,'-storepass','android','-alias','androiddebugkey'])
            if CERT not in cert.lower().replace(':',''): raise RuntimeError('Ключ не совпадает с сохранённым сертификатом')
            folder=BASE/'builds'/f'main-{remote[:12]}-{uuid.uuid4().hex[:12]}'
            folder.parent.mkdir(exist_ok=True)
            prepare_main(folder,remote)
            source_commit=run(['git','rev-parse','HEAD'],cwd=folder)
            adapt_build(folder)
            proot=folder/'scripts/fetch-proot.sh'
            text,n=re.subn(r'^NDK_VERSION=.*$', 'NDK_VERSION=28.2.13676358', proot.read_text(), count=1, flags=re.M)
            if n != 1: raise RuntimeError('Не найден NDK_VERSION')
            text,n=re.subn(r'^TC=.*$', 'TC="$NDK/toolchains/llvm/prebuilt/linux-aarch64/bin"', text, count=1, flags=re.M)
            if n != 1: raise RuntimeError('Не найден путь инструментов NDK')
            proot.write_text(text)
            shutil.copy2(REPO/'local.properties',folder/'local.properties')
            shutil.copy2(BASE/'build-main.sh',folder/'build-local.sh')
            # Rebuild proot and dependencies with the updated project's own pinned inputs.
            save(generated_files={'scripts/fetch-proot.sh':hashlib.sha256(proot.read_bytes()).hexdigest()})
            stage(3, 'Подготовка proot и библиотек')
            env=os.environ.copy(); env['PATH']='/usr/bin/core_perl:'+env.get('PATH','/usr/bin'); env.update(JAVA_HOME='/usr/lib/jvm/java-25-openjdk',ANDROID_HOME='/root/android-sdk')
            run(['bash','scripts/fetch-proot.sh'],cwd=folder,env=env,timeout=1200)
            gradle=folder/'app/build.gradle.kts'; text=gradle.read_text()
            match=re.search(r'versionName\s*=\s*"([^"]+)"',text)
            if not match: raise RuntimeError('Не найден versionName')
            version=match[1]+'-g'+remote[:7]+'-main'
            text=text[:match.start()]+f'versionName = "{version}"'+text[match.end():]
            gradle.write_text(text)
            save(generated_files={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['scripts/fetch-proot.sh','app/build.gradle.kts']})
            stage(4, 'Сборка APK '+version)
            run(['bash','build-local.sh',':app:testDebugUnitTest',':owl:test',':app:lintDebug'],cwd=folder,env=env,timeout=7200)
            apk=folder/'app/build/outputs/apk/debug/app-debug.apk'
            stage(5, 'Проверка полноты APK и подписи')
            import zipfile
            with zipfile.ZipFile(apk) as package:
                for name in ('libproot.so','libproot-loader.so','libtalloc.so','libandroid-shmem.so','libwlbridge.so'):
                    if 'lib/arm64-v8a/'+name not in package.namelist():
                        raise RuntimeError('В APK отсутствует '+name)
            cert=run([TOOLS/'apksigner','verify','--print-certs',apk])
            if CERT not in cert.lower(): raise RuntimeError('Подпись APK не совпадает с нашим ключом')
            out=OUTPUT/f'omalauncher-{version}-our-key.apk'
            out.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(apk,out.with_suffix('.tmp')); out.with_suffix('.tmp').replace(out)
            with out.open('rb') as apk_file:
                digest=hashlib.file_digest(apk_file,'sha256').hexdigest()
            out.with_suffix('.apk.sha256').write_text(f'{digest}  {out.name}\n')
            out.with_suffix('.apk.json').write_text(json.dumps(dict(commit=remote,local_commit=local,source_commit=source_commit,version=version,certificate=CERT,sha256=digest,worktree=str(folder),build_mode='upstream-main',local_changes='',build_adaptations=['NDK 28.2.13676358 arm64 host','Build tools 37.0.0','CMake 4.4.4','version suffix'],source_diff=run(['git','diff','--','app/build.gradle.kts','scripts/fetch-proot.sh'],cwd=folder)),indent=2))
            save(phase='ready',stage=6,finished_at=int(time.time()),message='APK готов · откройте APK Share',build_mode='upstream-main',built_commit=remote,built_local=local,source_commit=source_commit,built_version=version,apk=str(out),available=False,error='')
        except Exception as e: save(finished_at=int(time.time()),phase='conflict' if read().get('pending_merge') else 'error',message='Конфликт с main · сборка остановлена' if read().get('pending_merge') else 'Ошибка обновления',error=str(e)[-2200:])
        finally: save(pid=0)
def start(action):
    with (CACHE/'launch.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        s=read(); pid=s.get('pid',0)
        if pid:
            try: os.kill(pid,0); return
            except ProcessLookupError: pass
        log=(CACHE/'worker.log').open('a')
        p=subprocess.Popen([sys.executable,str(SELF),'worker',action],stdout=log,stderr=log,start_new_session=True,close_fds=True)
        save(pid=p.pid,phase='busy',action=action,stage=1,started_at=int(time.time()),
             stage_started=int(time.time()),finished_at=None,message='Запуск…',error='')
if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    if action=='worker': worker(sys.argv[2])
    elif action=='changes': print(json.dumps(changes(),ensure_ascii=False))
    elif action=='status':
        s=read()
        if s.get('pid'):
            try: os.kill(s['pid'],0)
            except ProcessLookupError: save(pid=0,phase='error',finished_at=int(time.time()),message='Процесс прерван',error='Сборка прервалась. Повторите запуск.'); s=read()
        s['apk_exists'] = bool(s.get('apk') and Path(s['apk']).is_file())
        s['installer_available'] = shutil.which('omalauncher-install') is not None
        print(json.dumps(s,ensure_ascii=False))
    elif action=='clear-log':
        with (CACHE/'worker.lock').open('w') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise SystemExit('Нельзя очистить журнал во время проверки или сборки')
            (CACHE/'build.log').write_text('')
            (CACHE/'worker.log').write_text('')
    elif action in ('check','update','build','auto','resume'):
        if action!='auto' or time.time()-read().get('checked',0)>3600: start(action)
    else: raise SystemExit('status | check | update | build | auto | resume | changes | clear-log')
