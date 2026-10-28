import hashlib
import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('player', Path(__file__).with_name('player.py'))
player = importlib.util.module_from_spec(spec)
spec.loader.exec_module(player)

class Response:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit):
        return b'<download-info><host>audio.music.yandex.net</host><path>/abc.mp3</path><ts>123</ts><s>salt</s></download-info>'

class Opener:
    def open(self, *args, **kwargs): return Response()

class PlayerTests(unittest.TestCase):
    def test_signed_audio_url(self):
        with patch.object(player.urllib.request, 'build_opener', return_value=Opener()):
            url = player.resolve('https://storage.music.yandex.net/info')
        digest = hashlib.md5(b'XGRlBW9FXlekgbPrRHuSiAabc.mp3salt').hexdigest()
        self.assertEqual(url, f'https://audio.music.yandex.net/get-mp3/{digest}/123/abc.mp3')

    def test_reject_foreign_or_local_urls(self):
        for url in ['http://music.yandex.net/x', 'https://yandex.net.evil.org/x',
                    'https://127.0.0.1/x', 'file:///etc/passwd', 'https://user@music.yandex.net/x']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                player.trusted_url(url)

    def test_local_path_stays_in_music_directory(self):
        player.MUSIC.mkdir(parents=True, exist_ok=True)
        allowed = player.MUSIC / 'test.mp3'
        allowed.touch()
        try:
            self.assertEqual(player.local_path(str(allowed)), allowed.resolve())
            with self.assertRaises(ValueError):
                player.local_path('/etc/passwd')
            with self.assertRaises(ValueError):
                player.local_path(str(player.MUSIC / '../outside.mp3'))
        finally:
            allowed.unlink(missing_ok=True)

    def test_metadata_is_safe_with_missing_optional_fields(self):
        self.assertEqual(
            player.metadata(['play', 'url', '42', 'Название']),
            {'id': '42', 'title': 'Название', 'artist': '', 'cover': '', 'local': False})

    def test_json_state_is_atomic_and_tolerates_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            player.write_json(path, {'title': 'Тест'})
            self.assertEqual(player.read_json(path, {}), {'title': 'Тест'})
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(player.read_json(path, {'safe': True}), {'safe': True})

    def test_explicit_android_playback_controls(self):
        calls = []
        with patch.object(player, 'ensure_player'), patch.object(player, 'ipc', side_effect=lambda command: calls.append(command)):
            player.main(['play-control'])
            player.main(['pause-control'])
        self.assertEqual(calls, [
            ['set_property', 'pause', False],
            ['set_property', 'pause', True],
        ])

if __name__ == '__main__': unittest.main()
