"""Pinned remote assets are lazy, verified, and served through the local boundary."""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('video_review_azure', ROOT / 'tools/policy-video-review/server.py')
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class AzureReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = 'https://account.blob.core.windows.net/container/bundle'
        self.identifier = 'hy_vla/pick_diverse_object/100052'
        self.prefix = 'evaluation/hy_vla/pick_diverse_object/pick_diverse_object_ep100052'
        index = io.StringIO(newline='')
        writer = csv.DictWriter(index, ['policy', 'task', 'seed', 'mode', 'success', 'instruction', 'record', 'video'])
        writer.writeheader()
        writer.writerow(dict(policy='hy_vla', task='pick_diverse_object', seed=100052, mode='seen',
                             success=1, instruction='Pick up the coffee box', record=self.prefix + '_result.json',
                             video=self.prefix + '_1.mp4'))
        self.blobs = {
            'episode-index.csv': index.getvalue().encode(),
            'evaluation/plan.json': json.dumps(dict(tasks=[dict(task='pick_diverse_object', seeds=[100052], modes={'seen': 0})])).encode(),
            self.prefix + '_result.json': json.dumps(dict(task='pick_diverse_object', seed=100052, status='success', success=True)).encode(),
            self.prefix + '_1.mp4': b'original video bytes',
        }
        inventory = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in self.blobs.items()).encode()
        self.blobs['SHA256SUMS'] = inventory
        self.pin = hashlib.sha256(inventory).hexdigest()
        self.downloaded = []
        def fetch(request, timeout):
            relative = request.full_url.removeprefix(self.base + '/')
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')
            self.downloaded.append(relative)
            response = io.BytesIO(self.blobs[relative])
            response.url = request.full_url
            return response
        self.opener = patch.object(app, 'build_opener')
        self.opener.start().return_value.open.side_effect = fetch
        self.addCleanup(self.opener.stop)
        auth = patch.object(app.AzureCatalog, 'access_token', return_value='test-token')
        auth.start()
        self.addCleanup(auth.stop)

    def catalog(self, pin=None):
        return app.AzureCatalog(self.base, pin or self.pin, self.root / 'cache')

    def test_index_does_not_download_all_videos_and_signatures_survive_cache_population(self):
        catalog = self.catalog()
        self.assertEqual(set(self.downloaded), {'SHA256SUMS', 'episode-index.csv', 'evaluation/plan.json'})
        row = catalog.rows[self.identifier]
        self.assertEqual((row['automatic'], row['block']), ('success', 0))
        before = row['source_signature']
        files = catalog.paths[self.identifier]
        self.assertEqual(catalog.ensure_file(files['video']).read_bytes(), b'original video bytes')
        self.assertEqual(catalog.signature(files), before)
        catalog.ensure_file(files['video'])
        self.assertEqual(self.downloaded.count(self.prefix + '_1.mp4'), 1)
        self.downloaded.clear()
        reopened = self.catalog()
        reopened.ensure_file(reopened.paths[self.identifier]['video'])
        self.assertEqual(self.downloaded, [])

    def test_remote_corruption_and_wrong_root_hash_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.catalog(pin='0' * 64)
        catalog = self.catalog()
        self.blobs[self.prefix + '_1.mp4'] = b'changed video'
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            catalog.ensure_file(catalog.paths[self.identifier]['video'])
        self.assertFalse(catalog.paths[self.identifier]['video'].exists())
        self.assertFalse(list((self.root / 'cache').rglob('*.download-*')))

    def test_v1_verbose_index_columns_are_supported(self):
        self.blobs['episode-index.csv'] = self.blobs['episode-index.csv'].replace(
            b',record,video\r\n', b',record_path,video_path\r\n')
        inventory = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                            for name, data in self.blobs.items() if name != 'SHA256SUMS').encode()
        self.blobs['SHA256SUMS'] = inventory
        self.pin = hashlib.sha256(inventory).hexdigest()
        catalog = self.catalog()
        self.assertEqual(catalog.rows[self.identifier]['automatic'], 'success')
        self.assertEqual(catalog.paths[self.identifier]['video'].name, 'pick_diverse_object_ep100052_1.mp4')

    def test_cache_corruption_is_repaired_and_unknown_paths_are_rejected(self):
        catalog = self.catalog()
        path = catalog.paths[self.identifier]['video']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'partial')
        self.assertEqual(catalog.ensure_file(path).read_bytes(), b'original video bytes')
        path.write_bytes(b'changed after first access')
        self.assertEqual(catalog.ensure_file(path).read_bytes(), b'original video bytes')
        with self.assertRaises(KeyError):
            catalog.ensure_file(catalog.run / 'not-in-inventory')
        with self.assertRaises(ValueError):
            catalog.ensure_file(catalog.run / '../outside')
        for url in ('http://account.blob.core.windows.net/a', 'https://example.com/a', self.base + '?sig=secret'):
            with self.assertRaises(ValueError):
                app.AzureCatalog(url, self.pin, self.root / 'bad')

    def test_redirect_is_rejected_before_forwarding_credentials(self):
        with self.assertRaisesRegex(OSError, 'redirects'):
            app.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')

    def test_overall_weights_tasks_not_episodes_and_ignores_human_reviews(self):
        rows = [dict(policy='xvla', task='arm_select', mode='left', automatic='success', archived=False, review={'label': 'failure'})]
        rows += [dict(policy='xvla', task='attribute_select', mode='size:big', automatic='failure', archived=False) for _ in range(9)]
        rows += [dict(policy='xvla', task='grasp_cube_approach', mode='top', automatic='failure', archived=True)]
        score = app.score_overview(rows)['policies']['xvla']
        self.assertEqual(score['overall'], .5)
        self.assertEqual(score['overall_percent'], 50)
        self.assertEqual(score['tasks']['arm_select']['success'], 1)
        rows[0]['automatic'] = 'error'
        self.assertIsNone(app.score_overview(rows)['policies']['xvla']['overall'])

    def test_rounding_matches_the_published_python_table(self):
        rows = []
        for task, successes, total in zip(app.TASKS, [18, 30, 108, 37, 17, 26], [40, 40, 160, 40, 120, 60]):
            rows.extend(dict(policy='lingbot_va', task=task, mode='example', archived=False,
                             automatic='success' if i < successes else 'failure') for i in range(total))
        self.assertEqual(app.score_overview(rows)['policies']['lingbot_va']['overall_percent'], 56.2)


if __name__ == '__main__':
    unittest.main()
