#!/usr/bin/env python3
"""Validate an agent's published source changes before starting a fresh build."""
import subprocess
import sys
from pathlib import Path

REPO = Path('/root/dev.omalauncher-another')
UPDATER = Path('/root/.local/share/oma-updater/updater.py')


def git(*args):
    result = subprocess.run(['git', *args], cwd=REPO, text=True,
                            capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-1200:] or 'Ошибка Git')
    return result.stdout.strip()


def validate(integrate=False):
    if git('branch', '--show-current') != 'main':
        raise RuntimeError('Вернитесь в локальную main после интеграции.')
    for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        path = Path(git('rev-parse', '--git-path', name))
        if (path if path.is_absolute() else REPO / path).exists():
            raise RuntimeError('Операция Git ещё не завершена. Вернитесь к Codex.')
    if git('status', '--porcelain'):
        raise RuntimeError('Есть несохранённые изменения или конфликты. Попросите Codex завершить коммит.')
    git('fetch', '--no-tags', 'origin', 'main')
    if git('rev-parse', 'HEAD') != git('rev-parse', 'origin/main'):
        raise RuntimeError('Локальная main отличается от GitHub. Попросите Codex завершить синхронизацию и push.')
    if integrate:
        git('fetch', '--no-tags', 'upstream', 'main')
        result = subprocess.run(['git', 'merge-base', '--is-ancestor', 'upstream/main', 'HEAD'], cwd=REPO)
        if result.returncode:
            raise RuntimeError('Не все коммиты upstream включены в main. Вернитесь к Codex для завершения интеграции.')


def main():
    try:
        validate('--upstream' in sys.argv[1:])
        subprocess.run([sys.executable, str(UPDATER), 'build'], check=True, timeout=30)
        print('ok')
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
