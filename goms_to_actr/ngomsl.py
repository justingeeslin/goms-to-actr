"""Parse a bounded, executable NGOMSL subset into the shared GOMS model.

Methods and selection rule sets follow NGOMSL's goal-dispatch structure. The
metadata, literal operators, and ordered selection policy are this project's
explicit dialect; arbitrary natural-language operators are never guessed.
"""
import json
from pathlib import Path
import re

from .model import ModelError, scalar, validate


_HEADER = re.compile(
    r'^(Model|Initial goal|Initial state|Method for goal|Selection rule set for goal)\s*:',
    re.IGNORECASE)
_RETURN = 'return with goal accomplished'


class Parser:
    def __init__(self, source):
        self.source = source
        self.model = {'version': 1, 'state': {}, 'goals': {}}
        self.references = []

    def error(self, line, message):
        raise ModelError(f'{self.source}:{line}: {message}')

    def identifier(self, text, line):
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*(?:\s+[a-zA-Z0-9_-]+)*', text):
            self.error(line, 'expected a goal phrase or identifier using ASCII words')
        return re.sub(r'\s+', '-', text.lower())

    def statements(self, text):
        pending, start = '', 1
        for line, raw in enumerate(text.splitlines(), 1):
            # Comments may follow a statement, but # inside a string is literal.
            quoted, escaped = False, False
            for i, char in enumerate(raw):
                if escaped:
                    escaped = False
                elif char == '\\' and quoted:
                    escaped = True
                elif char == '"':
                    quoted = not quoted
                elif char == '#' and not quoted:
                    raw = raw[:i]
                    break
            if quoted:
                self.error(line, 'unterminated string; use JSON escapes within one line')
            value = raw.strip()
            if not value:
                continue
            if _HEADER.match(value):
                if pending:
                    self.error(start, 'statement must end with a period')
                yield line, value.removesuffix('.').rstrip()
                continue
            if not pending:
                start = line
            pending = (pending + ' ' + value).strip()
            if value.endswith('.'):
                yield start, pending[:-1].rstrip()
                pending = ''
        if pending:
            self.error(start, 'statement must end with a period')

    def value(self, text, pos, line):
        try:
            value, end = json.JSONDecoder().raw_decode(text, pos)
        except (ValueError, RecursionError) as exc:
            self.error(line, f'expected a quoted string or number: {exc}')
        try:
            scalar(value, 'value')
        except ModelError as exc:
            self.error(line, str(exc))
        return value, end

    def pairs(self, text, relation, line):
        """Read scalar comparisons/assignments, leaving the selection's THEN tail."""
        values, pos = {}, 0
        while True:
            match = re.match(r'([a-z][a-z0-9_-]*)\s*' + relation + r'\s*',
                             text[pos:], re.IGNORECASE)
            if not match:
                self.error(line, 'expected a state slot followed by ' + relation)
            slot = match[1].lower()
            if slot in values:
                self.error(line, f'duplicate state slot {slot!r}')
            pos += match.end()
            values[slot], pos = self.value(text, pos, line)
            match = re.match(r'\s+and\s+', text[pos:], re.IGNORECASE)
            if not match:
                return values, text[pos:].strip()
            pos += match.end()

    def declared(self, values, line):
        for slot in values:
            if slot not in self.model['state']:
                self.error(line, f'undeclared state slot {slot!r}')

    def goal_reference(self, text, line):
        goal = self.identifier(text, line)
        self.references.append((goal, line))
        return {'goal': goal}

    def operator(self, text, line):
        match = re.fullmatch(r'Accomplish goal:\s*(.+)', text, re.IGNORECASE)
        if match:
            return self.goal_reference(match[1], line)
        match = re.fullmatch(r'Set\s+(.+)', text, re.IGNORECASE)
        if match:
            values, tail = self.pairs(match[1], r'\bto\b', line)
            if tail:
                self.error(line, f'unexpected assignment text {tail!r}')
            self.declared(values, line)
            return {'op': 'set', 'values': values}
        if text.lower() == 'think':
            return {'op': 'think'}
        match = re.fullmatch(r'(Emit|Speak|Type text|Press key)\s+(.+)', text, re.IGNORECASE)
        if match:
            value, end = self.value(match[2], 0, line)
            if not isinstance(value, str) or match[2][end:].strip():
                self.error(line, 'operator argument must be one quoted string')
            op = {'emit': 'emit', 'speak': 'speak', 'type text': 'type_text',
                  'press key': 'press_key'}[match[1].lower()]
            return {'op': op, 'key' if op == 'press_key' else 'text': value}
        self.error(line, f'unsupported NGOMSL operator {text!r}')

    def parse(self, text):
        section, methods, expected_step = None, None, 1
        metadata, definitions_started = set(), False
        for line, statement in self.statements(text):
            header = _HEADER.match(statement)
            if header:
                if section in ('method', 'selection'):
                    self.error(line, 'previous block is missing Return with goal accomplished')
                kind = header[1].lower()
                value = statement[header.end():].strip()
                if kind in ('model', 'initial goal', 'initial state'):
                    if definitions_started:
                        self.error(line, 'model metadata must precede goal definitions')
                    if kind in metadata:
                        self.error(line, f'duplicate {kind} declaration')
                    metadata.add(kind)
                    if kind == 'initial state':
                        if value:
                            self.error(line, 'Initial state must introduce a block of assignments')
                        section = 'state'
                    else:
                        section = None
                        if kind == 'model':
                            self.model['name'] = self.identifier(value, line)
                        else:
                            self.model['entry'] = self.goal_reference(value, line)['goal']
                    continue
                definitions_started = True
                goal = self.identifier(value, line)
                if goal in self.model['goals']:
                    self.error(line, f'duplicate goal {goal!r}; use a selection rule set for alternatives')
                methods = self.model['goals'][goal] = []
                if kind == 'method for goal':
                    section, expected_step = 'method', 1
                    methods.append({'name': 'method', 'steps': []})
                else:
                    section = 'selection'
                continue
            if section == 'state':
                values, tail = self.pairs(statement, '=', line)
                if tail:
                    self.error(line, f'unexpected initial state text {tail!r}')
                for slot in values:
                    if slot in self.model['state']:
                        self.error(line, f'duplicate state slot {slot!r}')
                self.model['state'].update(values)
            elif section == 'method':
                match = re.fullmatch(r'Step\s+([0-9]+)\.\s+(.+)', statement, re.IGNORECASE)
                if not match or match[1] != str(expected_step):
                    self.error(line, f'expected Step {expected_step}. followed by an operator')
                expected_step += 1
                if match[2].lower() == _RETURN:
                    section = None
                else:
                    methods[0]['steps'].append(self.operator(match[2], line))
            elif section == 'selection':
                if statement.lower() == _RETURN:
                    if not methods:
                        self.error(line, 'selection rule set must contain at least one rule')
                    section = None
                    continue
                if methods and 'when' not in methods[-1]:
                    self.error(line, 'Otherwise must be the last selection rule')
                method = {'name': f'rule-{len(methods) + 1}'}
                match = re.fullmatch(r'If\s+(.+)', statement, re.IGNORECASE)
                if match:
                    values, tail = self.pairs(match[1], r'\bis\b', line)
                    self.declared(values, line)
                    method['when'] = values
                    match = re.fullmatch(r',?\s*then\s+accomplish goal:\s*(.+)', tail, re.IGNORECASE)
                else:
                    match = re.fullmatch(r'Otherwise,?\s+accomplish goal:\s*(.+)', statement,
                                         re.IGNORECASE)
                if not match:
                    self.error(line, 'expected If <conditions>, then accomplish goal: <goal> '
                               'or Otherwise accomplish goal: <goal>')
                method['steps'] = [self.goal_reference(match[1], line)]
                methods.append(method)
            else:
                self.error(line, f'unexpected statement outside a block: {statement!r}')
        if section in ('method', 'selection'):
            self.error(len(text.splitlines()) or 1, 'missing Return with goal accomplished')
        for kind in ('model', 'initial goal'):
            if kind not in metadata:
                self.error(1, f'missing {kind} declaration')
        for goal, line in self.references:
            if goal not in self.model['goals']:
                self.error(line, f'unknown goal {goal!r}')
        try:
            return validate(self.model)
        except ModelError as exc:
            raise ModelError(f'{self.source}: {exc}') from exc


def parse_ngomsl(text, *, source='<ngomsl>'):
    """Parse text into a validated model accepted by compile_model and simulate."""
    return Parser(source).parse(text)


def load_ngomsl(path):
    """Read a UTF-8 NGOMSL source file and return its validated shared model."""
    return parse_ngomsl(Path(path).read_text(encoding='utf-8'), source=str(path))
