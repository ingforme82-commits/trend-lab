import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import visitor_stats as stats
import rt_serve

NOW = 1794838400


class VisitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'visitors.sqlite3'

    def tearDown(self):
        self.tmp.cleanup()

    def beat(self, browser='a', page='b', at=NOW):
        stats.heartbeat(self.db, {'browser': browser * 32, 'page': page * 32}, at)

    def test_missing_and_corrupt_are_not_zero(self):
        self.assertIsNone(stats.summary(self.db)['online'])
        self.db.write_text('bad database')
        self.assertFalse(stats.summary(self.db)['available'])

    def test_heartbeats_do_not_inflate_visits_or_views(self):
        self.beat()
        self.beat(at=NOW + 30)
        row = stats.summary(self.db, NOW + 40)
        self.assertEqual(row['online'], 1)
        self.assertEqual(row['today'], {'day': '2026-11-16', 'browsers': 1, 'pageviews': 1})

    def test_tabs_deduplicate_browsers_and_timeout(self):
        self.beat()
        self.beat(page='c', at=NOW + 10)
        self.beat(browser='d', page='e', at=NOW + 10)
        row = stats.summary(self.db, NOW + 20)
        self.assertEqual(row['online'], 2)
        self.assertEqual(row['today']['pageviews'], 3)
        self.assertEqual(stats.summary(self.db, NOW + 131)['online'], 0)

    def test_kst_day_boundary_and_cumulative_semantics(self):
        self.beat(at=1794831599)  # before next test day, use explicit UTC conversion below
        from datetime import datetime
        t = datetime.fromisoformat('2026-11-16T23:59:59+09:00').timestamp()
        self.beat(at=t)
        self.beat(at=t + 2)
        row = stats.summary(self.db, t + 2)
        self.assertEqual(row['today']['day'], '2026-11-17')
        self.assertEqual(row['total_visits'], 2)
        self.assertFalse(row['unique_people_verified'])

    def test_extra_personal_fields_rejected(self):
        with self.assertRaises(ValueError):
            stats.heartbeat(self.db, {'browser': 'a' * 32, 'page': 'b' * 32, 'email': 'private@example.com'}, NOW)
        self.beat()
        data = json.dumps(stats.summary(self.db, NOW))
        self.assertNotIn('a' * 32, data)
        self.assertNotIn('private', data)

    def test_public_route_only_accepts_origin_and_shape(self):
        previous = rt_serve.VISITORS
        rt_serve.VISITORS = self.db
        server = ThreadingHTTPServer(('127.0.0.1', 0), rt_serve.H)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            for origin, expected in [('https://other.example', 403), (stats.ORIGIN, 204)]:
                request = urllib.request.Request(url + '/presence', data=json.dumps({'browser':'a'*32,'page':'b'*32}).encode(), headers={'Origin':origin, 'Content-Type':'text/plain'})
                try:
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(response.status, expected)
                except urllib.error.HTTPError as error:
                    self.assertEqual(error.code, expected)
            for path in ['/presence', '/visitors.sqlite3', '/api/ops', '/stats']:
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(url + path)
                self.assertEqual(caught.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
            rt_serve.VISITORS = previous


if __name__ == '__main__':
    unittest.main()
