import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fast_feed


class FastFeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = {'updated': 123456, 'items': [], 'runtime': {'executor':'oracle', 'source_revision':'a'*40}, 'private_debug': 'not-public'}
        self.status = {'mode':'publish', 'published':True, 'validation_issues':[], 'source_revision':'a'*40}
        self.write()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        candidate = self.root / 'candidate-news.json'
        status = self.root / 'status.json'
        candidate.write_text(json.dumps(self.data), encoding='utf-8')
        status.write_text(json.dumps(self.status), encoding='utf-8')
        os.utime(candidate, ns=(1000,1000))
        os.utime(status, ns=(2000,2000))

    def test_only_published_public_fields_and_stable_etag(self):
        body, tag = fast_feed.read_public(self.root)
        self.assertNotIn('not-public', body.decode())
        self.assertEqual(json.loads(body)['items'], [])
        self.assertEqual(tag, fast_feed.read_public(self.root)[1])

    def test_new_candidate_with_old_success_is_blocked(self):
        os.utime(self.root / 'candidate-news.json', ns=(3000,3000))
        with self.assertRaises(ValueError):
            fast_feed.read_public(self.root)

    def test_shadow_failure_validation_and_revision_mismatch_blocked(self):
        for overrides in [{'mode':'shadow'}, {'published':False}, {'validation_issues':['bad data']}, {'source_revision':'b'*40}, {'source_revision':None}]:
            with self.subTest(overrides=overrides):
                self.status = {'mode':'publish','published':True,'validation_issues':[],'source_revision':'a'*40} | overrides
                self.write()
                with self.assertRaises(ValueError):
                    fast_feed.read_public(self.root)

    def test_partial_json_not_served(self):
        (self.root / 'candidate-news.json').write_text('{partial', encoding='utf-8')
        with self.assertRaises(ValueError):
            fast_feed.read_public(self.root)


if __name__ == '__main__':
    unittest.main()
