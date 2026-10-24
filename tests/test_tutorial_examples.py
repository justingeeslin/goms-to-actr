"""Task-level expectations for the tutorial adaptations and emitted artifacts."""
import copy
from pathlib import Path
import unittest

from goms_to_actr import compile_model, load, simulate
from test_generated_flow import run_generated

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/tutorials'


class TutorialExampleTests(unittest.TestCase):
    def test_all_examples_complete_and_generated_files_are_current(self):
        sources = sorted(EXAMPLES.glob('*.json'))
        self.assertEqual(len(sources), 5)
        for source in sources:
            with self.subTest(example=source.stem):
                model = load(source)
                result = simulate(model)
                self.assertEqual(result['status'], 'done')
                self.assertEqual(result['state']['status'], 'complete')
                self.assertEqual(source.with_suffix('.lisp').read_text(), compile_model(model))
                goal, events = run_generated(model)
                self.assertEqual(goal['pc'], 'done')
                for slot, value in result['state'].items():
                    self.assertEqual(goal['s-' + slot], value)
                self.assertEqual(events, [('emit', e['text']) for e in result['events']
                                          if e.get('op') == 'emit'])

    def test_count_reports_inclusive_interval(self):
        result = simulate(load(EXAMPLES / 'count.json'))
        outputs = [e['text'] for e in result['events'] if e.get('op') == 'emit']
        self.assertEqual(outputs, ['2', '3', '4'])
        counts = [e['values']['count'] for e in result['events']
                  if e.get('op') == 'set' and 'count' in e['values']]
        self.assertEqual(counts, [2, 3, 4])

    def test_addition_advances_sum_and_counter_separately(self):
        result = simulate(load(EXAMPLES / 'addition.json'))
        state = {}
        pairs = []
        for event in result['events']:
            if event.get('op') == 'set':
                state.update(event['values'])
                if 'sum' in event['values'] or 'count' in event['values']:
                    pairs.append((state['sum'], state['count']))
        self.assertEqual(pairs, [(5, 0), (6, 0), (6, 1), (7, 1), (7, 2)])
        self.assertEqual([e['text'] for e in result['events'] if e.get('op') == 'emit'], ['7'])

    def test_fixed_arithmetic_inputs_reject_unsupported_problem(self):
        for filename, slot, value in [('count', 'end', 5), ('addition', 'arg2', 3)]:
            with self.subTest(example=filename):
                model = load(EXAMPLES / (filename + '.json'))
                model['state'][slot] = value
                self.assertEqual(simulate(model)['status'], 'failed')
                goal, events = run_generated(model)
                self.assertEqual(goal['pc'], 'failed')
                self.assertEqual(events, [])

    def test_semantic_queries_use_same_methods_and_different_paths(self):
        baseline = load(EXAMPLES / 'semantic-direct.json')
        for variant, category, judgment, links, final_object in [
                ('direct', 'bird', 'yes', 1, 'canary'),
                ('chain', 'animal', 'yes', 2, 'bird'),
                ('failure', 'fish', 'no', 2, 'animal')]:
            with self.subTest(query=category):
                model = load(EXAMPLES / ('semantic-' + variant + '.json'))
                self.assertEqual(model['goals'], baseline['goals'])
                result = simulate(model)
                self.assertEqual(result['state']['category'], category)
                self.assertEqual(result['state']['judgment'], judgment)
                self.assertEqual(result['state']['object'], final_object)
                candidates = [e['values']['candidate'] for e in result['events']
                              if e.get('op') == 'set' and 'candidate' in e['values']]
                self.assertEqual(candidates, ['bird', 'animal'][:links])
                if judgment == 'no':
                    self.assertEqual(result['status'], 'done')

    def test_semantic_rejects_unsupported_subject(self):
        model = copy.deepcopy(load(EXAMPLES / 'semantic-direct.json'))
        model['state']['object'] = 'shark'
        self.assertEqual(simulate(model)['status'], 'failed')
        goal, _ = run_generated(model)
        self.assertEqual(goal['pc'], 'failed')
