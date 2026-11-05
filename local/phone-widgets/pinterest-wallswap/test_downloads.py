import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import downloads
import viewer

BOARD = dict(id='123', name='Test', profile='xonars', count=2, url='/xonars/test/')


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(downloads, 'STATE_DIR', self.root),
                        patch.object(downloads, 'STATE', self.root / 'downloads.json'),
                        patch.object(downloads, 'start_worker'),
                        patch.object(downloads, 'executable', return_value='/fake/gallery-dl')]
        for p in self.patches: p.start()
        self.addCleanup(self.temp.cleanup)
        for p in self.patches: self.addCleanup(p.stop)

    def enqueue(self):
        return downloads.enqueue(dict(board=BOARD, saveDirectory=str(self.root / 'Pictures with spaces')))

    def saved_image(self, job):
        p = Path(job['directory']) / 'a.jpg'
        p.write_bytes(b'test-image')
        Path(str(p) + '.json').write_text(json.dumps(dict(id='42', title='Local image', width=10, height=20)))
        return p

    def test_duplicate_queue_and_resume(self):
        job = self.enqueue()
        self.assertEqual(self.enqueue()['created'], job['created'])
        image = self.saved_image(job)
        downloads.atomic(Path(job['directory']) / '.pinterest-board.json', dict(items=[downloads.image_item(image, BOARD)]))
        downloads.update('123', status='error', saved=1)
        self.assertEqual(self.enqueue()['saved'], 1)

    def test_invalid_board_and_directory(self):
        with self.assertRaises(ValueError): downloads.destination('relative')
        with self.assertRaises(ValueError): downloads.validate_board(dict(BOARD, url='/xonars/test/?x=y'))

    def test_partial_failure_keeps_local_copy(self):
        job = self.enqueue()
        image = self.saved_image(job)
        process = unittest.mock.Mock(stdout=iter(['PW_FILE:' + str(image) + '\n']))
        process.wait.return_value = 4
        with patch.object(downloads.subprocess, 'Popen', return_value=process):
            downloads.run_job('123', job)
        state = downloads.snapshot()['jobs']['123']
        self.assertEqual((state['status'], state['saved']), ('error', 1))
        self.assertEqual(downloads.local_items('123')[0][0]['image'], str(image))

    def test_deleted_files_do_not_show_completed(self):
        job = self.enqueue()
        downloads.atomic(Path(job['directory']) / '.pinterest-board.json', dict(items=[dict(image=str(self.root / 'missing.jpg'))]))
        downloads.update('123', status='completed', saved=1)
        state = downloads.snapshot()['jobs']['123']
        self.assertEqual((state['status'], state['saved']), ('error', 0))

    def test_saved_board_next_prev_never_use_network(self):
        job = self.enqueue()
        first = self.saved_image(job)
        second = first.with_name('b.jpg'); second.write_bytes(b'test-image')
        downloads.atomic(Path(job['directory']) / '.pinterest-board.json', dict(items=[downloads.image_item(p, BOARD) for p in (first, second)]))
        downloads.update('123', status='completed', saved=2)
        with patch.object(viewer, 'STATE', self.root / 'viewer.json'), patch.object(viewer.pinterest, 'ROOT', self.root), patch.object(viewer, 'start_worker', side_effect=AssertionError('Network worker')), patch.object(viewer.pinterest, 'candidates', side_effect=AssertionError('Pinterest network')):
            def call(action):
                with patch.object(sys, 'argv', ['viewer.py', action, '{"boards":["123"],"profiles":"xonars"}']), contextlib.redirect_stdout(io.StringIO()):
                    viewer.main()
                return downloads.pinterest.read(viewer.STATE)
            self.assertEqual(call('open')['localIndex'], 0)
            self.assertEqual(call('next')['localIndex'], 1)
            self.assertEqual(call('next')['localIndex'], 1)
            self.assertEqual(call('prev')['localIndex'], 0)

    def test_batch_enqueues_entire_catalog_and_starts_once(self):
        with patch.object(downloads, 'start_worker') as launch:
            downloads.enqueue_all(dict(boards=[BOARD, dict(BOARD, id='456')], saveDirectory=str(self.root / 'Pictures')))
            launch.assert_called_once()
        jobs = downloads.pinterest.read(downloads.STATE)['jobs']
        self.assertEqual(set(jobs), {'123', '456'})
        self.assertTrue(all(job['status'] == 'queued' for job in jobs.values()))

    def test_new_pin_marks_completed_copy_outdated(self):
        self.enqueue()
        downloads.update('123', status='completed', saved=2)
        downloads.mark_changed('123')
        job = downloads.pinterest.read(downloads.STATE)['jobs']['123']
        self.assertTrue(job['dirty'])
        self.assertEqual(job['saved'], 2)

    def test_update_preserves_pin_deleted_online(self):
        job = self.enqueue()
        old = self.saved_image(job)
        new = old.with_name('new.jpg'); new.write_bytes(b'new-image')
        process = unittest.mock.Mock(stdout=iter(['PW_FILE:' + str(new) + '\n']))
        process.wait.return_value = 0
        with patch.object(downloads.subprocess, 'Popen', return_value=process):
            downloads.run_job('123', job)
        items, saved_job = downloads.local_items('123')
        self.assertTrue(old.is_file())
        self.assertEqual({i['image'] for i in items}, {str(old), str(new)})
        self.assertFalse(saved_job['dirty'])

    def test_pin_added_during_download_remains_outdated(self):
        job = self.enqueue()
        image = self.saved_image(job)
        def output():
            downloads.mark_changed('123')
            yield 'PW_FILE:' + str(image) + '\n'
        process = unittest.mock.Mock(stdout=output()); process.wait.return_value = 0
        with patch.object(downloads.subprocess, 'Popen', return_value=process): downloads.run_job('123', job)
        self.assertTrue(downloads.pinterest.read(downloads.STATE)['jobs']['123']['dirty'])

    def test_external_board_revision_marks_copy_outdated(self):
        self.enqueue()
        downloads.update('123', status='completed', saved=2, syncedAt=100, syncedPinCount=2)
        downloads.observe_boards([dict(BOARD, modifiedAt=101)])
        self.assertTrue(downloads.pinterest.read(downloads.STATE)['jobs']['123']['dirty'])

    def test_queue_runs_in_order(self):
        self.enqueue()
        downloads.enqueue(dict(board=dict(BOARD, id='456'), saveDirectory=str(self.root / 'Pictures')))
        order = []
        def run(board_id, job):
            order.append(board_id); downloads.update(board_id, status='completed')
        with patch.object(downloads, 'run_job', side_effect=run): downloads.worker()
        self.assertEqual(order, ['123', '456'])


if __name__ == '__main__': unittest.main()
