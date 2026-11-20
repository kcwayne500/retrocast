"""Integration tests for RetroCast's zero-dependency local HTTP server."""
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.parse
import urllib.request

_TMP = tempfile.TemporaryDirectory()
os.environ['RETROCAST_MEDIA_DIR'] = _TMP.name
os.environ['RETROCAST_RF_ENABLED'] = '0'
import app as retro  # noqa: E402


class RetrocastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = retro.create_server('127.0.0.1', 0)
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=4)
        _TMP.cleanup()

    def setUp(self):
        retro.stop_process()
        with retro._lock:
            retro._error = ''

    def tearDown(self):
        retro.stop_process()
        for p in Path(_TMP.name).iterdir():
            if p.is_file():
                p.unlink()

    def req(self, route, method='GET', data=None, headers=None):
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            headers = {'Content-Type':'application/json', **(headers or {})}
        req = urllib.request.Request(self.base+route, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read()
                return resp.status, json.loads(body) if 'application/json' in resp.headers.get('Content-Type','') else body, resp.headers
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read()), e.headers

    def test_health_and_index(self):
        code, obj, _ = self.req('/api/health')
        self.assertEqual(code, 200)
        self.assertEqual(obj['service'], 'retrocast')
        self.assertIn(b'RETROCAST', self.req('/')[1])
        self.assertEqual(self.req('/static/app.js')[0], 200)
        self.assertEqual(self.req('/static/style.css')[0], 200)

    def test_upload_list_and_preview(self):
        code, obj, _ = self.req('/api/upload?filename=demo.mp4','POST',b'not real video', {'Content-Type':'application/octet-stream'})
        self.assertEqual(code,201)
        name=obj['item']['name']
        self.assertEqual(len(self.req('/api/media')[1]['items']),1)
        self.assertEqual(self.req('/media/'+name)[0],200)
        code, body, headers = self.req('/media/'+name,headers={'Range':'bytes=0-2'})
        self.assertEqual(code,206)
        self.assertEqual(body,b'not')
        self.assertEqual(headers['Content-Range'],'bytes 0-2/14')
        self.assertEqual(self.req('/api/play','POST',{'mode':'preview','source':'file','name':name,'channel':'3'})[0],200)
        self.assertEqual(self.req('/api/status')[1]['active']['name'], name)
        self.assertEqual(self.req('/api/media/'+name,'DELETE')[0],409)
        self.assertEqual(self.req('/api/stop','POST',{})[0],200)
        self.assertEqual(self.req('/api/media/'+name,'DELETE')[0],200)

    def test_testcard_preview(self):
        code, obj, _ = self.req('/api/play','POST',{'mode':'preview','source':'test','channel':'4'})
        self.assertEqual(code,200)
        self.assertEqual(obj['active']['frequency_hz'],67_250_000)
        self.assertEqual(obj['active']['name'],'test:colourbars')

    def test_rf_locked_by_default(self):
        code, _, _ = self.req('/api/play','POST',{'mode':'rf','source':'test','bench_confirmed':True})
        self.assertEqual(code,403)

    def test_bad_paths_rejected(self):
        for name in ('../../etc/passwd.mp4','/tmp/video.mp4','a\\b.mp4','file.exe'):
            self.assertEqual(self.req('/api/play','POST',{'mode':'preview','source':'file','name':name})[0],400)
        self.assertEqual(self.req('/media/../app.py')[0],404)
        self.assertEqual(self.req('/api/upload?filename=run.exe','POST',b'evil')[0],400)

    def test_youtube_url_validation(self):
        self.assertTrue(retro.valid_youtube_url('https://www.youtube.com/watch?v=123'))
        self.assertTrue(retro.valid_youtube_url('https://youtu.be/123'))
        self.assertFalse(retro.valid_youtube_url('http://youtube.com/watch?v=x'))
        self.assertFalse(retro.valid_youtube_url('https://youtube.com.evil.net/watch?v=x'))
        self.assertFalse(retro.valid_youtube_url('https://127.0.0.1/'))
        self.assertFalse(retro.valid_youtube_url('https://www.youtube.com/playlist?list=abc'))

    @mock.patch.object(retro, 'TX_ENABLED', True)
    @mock.patch.object(retro, 'binary_found', return_value=True)
    @mock.patch.object(retro.subprocess, 'Popen')
    def test_hacktv_arguments(self, mock_popen, _binary):
        proc=mock_popen.return_value
        proc.poll.return_value=None
        proc.stdout=io.StringIO('')
        code,obj,_=self.req('/api/play','POST',{'mode':'rf','source':'test','channel':'3','repeat':True,'bench_confirmed':True})
        self.assertEqual(code,200)
        args=mock_popen.call_args.args[0]
        self.assertEqual(args[:9],['hacktv','-o','hackrf','-m','m','-s','13500000','-f','61250000'])
        self.assertIn('-g',args)
        self.assertNotIn('-a',args)
        self.assertIn('test:colourbars',args)
        # Avoid calling os.killpg against fake Popen process.
        with retro._lock:
            retro._process=None
            retro._active=None

if __name__=='__main__':
    unittest.main()
