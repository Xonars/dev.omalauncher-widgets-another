# Fixed helper embedded in the store version of omagit: read-only Git statistics.
import subprocess
import sys
repo = sys.argv[1]
print(repo)
if not repo:
    raise SystemExit(0)
def git(*args):
    return subprocess.run(['git','-C',repo,'-c','core.quotePath=false',*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout
sys.stdout.buffer.flush()
sys.stdout.flush()
sys.stdout.buffer.write(git('diff','--no-ext-diff','--numstat'))
for path in git('ls-files','--others','--exclude-standard','-z').split(b'\0'):
    if path:
        result = subprocess.run(['git','-C',repo,'diff','--no-ext-diff','--numstat','--no-index','--','/dev/null',path.decode()],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        sys.stdout.buffer.write(result.stdout)
