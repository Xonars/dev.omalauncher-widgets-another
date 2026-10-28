import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import account
import downloads

BOARD = dict(id='123', name='Mine', profile='me', count=2, url='/me/mine/')


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        replacements = [(account, 'ROOT', self.root), (downloads, 'STATE_DIR', self.root),
                        (downloads, 'STATE', self.root / 'downloads.json'),
                        (account.pinterest, 'ROOT', self.root)]
        replacements += [(account, key, self.root / name) for key, name in [('ACCOUNT','account.json'), ('MY_BOARDS','my-boards.json'),('FEED','feed.json'),('SAVES','saved-pins.json')]]
        for obj, name, value in replacements:
            p = patch.object(obj, name, value);p.start(); self.addCleanup(p.stop)
        account.write(account.ACCOUNT, dict(connected=True, username='me'))
        account.write(account.MY_BOARDS, dict(username='me', boards=[BOARD]))
        account.write(downloads.STATE, dict(jobs={'123': dict(board=BOARD, status='completed', saved=2)}))

    def test_save_only_after_confirmed_success_marks_board_outdated(self):
        client = Mock(); client.api.return_value = dict(resource_response=dict(data=dict(id='saved-42')))
        with patch.object(account, 'Client', return_value=client):
            result = account.save_pin(dict(pinId='42', boardId='123'))
        self.assertTrue(result['ok'])
        self.assertEqual(client.api.call_args.args[0], 'RepinResource')
        self.assertTrue(client.api.call_args.args[2])
        self.assertTrue(account.pinterest.read(downloads.STATE)['jobs']['123']['dirty'])
        self.assertEqual(account.pinterest.read(account.SAVES)['42']['123']['id'], 'saved-42')

    def test_foreign_board_is_not_written(self):
        client = Mock()
        with patch.object(account, 'Client', return_value=client), self.assertRaises(RuntimeError):
            account.save_pin(dict(pinId='42', boardId='999'))
        client.api.assert_not_called()

    def test_failed_save_does_not_claim_success_or_mark_board(self):
        client = Mock(); client.api.side_effect = RuntimeError('Expired session')
        with patch.object(account, 'Client', return_value=client), self.assertRaises(RuntimeError):
            account.save_pin(dict(pinId='42', boardId='123'))
        self.assertNotIn('dirty', account.pinterest.read(downloads.STATE)['jobs']['123'])
        self.assertFalse(account.SAVES.exists())

    def test_picker_filters_out_foreign_boards_and_follows_pages(self):
        client = Mock()
        client.api.side_effect = [dict(resource_response=dict(data=[dict(BOARD, type='board', owner=dict(username='me')),dict(BOARD, id='456', type='board', owner=dict(username='other'))],bookmark='next')),
                                  dict(resource_response=dict(data=[dict(BOARD, id='789', type='board', owner=dict(username='other'), collaborated_by_me=True)],bookmark='-end-'))]
        result = account.my_boards(client, 'me')
        self.assertEqual({b['id'] for b in result['boards']}, {'123','789'})
        self.assertEqual(client.api.call_count,2)

    def test_feed_pagination_uses_bookmark_and_never_writes(self):
        account.write(account.FEED,dict(resource='UserHomefeedResource',bookmark='next',options={},page=1))
        client=Mock();client.api.return_value=dict(resource_response=dict(status='success',data=[dict(id='42',type='pin',images={'736x':dict(url='https://i.pinimg.com/736x/test.jpg')})],bookmark='end'))
        with patch.object(account,'Client',return_value=client): account.feed('next')
        self.assertEqual(client.api.call_args.args[1]['bookmarks'],['next'])
        self.assertEqual(len(client.api.call_args.args),2)
        self.assertEqual(account.pinterest.read(account.FEED)['items'][0]['id'],'42')

    def test_untrusted_image_host_is_rejected(self):
        self.assertIsNone(account.pin_item(dict(id='42',images={'orig':dict(url='https://example.com/a.jpg')})))

if __name__=='__main__':unittest.main()
