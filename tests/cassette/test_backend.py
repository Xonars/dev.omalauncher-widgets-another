"""Regression tests for the actual embedded bridge, without touching the running player."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / 'app.owl'


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        code = APP.read_text().split('let backend = """', 1)[1].split('"""', 1)[0]
        self.bridge = {'__name__': 'cassette_test'}
        with patch('pathlib.Path.home', return_value=Path(self.temp.name)):
            exec(compile(code, str(APP), 'exec'), self.bridge)

    def test_each_skip_sends_a_distinct_event_to_the_same_owl_queue(self):
        with patch('subprocess.run') as run, patch('time.time_ns', side_effect=[10, 11, 12]):
            for action in ['next', 'next', 'previous']:
                self.bridge['main']([action])
        events = [call.args[0] for call in run.call_args_list]
        self.assertTrue(all(e[:4] == ['owl-send', 'cassette.owl', 'set', 'mediaControl'] for e in events))
        self.assertEqual([json.loads(e[4]) for e in events], [
            {'action': 'next', 'nonce': 10}, {'action': 'next', 'nonce': 11},
            {'action': 'previous', 'nonce': 12}])

    def test_stop_goes_through_queue_owner_before_stopping_mpv(self):
        with patch('subprocess.run') as run:
            self.bridge['main'](['stop-control'])
        self.assertEqual('stop-control', json.loads(run.call_args.args[0][4])['action'])

    def test_single_track_repeat_can_reload_an_unloaded_mpv_file(self):
        track = {'source': 'https://storage.yandex.net/download-info', 'local': False}
        self.bridge['write_json'](self.bridge['NOW_PLAYING'], track)
        commands = []
        self.bridge['ensure_player'] = lambda: None
        self.bridge['resolve'] = lambda url: 'https://storage.yandex.net/audio'
        self.bridge['ipc'] = commands.append
        self.bridge['main'](['replay'])
        self.assertEqual([['loadfile', 'https://storage.yandex.net/audio', 'replace'],
                          ['set_property', 'pause', False]], commands)

    def test_local_repeat_keeps_path_validation(self):
        self.bridge['write_json'](self.bridge['NOW_PLAYING'], {'source': '/etc/passwd', 'local': True})
        self.bridge['ensure_player'] = lambda: None
        with self.assertRaises(ValueError):
            self.bridge['main'](['replay'])

    def test_metadata_keeps_replay_source_without_an_account_token(self):
        result = self.bridge['metadata'](['play', 'https://storage.yandex.net/info', '42', 'Title', 'Artist', 'cover'])
        self.assertEqual('42', result['id'])
        self.assertEqual('https://storage.yandex.net/info', result['source'])
        self.assertNotIn('token', result)


class ArtworkTest(unittest.TestCase):
    setUp = BackendTest.setUp
    def test_downloaded_cover_is_embedded_and_available_offline_in_library(self):
        import base64
        import io
        import subprocess
        music = self.bridge['MUSIC']
        music.mkdir(parents=True)
        audio = music / 'Artist - Title.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'anullsrc=r=44100:cl=stereo', '-t', '0.15', str(audio)], check=True)
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aE1sAAAAASUVORK5CYII=')
        track = {'id': '42', 'title': 'Title', 'artists': [{'id': '7', 'name': 'Artist'}],
                 'albums': [{'id': '8', 'title': 'Album'}], 'coverUri': 'avatars.yandex.net/cover/%%'}
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(png)
            self.assertTrue(self.bridge['save_track_art'](audio, track))
        result = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(audio)]))
        self.assertTrue(any(s.get('disposition', {}).get('attached_pic') == 1 for s in result['streams']))
        self.assertEqual('Album', result['format']['tags']['album'])
        offline = self.bridge['local_tracks']()[0]
        self.assertTrue(Path(offline['coverPath']).is_file())
        self.assertEqual('7', offline['artists'][0]['id'])
        self.assertEqual('8', offline['albums'][0]['id'])
        self.assertEqual('local:Artist - Title.mp3', offline['id'])

    def test_legacy_repair_only_matches_the_exact_download_filename(self):
        from unittest.mock import Mock
        music = self.bridge['MUSIC']
        music.mkdir(parents=True)
        (music / 'Artist - Title.mp3').write_bytes(b'audio')
        save = Mock(return_value=True)
        self.bridge['save_track_art'] = save
        tracks = [{'title': 'Other', 'artists': [{'name': 'Artist'}], 'coverUri': 'avatars.yandex.net/a/%%'},
                  {'title': 'Title', 'artists': [{'name': 'Artist'}], 'coverUri': 'avatars.yandex.net/b/%%'}]
        self.assertEqual(1, self.bridge['repair_downloads'](tracks))
        save.assert_called_once_with(music / 'Artist - Title.mp3', tracks[1])

    def test_cover_failure_does_not_lose_the_downloaded_audio(self):
        import io
        from unittest.mock import Mock
        self.bridge['ensure_player'] = lambda: None
        self.bridge['resolve'] = lambda url: 'https://storage.yandex.net/audio'
        self.bridge['save_track_art'] = Mock(side_effect=OSError('offline'))
        with patch('urllib.request.build_opener') as opener, patch('sys.stdout'):
            opener.return_value.open.return_value = io.BytesIO(b'complete audio')
            self.bridge['main'](['download', 'https://storage.yandex.net/info', 'Artist - Title', '{}'])
        self.assertEqual(b'complete audio', (self.bridge['MUSIC'] / 'Artist - Title.mp3').read_bytes())


if __name__ == '__main__':
    unittest.main()
