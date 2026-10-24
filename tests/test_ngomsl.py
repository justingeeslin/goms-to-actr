"""NGOMSL parsing, CLI integration, and behavior of translated examples."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from goms_to_actr import (ModelError, compile_model, load, load_ngomsl,
                          parse_ngomsl, simulate)
from goms_to_actr.cli import main
from test_generated_flow import run_generated


ROOT = Path(__file__).resolve().parents[1]


def program(body='Step 1. Return with goal accomplished.', state=''):
    return ('Model: test.\nInitial goal: main.\n' + state +
            '\nMethod for goal: main\n' + body + '\n')


class NgomslParserTests(unittest.TestCase):
    def test_empty_method_and_optional_state(self):
        model = parse_ngomsl(program())
        self.assertEqual(model['goals']['main'][0]['steps'], [])
        self.assertEqual(simulate(model)['status'], 'done')
        self.assertEqual(run_generated(model)[0]['pc'], 'done')

    def test_keywords_and_goal_phrases_are_case_insensitive(self):
        model = parse_ngomsl('''MODEL: Friendly Example.
INITIAL GOAL: Say Hello.
METHOD FOR GOAL: say hello.
  STEP 1. SPEAK "Hello".
  STEP 2. RETURN WITH GOAL ACCOMPLISHED.
''')
        self.assertEqual(model['name'], 'friendly-example')
        self.assertEqual(model['entry'], 'say-hello')
        self.assertIn({'op': 'speak', 'text': 'Hello'}, simulate(model)['events'])

    def test_comments_escapes_and_language_words_inside_literals(self):
        text = '# and then accomplish goal: other. " ) (quit) ; \\ ~a'
        literal = json.dumps(text)
        model = parse_ngomsl(program(
            f'Step 1. Set x to {literal}. # comment\n'
            f'Step 2. Emit {literal}.\n'
            'Step 3. Accomplish goal: choose.\n'
            'Step 4. Return with goal accomplished.',
            'Initial state:\n x = "initial".') +
            'Selection rule set for goal: choose\n'
            f'If x is {literal}, then\n accomplish goal: finish.\n'
            'Return with goal accomplished.\n'
            'Method for goal: finish\nStep 1. Return with goal accomplished.\n')
        self.assertEqual(simulate(model)['state']['x'], text)
        self.assertEqual(run_generated(model)[1], [('emit', text)])

    def test_numbers_and_atomic_multi_slot_assignments(self):
        model = parse_ngomsl(program(
            'Step 1. Set x to -1.5e2 and y to 2.5.\n'
            'Step 2. Return with goal accomplished.',
            'Initial state:\nx = 0 and y = 1.'))
        self.assertEqual(simulate(model)['state'], {'x': -150, 'y': 2.5})

    def test_selection_order_numeric_equality_and_no_reselection(self):
        source = '''Model: selection.
Initial goal: choose.
Initial state:
  x = 1.
Selection rule set for goal: choose
  If x is 1.0, then accomplish goal: first.
  If x is 1, then accomplish goal: second.
  Otherwise accomplish goal: second.
  Return with goal accomplished.
Method for goal: first
  Step 1. Set x to 2.
  Step 2. Emit "first".
  Step 3. Return with goal accomplished.
Method for goal: second
  Step 1. Emit "second".
  Step 2. Return with goal accomplished.
'''
        model = parse_ngomsl(source)
        goal, events = run_generated(model)
        self.assertEqual(goal['s-x'], 2)
        self.assertEqual(events, [('emit', 'first')])
        self.assertEqual(simulate(model)['state']['x'], 2)

    def test_repeated_subgoals_return_to_their_callers(self):
        model = parse_ngomsl(program(
            'Step 1. Accomplish goal: child.\n'
            'Step 2. Emit "between".\n'
            'Step 3. Accomplish goal: child.\n'
            'Step 4. Return with goal accomplished.') +
            'Method for goal: child\nStep 1. Emit "child".\n'
            'Step 2. Return with goal accomplished.\n')
        self.assertEqual(run_generated(model)[1],
                         [('emit', 'child'), ('emit', 'between'), ('emit', 'child')])

    def test_failed_selection_does_not_resume_parent(self):
        model = parse_ngomsl(program(
            'Step 1. Accomplish goal: child.\n'
            'Step 2. Emit "unreachable".\n'
            'Step 3. Return with goal accomplished.',
            'Initial state:\nx = 1.') +
            'Selection rule set for goal: child\n'
            'If x is 2, then accomplish goal: finish.\n'
            'Return with goal accomplished.\n'
            'Method for goal: finish\nStep 1. Return with goal accomplished.\n')
        self.assertEqual(simulate(model)['status'], 'failed')
        goal, events = run_generated(model)
        self.assertEqual(goal['pc'], 'failed')
        self.assertEqual(events, [])

    def test_syntax_errors_report_source_and_line(self):
        variants = [
            (program('Step 2. Think.'), 'expected Step 1'),
            (program('Step 1. Think'), 'end with a period'),
            (program('Step 1. Think.'), 'missing Return'),
            (program('Step 1. Look at the screen.'), 'unsupported NGOMSL operator'),
            (program('Step 1. Goto Step 1.'), 'unsupported NGOMSL operator'),
            (program('Step 1. Decide: If x is 1, then Think.'), 'unsupported NGOMSL operator'),
            (program('Step 1. Emit "unclosed.'), 'unterminated string'),
            (program('Step 1. Emit "ok" extra.'), 'one quoted string'),
            (program() + 'Step 2. Think.\n', 'outside a block'),
            (program() + 'Method for goal: main\n', 'duplicate goal'),
            (program().replace('Initial goal: main.', 'Initial goal: absent.'), 'unknown goal'),
            (program().replace('Model: test.\n', ''), 'missing model'),
            (program().replace('Initial goal: main.\n', ''), 'missing initial goal'),
            ('Model: a.\nModel: b.\n', 'duplicate model'),
            (program() + 'Initial state:\n', 'metadata must precede'),
            (program('Step 1. Think.\nMethod for goal: other'), 'previous block'),
            (program('Step 1. Accomplish goal: unknown.\n'
                     'Step 2. Return with goal accomplished.'), 'unknown goal'),
        ]
        for source, message in variants:
            with self.subTest(message=message), self.assertRaises(ModelError) as error:
                parse_ngomsl(source, source='bad.ngomsl')
            self.assertRegex(str(error.exception), r'^bad\.ngomsl:\d+:')
            self.assertIn(message, str(error.exception))

    def test_rejects_invalid_state_and_assignments(self):
        for value in ('true', 'null', 'NaN', 'Infinity', '1e999', '[]', '{}', '"\\n"', '"\\ud800"'):
            with self.subTest(value=value), self.assertRaises(ModelError):
                parse_ngomsl(program(state='Initial state:\nx = ' + value + '.'))
        for state in ('Initial state:\nx = 1.\nx = 2.',
                      'Initial state:\nx = 1 and x = 2.',
                      'Initial state: x = 1.',
                      'Initial state:\nx = 1 trailing.'):
            with self.subTest(state=state), self.assertRaises(ModelError):
                parse_ngomsl(program(state=state))
        for step in ('Set x to 1', 'Set x to 1 and x to 2', 'Set x to 1 trailing'):
            with self.subTest(step=step), self.assertRaises(ModelError):
                parse_ngomsl(program('Step 1. ' + step + '.\n'
                                     'Step 2. Return with goal accomplished.'))

    def test_rejects_invalid_selection_rules(self):
        prefix = 'Model: test.\nInitial goal: choose.\nInitial state:\nx = 1.\n'
        suffix = '\nReturn with goal accomplished.\n'
        for rules in ('', 'If x is 1, then Think.',
                      'If missing is 1, then accomplish goal: choose.',
                      'Otherwise accomplish goal: choose.\nIf x is 1, then accomplish goal: choose.',
                      'If x is 1 and x is 2, then accomplish goal: choose.'):
            with self.subTest(rules=rules), self.assertRaises(ModelError):
                parse_ngomsl(prefix + 'Selection rule set for goal: choose\n' + rules + suffix)

    def test_shared_validation_and_resource_limits(self):
        for step in ('Press key "unknown"', 'Type text "UPPER"', 'Speak ""',
                     'Accomplish goal: main'):
            with self.subTest(step=step), self.assertRaises(ModelError):
                parse_ngomsl(program('Step 1. ' + step + '.\n'
                                     'Step 2. Return with goal accomplished.'))
        model = parse_ngomsl(program('Step 1. Think.\nStep 2. Return with goal accomplished.'))
        with self.assertRaisesRegex(ModelError, 'exceeds'):
            compile_model(model, max_states=1)
        with self.assertRaisesRegex(ModelError, 'exceeds'):
            simulate(model, max_steps=1)

    def test_loading_and_cli_format_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'model.txt', Path(tmp) / 'model.lisp'
            source.write_text(program(), encoding='utf-8')
            self.assertEqual(load_ngomsl(source), load(source, format='ngomsl'))
            with self.assertRaises(ModelError):
                load(source)
            self.assertEqual(main(['compile', str(source), '--format', 'ngomsl', '-o', str(target)]), 0)
            self.assertEqual(target.read_text(), compile_model(load_ngomsl(source)))
            for command in ('validate', 'simulate'):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main([command, str(source), '--format', 'ngomsl']), 0)
                self.assertTrue(output.getvalue())
            uppercase = Path(tmp) / 'model.NGOMSL'
            uppercase.write_text(program(), encoding='utf-8')
            self.assertEqual(load(uppercase), load_ngomsl(source))
            with self.assertRaisesRegex(ModelError, 'unsupported input format'):
                load(source, format='unknown')
            with contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as exit_error:
                    main(['compile', str(uppercase), '-o', str(uppercase)])
            self.assertEqual(exit_error.exception.code, 2)
            self.assertIn('output must differ from input', error.getvalue())

    def test_cli_bad_ngomsl_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'bad.ngomsl', Path(tmp) / 'out.lisp'
            source.write_text(program('Step 1. Unsupported.'), encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(main(['compile', str(source), '-o', str(target)]), 2)
            self.assertIn('bad.ngomsl:5:', error.getvalue())
            self.assertFalse(target.exists())


class NgomslExampleTests(unittest.TestCase):
    def test_every_example_matches_json_and_generated_artifacts(self):
        sources = sorted((ROOT / 'examples').rglob('*.json'))
        self.assertEqual(len(sources), 6)
        self.assertEqual(len(list((ROOT / 'examples').rglob('*.ngomsl'))), len(sources))
        for source in sources:
            with self.subTest(example=source.stem):
                original = load(source)
                model = load(source.with_suffix('.ngomsl'))
                expected, actual = simulate(original), simulate(model)
                self.assertEqual(actual['status'], 'done')
                self.assertEqual(actual['state'], expected['state'])
                # Explicit selection goals add goal-entry events, but preserve operators.
                self.assertEqual([e for e in actual['events'] if 'op' in e],
                                 [e for e in expected['events'] if 'op' in e])
                goal, events = run_generated(model)
                self.assertEqual(goal['pc'], 'done')
                for slot, value in actual['state'].items():
                    self.assertEqual(goal['s-' + slot], value)
                self.assertEqual(events, run_generated(original)[1])
                self.assertEqual(source.with_suffix('.ngomsl.lisp').read_text(), compile_model(model))

    def test_alternative_and_failed_paths_match_json(self):
        variants = [('write-message', 'mode', 'speech'),
                    ('tutorials/count', 'end', 5),
                    ('tutorials/addition', 'arg2', 3),
                    ('tutorials/semantic-direct', 'object', 'shark')]
        for stem, slot, value in variants:
            with self.subTest(example=stem):
                models = [load(ROOT / 'examples' / (stem + suffix))
                          for suffix in ('.json', '.ngomsl')]
                for model in models:
                    model['state'][slot] = value
                expected, actual = [simulate(model) for model in models]
                self.assertEqual(actual['status'], expected['status'])
                self.assertEqual(actual['state'], expected['state'])
                self.assertEqual([e for e in actual['events'] if 'op' in e],
                                 [e for e in expected['events'] if 'op' in e])
                self.assertEqual(run_generated(models[0]), run_generated(models[1]))
