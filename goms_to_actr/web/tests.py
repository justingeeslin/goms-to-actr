import json
from pathlib import Path

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from goms_to_actr import compile_model, load, loads
from .examples import EXAMPLES


@override_settings(STORAGES={
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ConversionTests(SimpleTestCase):
    def post(self, payload):
        return self.client.post(reverse('convert'), data=json.dumps(payload), content_type='application/json')

    def test_index_loads_editable_example_and_api_url(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Model: send-message.')
        self.assertContains(response, 'action="/api/convert/"')
        self.assertContains(response, '/static/converter/app.js')
        self.assertContains(response, 'id="examples-data"')

    def test_both_formats_match_the_library(self):
        for source_format, source in EXAMPLES.items():
            with self.subTest(format=source_format):
                response = self.post({'format': source_format, 'source': source})
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data['format'], source_format)
                self.assertEqual(data['name'], 'send-message')
                self.assertEqual(data['lisp'], compile_model(loads(source, format=source_format)))
                self.assertIn('no-store', response['Cache-Control'])

    def test_all_repository_examples_match_file_conversion(self):
        root = Path(__file__).resolve().parents[2] / 'examples'
        for pattern, source_format in [('*.json', 'json'), ('*.ngomsl', 'ngomsl')]:
            for path in root.rglob(pattern):
                with self.subTest(path=path):
                    response = self.post({'format': source_format, 'source': path.read_text(encoding='utf-8')})
                    self.assertEqual(response.status_code, 200, response.content)
                    self.assertEqual(response.json()['lisp'], compile_model(load(path)))

    def test_public_stateless_api_needs_no_csrf_cookie(self):
        response = Client(enforce_csrf_checks=True).post(
            reverse('convert'), data=json.dumps({'format': 'ngomsl', 'source': EXAMPLES['ngomsl']}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.cookies)

    def test_only_post_is_supported(self):
        for method in ['get', 'put', 'delete', 'patch', 'head', 'options']:
            with self.subTest(method=method):
                response = getattr(self.client, method)(reverse('convert'))
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response['Allow'], 'POST')
                self.assertEqual(response['Content-Type'], 'application/json')

    def test_wrong_media_type(self):
        response = self.client.post(reverse('convert'), data='{}', content_type='text/plain')
        self.assertEqual(response.status_code, 415)
        self.assertIn('error', response.json())

    def test_invalid_request_json(self):
        for body in [b'{', b'\xff', b'{"format":"json","format":"ngomsl","source":"x"}', b'[' * 2000]:
            with self.subTest(body=body[:40]):
                response = self.client.post(reverse('convert'), data=body, content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())

    def test_invalid_payload(self):
        for payload in [None, [], {}, {'source': 'x'},
                        {'format': 'yaml', 'source': 'x'},
                        {'format': [], 'source': 'x'},
                        {'format': 'json', 'source': {}},
                        {'format': 'json', 'source': ''},
                        {'format': 'json', 'source': '   '},
                        {'format': 'json', 'source': '{}', 'max_states': 999999}]:
            with self.subTest(payload=payload):
                response = self.post(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())

    def test_invalid_source_has_actionable_error(self):
        cases = [
            ('json', '{', 'invalid JSON'),
            ('json', '{"version":1,"version":1}', 'duplicate JSON key'),
            ('json', '{}', 'missing fields'),
            ('json', '[' * 2000, 'invalid JSON'),
            ('ngomsl', 'Model: hello.', 'missing initial goal'),
            ('ngomsl', EXAMPLES['ngomsl'].replace('Think.', 'Teleport.'), 'unsupported'),
        ]
        for source_format, source, message in cases:
            with self.subTest(format=source_format, source=source[:50]):
                response = self.post({'format': source_format, 'source': source})
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, response.json()['error'])

    def test_request_limit_returns_json(self):
        response = self.post({'format': 'ngomsl', 'source': 'a' * (256 * 1024)})
        self.assertEqual(response.status_code, 413)
        self.assertIn('error', response.json())

    @override_settings(CONVERSION_MAX_STATES=1)
    def test_expansion_limit_cannot_be_overridden_by_clients(self):
        response = self.post({'format': 'ngomsl', 'source': EXAMPLES['ngomsl']})
        self.assertEqual(response.status_code, 400)
        self.assertIn('expanded model exceeds 1', response.json()['error'])

    def test_source_strings_remain_literal_output(self):
        model = loads(EXAMPLES['json'])
        literal = '<script>alert("hello")</script>'
        model['goals']['send-message'][0]['steps'] = [{'op': 'emit', 'text': literal}]
        response = self.post({'format': 'json', 'source': json.dumps(model)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['lisp'], compile_model(model))

    def test_small_source_cannot_amplify_into_unbounded_output(self):
        model = {
            'version': 1, 'name': 'large', 'entry': 'main',
            'goals': {
                'main': [{'name': 'default', 'steps': [{'goal': 'child'}] * 100}],
                'child': [{'name': 'default', 'steps': [{'op': 'emit', 'text': 'x' * 30000}]}],
            },
        }
        source = json.dumps(model)
        self.assertLess(len(source), 256 * 1024)
        response = self.post({'format': 'json', 'source': source})
        self.assertEqual(response.status_code, 400)
        self.assertIn('generated Lisp exceeds', response.json()['error'])
