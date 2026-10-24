import unittest

from goms_to_actr import ModelError, loads


class TextInputTests(unittest.TestCase):
    def test_json_source(self):
        model = loads('{"version":1,"name":"hello","entry":"greet",'
                      '"goals":{"greet":[{"name":"default","steps":[]}]}}')
        self.assertEqual(model['name'], 'hello')

    def test_ngomsl_source(self):
        model = loads('Model: hello.\nInitial goal: greet.\nMethod for goal: greet\n'
                      'Step 1. Return with goal accomplished.', format='ngomsl')
        self.assertEqual(model['entry'], 'greet')

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ModelError, 'duplicate JSON key'):
            loads('{"version":1,"version":2}')

    def test_unsupported_format_rejected(self):
        with self.assertRaisesRegex(ModelError, 'unsupported input format'):
            loads('source', format='yaml')
