"""Run the GPL-3.0 KindleUnpack program in a separate, resource-limited process."""
from pathlib import Path
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU, (20, 21))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
sys.path.insert(0, str(Path(__file__).parent / 'vendor' / 'KindleUnpack'))
from lib.kindleunpack import unpackBook

if __name__ == '__main__':
    unpackBook(sys.argv[1], sys.argv[2])
