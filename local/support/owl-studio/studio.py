#!/usr/bin/env python3
"""Data model + OWL source generator, not an OWL interpreter. Python stdlib only."""
import copy
import fcntl
import json
import math
import os
from pathlib import Path
import re
import tempfile
import uuid
import hashlib
import subprocess
import sys
import time

TYPES = {'Text', 'Button', 'Row', 'Column', 'Box'}
CONTAINERS = {'Row', 'Column', 'Box'}
COLORS = {'foreground', 'background', 'surface', 'accent', 'muted', 'red', 'green', 'blue', 'yellow'}
STYLES = {'huge', 'title', 'body', 'small', 'muted', 'label'}


def quote(text):
    # Lexer.escape accepts escaped $, unlike JSON. Never interpolate user text.
    return json.dumps(text, ensure_ascii=False).replace('${', '\\${')


def atomic(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Символические ссылки запрещены: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.studio-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data if isinstance(data, bytes) else data.encode('utf-8'))
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def validate_props(kind, props):
    allowed = {'padding', 'color', 'background'}
    if kind in CONTAINERS:
        allowed |= {'gap'} if kind != 'Box' else set()
    else:
        allowed |= {'text'}
    if kind == 'Text':
        allowed |= {'style', 'binding'}
    if kind == 'Button':
        allowed |= {'action'}
    if not isinstance(props, dict) or set(props) - allowed:
        raise ValueError('Свойство не поддерживается для ' + kind)
    for key, value in props.items():
        if key in ('padding', 'gap'):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 64:
                raise ValueError('Отступ должен быть от 0 до 64')
        elif key in ('color', 'background'):
            if value not in COLORS:
                raise ValueError('Неизвестный цвет темы')
        elif key == 'style':
            if value not in STYLES:
                raise ValueError('Неизвестный стиль')
        elif key == 'binding':
            if value not in ('literal', 'counter'):
                raise ValueError('Неизвестная привязка')
        elif key == 'action':
            if value not in ('none', 'increment'):
                raise ValueError('Неизвестное действие')
        elif not isinstance(value, str) or len(value) > 2000 or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise ValueError('Некорректный текст (максимум 2000 символов)')


def validate(p):
    if p.get('version') != 1 or p.get('kind') not in ('widget', 'app'):
        raise ValueError('Неподдерживаемый формат проекта')
    if not isinstance(p.get('name'), str) or not 1 <= len(p['name'].strip()) <= 120:
        raise ValueError('Название: 1–120 символов')
    if any(ord(c) < 32 for c in p['name']):
        raise ValueError('Управляющий символ в названии')
    nodes = p.get('nodes')
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 80:
        raise ValueError('Лимит: 1–80 компонентов')
    by_id = {n['id']: n for n in nodes}
    if len(by_id) != len(nodes) or nodes[0]['id'] != 'n0' or nodes[0]['parent'] != '' or nodes[0]['type'] != 'Column':
        raise ValueError('Некорректный корень/повтор ID')
    for n in nodes:
        if not re.fullmatch(r'n[0-9]+', n['id']) or n['type'] not in TYPES:
            raise ValueError('Некорректный компонент')
        validate_props(n['type'], n['props'])
        trail = {n['id']}
        current = n
        while current['parent']:
            parent = by_id.get(current['parent'])
            if parent is None or parent['type'] not in CONTAINERS or parent['id'] in trail:
                raise ValueError('Некорректный родитель или цикл')
            trail.add(parent['id'])
            current = parent
            if len(trail) > 8:
                raise ValueError('Лимит глубины: 8')
        if current['id'] != 'n0':
            raise ValueError('Компонент вне корня')


def generate(p):
    validate(p)
    lines = [p['kind'] + ' ' + quote(p['name']) + ' {', '  meta { owl: 12 }', '  requires { pacman: [] }']
    if p['kind'] == 'widget':
        lines += ['  size: 3x3', '  minSize: 2x2']
    lines += ['  state count = 0 persist']
    tree = []

    def emit(n, depth):
        indent = '  ' * depth
        tree.append(dict(n, label=('  ' * (depth - 1)) + n['type'] + ' · ' + n['id']))
        lines.append(indent + n['type'] + ' {')
        for key, value in n['props'].items():
            if key in ('action', 'binding'):
                continue
            if key == 'text' and n['props'].get('binding') == 'counter':
                continue
            val = quote(value) if key == 'text' else str(value)
            lines.append(indent + '  ' + key + ': ' + val)
        if n['type'] == 'Text' and n['props'].get('binding') == 'counter':
            lines.append(indent + '  text: "${count}"')
        if n['type'] == 'Button' and n['props'].get('action') == 'increment':
            lines.append(indent + '  onTap: count = count + 1')
        for child in p['nodes']:
            if child['parent'] == n['id']:
                emit(child, depth + 1)
        lines.append(indent + '}')

    emit(p['nodes'][0], 1)
    lines.append('}')
    return '\n'.join(lines) + '\n', tree


class Studio:
    def __init__(self, root, widgets, compiler):
        self.root = Path(root)
        self.widgets = Path(widgets)
        self.compiler = compiler
        if self.root.is_symlink():
            raise ValueError('Каталог данных не может быть ссылкой')
        self.root.mkdir(parents=True, exist_ok=True)

    def project_path(self, pid):
        if not isinstance(pid, str) or not re.fullmatch(r'[a-f0-9]{12}', pid):
            raise ValueError('Некорректный ID проекта')
        return self.root / (pid + '.json')

    def load(self, pid):
        path = self.project_path(pid)
        if path.is_symlink() or path.stat().st_size > 262144:
            raise ValueError('Недопустимый файл проекта')
        p = json.loads(path.read_text())
        validate(p)
        if p['id'] != pid:
            raise ValueError('ID файла не совпадает')
        return p

    def save(self, p):
        validate(p)
        atomic(self.project_path(p['id']), json.dumps(p, ensure_ascii=False, indent=2))

    def view(self, pid='', ok=True, status=None):
        projects, warnings = [], []
        for file in sorted(self.root.glob('*.json')):
            if not re.fullmatch(r'[a-f0-9]{12}', file.stem):
                continue
            try:
                p = self.load(file.stem)
                projects.append({'id': p['id'], 'name': p['name']})
            except (ValueError, KeyError, TypeError, OSError) as e:
                warnings.append(file.name + ': ' + str(e))
        p = self.load(pid) if pid else None
        code, tree = generate(p) if p else ('', [])
        meta = self.read_build(pid) if pid else {}
        output = self.widgets / ('owl-studio-v01-' + pid + '.owl') if pid else None
        published = bool(output and output.is_file() and not output.is_symlink() and meta.get('sha256') == hashlib.sha256(output.read_bytes()).hexdigest())
        return {'ok': ok, 'projects': projects, 'project': p, 'tree': tree, 'code': code,
                'status': status if status is not None else '\n'.join(warnings + [meta.get('status', '')]),
                'output': str(output) if published else '',
                'preview': meta.get('preview', '') if published and meta.get('checked_sha256') == meta.get('sha256') and Path(meta.get('preview', '')).is_file() else '',
                'published': published, 'buildCurrent': published and meta.get('revision') == p['revision'],
                'openkey': 'o:' + output.name if published and p['kind'] == 'app' else ''}

    def read_build(self, pid):
        path = self.root / (pid + '.build.json')
        if path.is_symlink():
            raise ValueError('Недопустимый файл диагностики')
        return json.loads(path.read_text()) if path.exists() else {}

    def record_build(self, pid, meta):
        atomic(self.root / (pid + '.build.json'), json.dumps(meta, ensure_ascii=False))

    def build(self, p):
        pid = p['id']
        if not self.compiler:
            raise ValueError('Не настроен настоящий OWL-компилятор')
        source, _ = generate(p)
        candidate = self.root / (pid + '.candidate.owl')
        atomic(candidate, source)
        meta = self.read_build(pid)
        try:
            result = subprocess.run(self.compiler + [str(candidate)], capture_output=True, text=True, timeout=15)
            diagnostic = (result.stdout + result.stderr)[-12000:]
            if result.returncode:
                meta['status'] = 'Ошибка компиляции; опубликованный файл не изменён.\n' + diagnostic
                self.record_build(pid, meta)
                return self.view(pid, False)
        except subprocess.TimeoutExpired:
            meta['status'] = 'Компилятор не ответил за 15 секунд; исходный файл не изменён'
            self.record_build(pid, meta)
            return self.view(pid, False)
        if self.widgets.is_symlink():
            raise ValueError('Каталог экспорта не может быть ссылкой')
        self.widgets.mkdir(parents=True, exist_ok=True)
        target = self.widgets / ('owl-studio-v01-' + pid + '.owl')
        # Never overwrite an unrelated file or a user edit, even with our prefix.
        if target.is_symlink():
            raise ValueError('Файл экспорта является ссылкой')
        if target.exists():
            previous = target.read_bytes()
            if meta.get('sha256') != hashlib.sha256(previous).hexdigest():
                raise ValueError('Экспорт изменён вне Studio; запись отменена')
            atomic(self.root / (pid + '.previous.owl'), previous)
        atomic(target, source)
        meta = {'sha256': hashlib.sha256(source.encode()).hexdigest(), 'revision': p['revision'],
                'status': 'Компилятор: OK. Файл опубликован атомарно. Выполните owl-check для проверки в лаунчере.\n' + diagnostic}
        self.record_build(pid, meta)
        return self.view(pid)

    def check(self, p):
        pid = p['id']
        current = self.view(pid)
        if not current['published']:
            raise ValueError('Сначала сгенерируйте файл; изменённый вне Studio файл не проверяется')
        meta = self.read_build(pid)
        meta.pop('preview', None)
        meta.pop('checked_sha256', None)
        try:
            result = subprocess.run(['owl-check', current['output']], capture_output=True, text=True, timeout=22)
            meta['status'] = 'owl-check: ' + ('OK' if result.returncode == 0 else 'ОШИБКА') + '\n' + (result.stdout + result.stderr)[-12000:]
            ok = result.returncode == 0
            target = Path(current['output'])
            record = self.widgets / '.check' / (target.name + '.txt')
            check_text = record.read_text() if record.is_file() and not record.is_symlink() else ''
            sha = meta['sha256']
            marker = 'screen' if p['kind'] == 'app' else 'preview'
            image = self.widgets / '.preview' / (target.name + ('.screen.png' if p['kind'] == 'app' else '.png'))
            fresh = ('sha256 ' + sha) in check_text.splitlines() and 'result ok' in check_text.splitlines()
            fresh = fresh and any(line.startswith(marker + ' ' + sha + ' ') for line in check_text.splitlines())
            if ok and fresh and image.is_file() and not image.is_symlink():
                snapshot = self.root / (pid + '.preview-' + str(time.time_ns()) + '.png')
                png = image.read_bytes()
                if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png) > 16777216:
                    raise ValueError('Некорректный PNG')
                atomic(snapshot, png)
                meta['preview'] = str(snapshot)
                meta['checked_sha256'] = sha
                for old in sorted(self.root.glob(pid + '.preview-*.png'))[:-3]:
                    old.unlink()
            else:
                meta['status'] += '\nАктуальный PNG не подтверждён; снимок не отображается.'
        except subprocess.TimeoutExpired:
            meta['status'] = 'owl-check: таймаут 22 секунды. Это не подтверждает успешную проверку; повторите её.'
            ok = False
        self.record_build(pid, meta)
        return self.view(pid, ok)

    def handle(self, req):
        lock = self.root / '.lock'
        if lock.is_symlink():
            raise ValueError('Недопустимый lock')
        with lock.open('a') as out:
            deadline = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(out, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        return {'ok': False, 'status': 'Studio занята другой операцией; повторите позже'}
                    time.sleep(0.05)
            pid = req.get('project', '')
            try:
                return self.dispatch(req)
            except (ValueError, KeyError, TypeError, OSError) as e:
                try:
                    return self.view(pid, False, str(e))
                except (ValueError, KeyError, TypeError, OSError):
                    return self.view('', False, str(e))

    def dispatch(self, req):
        op = req['op']
        pid = req.get('project', '')
        if op == 'view':
            return self.view(pid)
        if op in ('new', 'demo'):
            pid = uuid.uuid4().hex[:12]
            p = {'version': 1, 'id': pid, 'name': req.get('name', 'Счётчик Studio' if op == 'demo' else 'Без имени'), 'kind': req.get('kind', 'widget'),
                 'revision': 1, 'nodes': [{'id': 'n0', 'parent': '', 'type': 'Column', 'props': {'gap': 8}}]}
            if op == 'demo':
                p['nodes'] += [
                    {'id': 'n1', 'parent': 'n0', 'type': 'Text', 'props': {'text': 'Счётчик Studio', 'style': 'title', 'color': 'accent'}},
                    {'id': 'n2', 'parent': 'n0', 'type': 'Text', 'props': {'binding': 'counter', 'style': 'title', 'color': 'foreground'}},
                    {'id': 'n3', 'parent': 'n0', 'type': 'Button', 'props': {'text': '+1', 'action': 'increment', 'color': 'accent'}}]
            self.save(p)
            return self.view(pid, status='Проект создан и сохранён')
        p = self.load(pid)
        if op == 'build':
            return self.build(p)
        if op == 'check':
            return self.check(p)
        if 'revision' in req and req['revision'] != p['revision']:
            raise ValueError('Проект изменён: перечитайте его перед записью')
        by_id = {n['id']: n for n in p['nodes']}
        if op == 'add':
            parent = by_id[req['parent']]
            if parent['type'] not in CONTAINERS or req['type'] not in TYPES:
                raise ValueError('Выберите контейнер Row, Column или Box')
            nid = 'n' + str(max(int(n['id'][1:]) for n in p['nodes']) + 1)
            kind = req['type']
            props = {'text': kind} if kind not in CONTAINERS else ({} if kind == 'Box' else {'gap': 8})
            p['nodes'].append({'id': nid, 'parent': parent['id'], 'type': kind, 'props': props})
        elif op == 'set':
            node = by_id[req['node']]
            props = dict(node['props'], **req['props'])
            validate_props(node['type'], props)
            node['props'] = props
        elif op == 'delete':
            nid = req['node']
            if nid == 'n0' or nid not in by_id:
                raise ValueError('Корень удалить нельзя')
            removed = {nid}
            while True:
                children = {n['id'] for n in p['nodes'] if n['parent'] in removed}
                if children <= removed:
                    break
                removed |= children
            p['nodes'] = [n for n in p['nodes'] if n['id'] not in removed]
        elif op == 'move':
            node = by_id[req['node']]
            siblings = [n for n in p['nodes'] if n['parent'] == node['parent']]
            delta = req['delta']
            if type(delta) is not int or delta not in (-1, 1):
                raise ValueError('Направление должно быть -1 или 1')
            idx = siblings.index(node)
            if 0 <= idx + delta < len(siblings):
                other = siblings[idx + delta]
                a, b = p['nodes'].index(node), p['nodes'].index(other)
                p['nodes'][a], p['nodes'][b] = p['nodes'][b], p['nodes'][a]
        elif op != 'save':
            raise ValueError('Неизвестная операция')
        p['revision'] += 1
        self.save(p)
        return self.view(pid, status='Проект сохранён')


def main():
    try:
        if len(sys.argv) != 2 or len(sys.argv[1]) > 32768:
            raise ValueError('Ожидается один JSON-запрос (до 32 KiB)')
        req = json.loads(sys.argv[1])
        if not isinstance(req, dict) or not isinstance(req.get('op'), str):
            raise ValueError('Нужен объект с полем op')
        install = Path(__file__).resolve().parent
        data = Path(os.environ.get('OWL_STUDIO_DATA', str(install / 'projects'))).expanduser()
        widgets = Path(os.environ.get('OWL_STUDIO_WIDGETS', '~/.config/omalauncher/widgets')).expanduser()
        jar = Path(os.environ.get('OWL_STUDIO_JAR', str(install / 'owl.jar'))).expanduser()
        result = Studio(data, widgets, ['java', '-jar', str(jar), 'check']).handle(req)
        result['request'] = req.get('request')
    except (ValueError, KeyError, TypeError, OSError) as e:
        result = {'ok': False, 'status': str(e)}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
