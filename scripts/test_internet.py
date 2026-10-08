"""HTTPS proxy/authentication checks without publishing a tunnel or using live data."""
import contextlib
import io
import os
import queue
import re
import sys
import socket
import threading
import unittest
import tempfile
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import serve_internet
import serve_native
from mysql57.app import create_app, password_hash
from mysql57.models import db, User
from waitress.server import create_server

HOST = 'test-catalog.trycloudflare.com'


class TunnelTests(unittest.TestCase):
    def test_extract_only_official_https_hostname(self):
        messages = queue.Queue()
        messages.put('Visit https://' + HOST)
        process = Mock()
        process.poll.return_value = None
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(serve_internet.wait_for_url(process, messages), HOST)
        for value in ['https://test.trycloudflare.com.evil.example', 'http://' + HOST, 'https://evil.example']:
            self.assertIsNone(serve_internet.TUNNEL_URL.search(value))

    def test_tunnel_stops_before_address(self):
        messages = queue.Queue()
        messages.put(None)
        with self.assertRaisesRegex(ValueError, 'tunnel stopped'):
            serve_internet.wait_for_url(Mock(), messages)

    def test_timeout_and_cleanup(self):
        with self.assertRaisesRegex(ValueError, '60 seconds'):
            serve_internet.wait_for_url(Mock(), queue.Queue(), timeout=0)
        process = Mock()
        process.poll.return_value = None
        serve_internet.stop_process(process)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)


class HTTPSAuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app({'SECRET_KEY': 'https-test-secret-'*4, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'SQLALCHEMY_ENGINE_OPTIONS': {}, 'SESSION_COOKIE_SECURE': True, 'REQUIRE_HTTPS': True, 'TRUSTED_HOSTS': [HOST]})
        with cls.app.app_context():
            db.create_all()
            db.session.add(User(username='reader', password_hash=password_hash('Reader-test-123!'), active=True))
            db.session.commit()
        cls.server = create_server(cls.app, host='127.0.0.1', port=0, threads=2,
            trusted_proxy='127.0.0.1', trusted_proxy_headers={'x-forwarded-proto'}, clear_untrusted_proxy_headers=True)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.server.task_dispatcher.shutdown()

    def request(self, path, method='GET', data=None, extra=None):
        headers = {'Host': HOST, 'X-Forwarded-Proto': 'https'}
        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers.update(extra or {})
        connection = HTTPConnection('127.0.0.1', int(self.server.effective_port), timeout=5)
        connection.request(method, path, body=urlencode(data) if data is not None else None, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read().decode()
        connection.close()
        return result

    def test_https_login_and_session(self):
        status, headers, html = self.request('/accounts/login/')
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';')[0]
        self.assertIn('Secure', headers['Set-Cookie'])
        csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
        status, headers, _ = self.request('/accounts/login/', 'POST', {'username':'reader', 'password':'Reader-test-123!', 'csrf_token':csrf},
            {'Cookie':cookie, 'Referer':'https://'+HOST+'/accounts/login/'})
        self.assertEqual(status, 302)
        self.assertIn('Secure', headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request('/', extra={'Cookie':cookie})[0], 200)

    def test_anonymous_cannot_read_catalog(self):
        self.assertEqual(self.request('/')[0], 302)

    def test_missing_csrf_rejected(self):
        self.assertEqual(self.request('/accounts/login/', 'POST', {'username':'reader', 'password':'Reader-test-123!'})[0], 400)

    def test_untrusted_host_rejected(self):
        self.assertEqual(self.request('/accounts/login/', extra={'Host':'evil.example'})[0], 400)

    def test_http_redirects_to_https(self):
        status, headers, _ = self.request('/accounts/login/', extra={'X-Forwarded-Proto':'http'})
        self.assertEqual(status, 308)
        self.assertEqual(headers['Location'], 'https://'+HOST+'/accounts/login/')

    def test_public_launcher_binds_loopback_and_trusts_only_local_proxy(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, '.env').touch()
            with patch.object(serve_native, 'ROOT', Path(directory)), patch('dotenv.load_dotenv'), patch.dict(os.environ), \
                patch.object(sys, 'argv', ['serve_native.py', '--public-host', HOST, '--no-browser', '--port', str(port)]), \
                patch.object(serve_native, 'backend_for', return_value=('mysql57', '5.7.31')), \
                patch('mysql57.app.create_app', return_value=self.app) as factory, patch('waitress.serve') as serve, \
                contextlib.redirect_stdout(io.StringIO()):
                serve_native.main()
                self.assertEqual(serve.call_args.kwargs['host'], '127.0.0.1')
                self.assertEqual(serve.call_args.kwargs['trusted_proxy'], '127.0.0.1')
                self.assertEqual(serve.call_args.kwargs['trusted_proxy_headers'], {'x-forwarded-proto'})
                self.assertTrue(factory.call_args.args[0]['SESSION_COOKIE_SECURE'])
                self.assertTrue(factory.call_args.args[0]['REQUIRE_HTTPS'])
                self.assertEqual(factory.call_args.args[0]['TRUSTED_HOSTS'], [HOST])
                self.assertEqual(os.environ['DJANGO_HTTPS'], 'true')


if __name__ == '__main__':
    unittest.main()
