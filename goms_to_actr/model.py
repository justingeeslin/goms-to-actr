"""Validation for the intentionally small, versioned GOMS interchange format."""
import json
import math
import re
from pathlib import Path


class ModelError(ValueError):
    """An invalid or unsupported source model."""


def fail(path, message):
    raise ModelError(f"{path}: {message}")


def fields(value, required, optional, path):
    if not isinstance(value, dict):
        fail(path, "expected an object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing:
        fail(path, f"missing fields: {', '.join(sorted(missing))}")
    if extra:
        fail(path, f"unknown fields: {', '.join(sorted(extra))}")


def name(value, path):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", value):
        fail(path, "expected a lowercase identifier starting with a letter")


def scalar(value, path):
    if isinstance(value, str):
        if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            fail(path, "control characters and unpaired surrogates are unsupported")
    elif type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        fail(path, "expected a string or finite number (not boolean/null)")


def validate(model):
    fields(model, ['version', 'name', 'entry', 'goals'], ['state'], '$')
    if type(model['version']) is not int or model['version'] != 1:
        fail('version', 'only version 1 is supported')
    name(model['name'], 'name')
    name(model['entry'], 'entry')
    state = model.get('state', {})
    if not isinstance(state, dict):
        fail('state', 'expected an object')
    for key, value in state.items():
        name(key, f'state.{key}')
        scalar(value, f'state.{key}')
    goals = model['goals']
    if not isinstance(goals, dict) or not goals:
        fail('goals', 'expected a nonempty object')
    if model['entry'] not in goals:
        fail('entry', 'unknown goal')
    edges = {g: [] for g in goals}

    def assignments(value, path):
        if not isinstance(value, dict) or not value:
            fail(path, 'expected a nonempty object')
        for key, val in value.items():
            if key not in state:
                fail(path, f'undeclared state slot {key!r}')
            scalar(val, f'{path}.{key}')

    for goal, methods in goals.items():
        name(goal, f'goals.{goal}')
        if not isinstance(methods, list) or not methods:
            fail(f'goals.{goal}', 'expected a nonempty method list')
        names = set()
        for i, method in enumerate(methods):
            path = f'goals.{goal}[{i}]'
            fields(method, ['name', 'steps'], ['when'], path)
            name(method['name'], path + '.name')
            if method['name'] in names:
                fail(path, 'duplicate method name')
            names.add(method['name'])
            if 'when' in method:
                assignments(method['when'], path + '.when')
            elif i != len(methods) - 1:
                fail(path, 'unconditional method must be last')
            if not isinstance(method['steps'], list):
                fail(path + '.steps', 'expected a list')
            for j, step in enumerate(method['steps']):
                sp = f'{path}.steps[{j}]'
                fields(step, [], ['goal', 'op', 'values', 'text', 'key'], sp)
                if 'goal' in step:
                    fields(step, ['goal'], [], sp)
                    if not isinstance(step['goal'], str) or step['goal'] not in goals:
                        fail(sp, 'unknown goal')
                    edges[goal].append(step['goal'])
                    continue
                op = step.get('op')
                args = {'set': 'values', 'emit': 'text', 'think': None,
                        'press_key': 'key', 'type_text': 'text', 'speak': 'text'}
                if not isinstance(op, str) or op not in args:
                    fail(sp, f'unsupported operator {op!r}')
                arg = args[op]
                fields(step, ['op'] + ([arg] if arg else []), [], sp)
                if op == 'set':
                    assignments(step['values'], sp + '.values')
                elif arg:
                    if not isinstance(step[arg], str) or not step[arg]:
                        fail(sp, f'{arg} must be a nonempty string')
                    scalar(step[arg], sp + '.' + arg)
                    if op == 'type_text' and any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789 ' for c in step[arg]):
                        fail(sp, 'type_text supports lowercase ASCII letters, digits, and spaces')
                    if op == 'press_key' and step[arg] not in set('abcdefghijklmnopqrstuvwxyz0123456789') | {'space', 'return', 'tab', 'delete', 'escape'}:
                        fail(sp, 'unsupported keyboard key')
    visiting, visited = set(), set()

    def visit(goal):
        if goal in visiting:
            fail('goals', f'recursive goal cycle involving {goal!r}')
        if goal in visited:
            return
        visiting.add(goal)
        for child in edges[goal]:
            visit(child)
        visiting.remove(goal)
        visited.add(goal)
    try:
        for goal in goals:
            visit(goal)
    except RecursionError:
        fail('goals', 'goal hierarchy is too deep')
    return model


def load(path, *, format=None):
    """Load JSON or NGOMSL, detected by extension unless format is supplied."""
    path = Path(path)
    if format is None:
        format = 'ngomsl' if path.suffix.lower() == '.ngomsl' else 'json'
    if format == 'ngomsl':
        from .ngomsl import load_ngomsl
        return load_ngomsl(path)
    if format != 'json':
        raise ModelError(f'unsupported input format {format!r}; expected json or ngomsl')
    return loads(path.read_text(encoding='utf-8'), format=format)


def loads(source, *, format='json'):
    """Parse source text without file I/O, preserving strict JSON validation."""
    if format == 'ngomsl':
        from .ngomsl import parse_ngomsl
        return parse_ngomsl(source)
    if format != 'json':
        raise ModelError(f'unsupported input format {format!r}; expected json or ngomsl')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail('$', f'duplicate JSON key {key!r}')
            result[key] = value
        return result
    try:
        return validate(json.loads(source, object_pairs_hook=unique))
    except ModelError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ModelError(f'invalid JSON: {exc}') from exc
