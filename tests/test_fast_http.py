from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import rt_serve


class FastHTTPTests(unittest.TestCase):
    def test_feed_conditional_response_fallback_and_private_routes(self):
        server = ThreadingHTTPServer(('127.0.0.1',0), rt_serve.H)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.object(rt_serve.fast_feed, 'read_public', return_value=(b'{"updated":123,"items":[]}', '"test"')):
                with urllib.request.urlopen(base+'/news') as response:
                    self.assertEqual(json.load(response)['updated'],123)
                    self.assertEqual(response.headers['Cache-Control'],'no-store')
                with urllib.request.urlopen(base+'/news?tag=%22test%22') as response:
                    self.assertEqual(response.status,204)
                    self.assertEqual(response.read(),b'')
            with patch.object(rt_serve.fast_feed, 'read_public', side_effect=ValueError('not published')):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base+'/news')
                self.assertEqual(error.exception.code,503)
            for route in ['/api/ops','/status.json','/candidate-news.json','/visitors.sqlite3']:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base+route)
                self.assertEqual(error.exception.code,404)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
