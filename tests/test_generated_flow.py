"""Execute the compiler's emitted sequencing subset, not the ACT-R architecture.

This independent reader checks the actual serialized output for branch/return
errors. It deliberately treats module actions as immediately completed and
makes no assertions about ACT-R timing, device behavior, or runtime acceptance.
"""
import json
from pathlib import Path
import re
import unittest

from goms_to_actr import compile_model, simulate


class Symbol(str):
    pass


def read_forms(source):
    tokens = iter(re.findall(r';[^\n]*|"(?:\\.|[^"\\])*"|[()]|[^\s()]+', source))

    def form(token):
        if token == '(':
            result = []
            for token in tokens:
                if token == ')':
                    return result
                if not token.startswith(';'):
                    result.append(form(token))
            raise AssertionError('unclosed Lisp form')
        if token == ')':
            raise AssertionError('unexpected closing parenthesis')
        if token.startswith('"'):
            return re.sub(r'\\(.)', r'\1', token[1:-1])
        try:
            return float(token.replace('d', 'e'))
        except ValueError:
            return Symbol(token)
    return [form(token) for token in tokens if not token.startswith(';')]


def run_generated(model):
    forms = read_forms(compile_model(model))
    assert len(forms) == 1
    body = forms[0][2:]
    initial = next(f[1] for f in body if f[0] == 'define-chunks')
    goal = dict(zip(initial[1::2], initial[2::2]))
    rules = [f for f in body if f[0] == 'p']
    events = []

    def evaluate(expr, bindings):
        if not isinstance(expr, list):
            return bindings.get(expr, expr) if isinstance(expr, Symbol) else expr
        op, *args = expr
        values = [evaluate(arg, bindings) for arg in args]
        if op in ('equal', 'equalp'):
            return values[0] == values[1]
        if op == 'and':
            return all(values)
        if op == 'not':
            return not values[0]
        raise AssertionError(f'unexpected test: {expr}')

    for _ in range(10000):
        if goal['pc'] in ('done', 'failed'):
            return goal, events
        matches = []
        for rule in rules:
            split = rule.index('==>')
            lhs = rule[2:split]
            bindings = {}
            matched = True
            i = 1  # =goal>
            while i < len(lhs):
                slot = lhs[i]
                if slot == '!eval!':
                    matched &= bool(evaluate(lhs[i + 1], bindings))
                    i += 2
                elif slot in ('?manual>', '?vocal>'):
                    i += 3  # query state free
                else:
                    value = lhs[i + 1]
                    if isinstance(value, Symbol) and value.startswith('='):
                        bindings[value] = goal[slot]
                    else:
                        matched &= goal.get(slot) == value
                    i += 2
            if matched:
                matches.append(rule[split + 1:])
        assert len(matches) == 1, f'{goal}: {len(matches)} enabled rules'
        rhs = matches[0]
        i = 1  # =goal>
        while i < len(rhs):
            if rhs[i] == '!eval!':
                events.append(('emit', rhs[i + 1][-1]))
                i += 2
            elif rhs[i] in ('+manual>', '+vocal>'):
                events.append((str(rhs[i + 2]), rhs[i + 4]))
                i += 5
            else:
                goal[rhs[i]] = rhs[i + 1]
                i += 2
    raise AssertionError('generated model did not terminate')


class GeneratedFlowTests(unittest.TestCase):
    def test_example_paths_match_source(self):
        source = Path(__file__).resolve().parents[1] / 'examples/write-message.json'
        for mode in ('keyboard', 'speech'):
            model = json.loads(source.read_text())
            model['state']['mode'] = mode
            goal, events = run_generated(model)
            expected = []
            for event in simulate(model)['events']:
                if event.get('op') == 'press_key':
                    expected.append(('press-key', event['key']))
                elif event.get('op') in ('emit', 'speak'):
                    expected.append((event['op'], event['text']))
            self.assertEqual(events, expected)
            self.assertEqual(goal['pc'], 'done')
            self.assertEqual(goal['s-sent'], 'yes')

    def test_state_changes_reselect_subgoal(self):
        model = {'version': 1, 'name': 'branch', 'entry': 'main', 'state': {'x': 1},
                 'goals': {
                     'main': [{'name': 'run', 'steps': [
                         {'goal': 'child'}, {'op': 'set', 'values': {'x': 2}}, {'goal': 'child'}]}],
                     'child': [
                         {'name': 'one', 'when': {'x': 1.0}, 'steps': [{'op': 'emit', 'text': 'one'}]},
                         {'name': 'other', 'steps': [{'op': 'emit', 'text': 'other'}]}]}}
        goal, events = run_generated(model)
        self.assertEqual(events, [('emit', 'one'), ('emit', 'other')])
        self.assertEqual(goal['pc'], 'done')

    def test_failed_child_never_resumes_parent(self):
        model = {'version': 1, 'name': 'failure', 'entry': 'main', 'state': {'x': 'a'},
                 'goals': {
                     'main': [{'name': 'run', 'steps': [
                         {'goal': 'child'}, {'op': 'emit', 'text': 'must not happen'}]}],
                     'child': [{'name': 'no', 'when': {'x': 'b'}, 'steps': []}]}}
        goal, events = run_generated(model)
        self.assertEqual(goal['pc'], 'failed')
        self.assertEqual(events, [])
