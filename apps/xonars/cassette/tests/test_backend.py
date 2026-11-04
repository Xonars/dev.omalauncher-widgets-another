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


if __name__ == '__main__':
    unittest.main()
