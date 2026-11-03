"""Exercise the production settings and static files used by Heroku."""
import json
import os
import re
import runpy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from .examples import EXAMPLES


def load_settings(**environment):
    with patch.dict(os.environ, environment, clear=True):
        return runpy.run_path(str(Path(__file__).with_name('settings.py')))


class HerokuDeploymentTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        static_directory = TemporaryDirectory()
        cls.addClassCleanup(static_directory.cleanup)
        production = load_settings(
            DJANGO_SECRET_KEY='production-test-secret-key-with-at-least-fifty-characters',
            DJANGO_ALLOWED_HOSTS='deployment-check.example.com',
            DYNO='web.1',
        )
        production['STATIC_ROOT'] = static_directory.name
        settings = override_settings(**{
            key: value for key, value in production.items()
            if key.isupper() and key != 'DATABASES'
        })
        settings.enable()
        cls.addClassCleanup(settings.disable)
        call_command('collectstatic', interactive=False, verbosity=0, stdout=StringIO())

    def request(self, path='/', **kwargs):
        return self.client.get(
            path, HTTP_HOST='deployment-check.example.com', **kwargs)

    def test_production_startup_requires_a_secret(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'Set DJANGO_SECRET_KEY'):
            load_settings(DYNO='web.1')

    def test_http_redirects_and_forwarded_https_does_not_loop(self):
        response = self.request()
        self.assertRedirects(
            response, 'https://deployment-check.example.com/',
            status_code=301, fetch_redirect_response=False)
        response = self.request(HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertIn('max-age=31536000', response['Strict-Transport-Security'])

    def test_unconfigured_host_is_rejected(self):
        with self.assertLogs('django.security.DisallowedHost', level='ERROR'):
            response = self.client.get(
                '/', HTTP_HOST='unexpected.example.com', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 400)

    def test_collected_fingerprinted_assets_are_served_without_debug(self):
        response = self.request(HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        assets = re.findall(
            r'(?:href|src)="(/static/converter/[^"]+)"', response.content.decode())
        self.assertEqual(len(assets), 2)
        for asset in assets:
            with self.subTest(asset=asset):
                self.assertRegex(asset, r'\.[0-9a-f]{12}\.(css|js)$')
                response = self.request(
                    asset, HTTP_X_FORWARDED_PROTO='https', HTTP_ACCEPT_ENCODING='gzip')
                self.assertEqual(response.status_code, 200)
                self.assertIn('immutable', response['Cache-Control'])
                self.assertEqual(response['Content-Encoding'], 'gzip')
                response.close()

    def test_conversion_works_behind_the_https_router(self):
        for source_format, source in EXAMPLES.items():
            with self.subTest(format=source_format):
                response = self.client.post(
                    '/api/convert/',
                    data=json.dumps({'format': source_format, 'source': source}),
                    content_type='application/json',
                    HTTP_HOST='deployment-check.example.com',
                    HTTP_X_FORWARDED_PROTO='https',
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn('(define-model goms-send-message', response.json()['lisp'])
