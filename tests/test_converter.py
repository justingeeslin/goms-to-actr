import contextlib
import copy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

from goms_to_actr import ModelError, compile_model, load, simulate, validate
from goms_to_actr.cli import main

ROOT = Path(__file__).resolve().parents[1]


def small(steps=None):
    return {'version': 1, 'name': 'test', 'entry': 'main', 'state': {'x': 'a'},
            'goals': {'main': [{'name': 'default', 'steps': steps or []}]}}


class ConverterTests(unittest.TestCase):
    def test_example(self):
        model = load(ROOT / 'examples/write-message.json')
        result = simulate(model)
        self.assertEqual(result['status'], 'done')
        self.assertEqual(result['state']['sent'], 'yes')
        keys = [e['key'] for e in result['events'] if e.get('op') == 'press_key']
        self.assertEqual(keys, list('hello') + ['space'] + list('world') + ['return'])
        lisp = compile_model(model)
        self.assertIn('(install-device \'("motor" "keyboard"))', lisp)
        self.assertEqual(lisp.count('cmd press-key'), 12)
        self.assertEqual(lisp.count('?manual>'), 24)
        self.assertNotIn('start-hand-at-keyboard', lisp)

    def test_fallback(self):
        model = load(ROOT / 'examples/write-message.json')
        model['state']['mode'] = 'speech'
        result = simulate(model)
        self.assertIn({'op': 'speak', 'text': 'hello world'}, result['events'])
        self.assertFalse(any(e.get('op') == 'type_text' for e in result['events']))

    def test_repeated_subgoal_returns_to_distinct_continuations(self):
        model = small([{'goal': 'child'}, {'op': 'set', 'values': {'x': 'b'}}, {'goal': 'child'}])
        model['goals']['child'] = [{'name': 'one', 'steps': [{'op': 'emit', 'text': 'child'}]}]
        lisp = compile_model(model)
        self.assertEqual(lisp.count('(format t'), 2)
        destinations = re.findall(r'pc (\S+)\n    !eval! \(format', lisp)
        self.assertEqual(len(set(destinations)), 2)
        self.assertEqual(sum(e.get('op') == 'emit' for e in simulate(model)['events']), 2)

    def test_first_matching_method_wins(self):
        model = small()
        model['goals']['main'] = [
            {'name': 'first', 'when': {'x': 'a'}, 'steps': [{'op': 'set', 'values': {'x': 'first'}}]},
            {'name': 'second', 'when': {'x': 'a'}, 'steps': [{'op': 'set', 'values': {'x': 'second'}}]}]
        self.assertEqual(simulate(model)['state']['x'], 'first')
        output = compile_model(model)
        self.assertIn('!eval! (not (and (equal =v0 "a")))', output)
        self.assertIn('pc failed', output)

    def test_no_applicable_method_fails(self):
        model = small()
        model['goals']['main'][0]['when'] = {'x': 'z'}
        self.assertEqual(simulate(model)['status'], 'failed')
        self.assertIn('pc failed', compile_model(model))

    def test_speech_waits(self):
        output = compile_model(small([{'op': 'speak', 'text': 'Hi'}]))
        self.assertEqual(output.count('?vocal>'), 2)
        self.assertIn('cmd speak', output)
        self.assertNotIn('install-device', output)

    def test_safe_lisp_string(self):
        text = '" ) (quit) ; \\ ~a'
        output = compile_model(small([{'op': 'emit', 'text': text}]))
        self.assertIn('"\\" ) (quit) ; \\\\ ~a"', output)
        self.assertIn('(format t "~&~a~%"', output)

    def test_numeric_guards(self):
        model = small()
        model['state']['x'] = 1
        model['goals']['main'][0]['when'] = {'x': 1.0}
        self.assertEqual(simulate(model)['status'], 'done')
        self.assertIn('(equalp =v0 1.0d0)', compile_model(model))

    def test_invalid_models(self):
        base = small()
        variants = []
        for key, value in [('version', True), ('name', '(quit)'), ('entry', 'missing'), ('state', {'x': None})]:
            m = copy.deepcopy(base)
            m[key] = value
            variants.append(m)
        for step in [{'goal': 'missing'}, {'goal': 'main'}, {'op': 'look'},
                     {'op': 'set', 'values': {'missing': 'a'}},
                     {'op': 'think', 'text': 'ignored'}, {'op': 'type_text', 'text': 'UPPER'},
                     {'op': 'press_key', 'key': 'unknown'}, {'op': 'emit', 'text': '\n'}]:
            variants.append(small([step]))
        for model in variants:
            with self.subTest(model=model), self.assertRaises(ModelError):
                compile_model(model)

    def test_duplicate_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'
            path.write_text('{"version":1,"version":1}')
            with self.assertRaisesRegex(ModelError, 'duplicate'):
                load(path)
        model = small()
        model['typo'] = 1
        with self.assertRaisesRegex(ModelError, 'unknown fields'):
            validate(model)

    def test_resource_limits(self):
        model = small([{'op': 'think'}] * 5)
        with self.assertRaisesRegex(ModelError, 'exceeds'):
            compile_model(model, max_states=3)
        with self.assertRaisesRegex(ModelError, 'exceeds'):
            simulate(model, max_steps=3)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'in.json', Path(tmp) / 'out.lisp'
            source.write_text(json.dumps(small()))
            self.assertEqual(main(['compile', str(source), '-o', str(target)]), 0)
            self.assertIn('define-model goms-test', target.read_text())
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(['simulate', str(source)]), 0)
            self.assertEqual(json.loads(stdout.getvalue())['status'], 'done')
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(main(['compile', str(source) + '.missing']), 2)
            self.assertIn('error:', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
