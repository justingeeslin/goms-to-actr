"""A continuation-based compiler; hierarchical calls are expanded per call site."""
from .model import ModelError, validate


def literal(value):
    if isinstance(value, str):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(value, float):
        result = repr(value)
        return result.replace('e', 'd') if 'e' in result else result + 'd0'
    return repr(value)


class Compiler:
    def __init__(self, model, max_states=10000, max_output_bytes=None):
        self.model = validate(model)
        self.max_states = max_states
        self.max_output_bytes = max_output_bytes
        self.output_bytes = 0
        self.count = 0
        self.productions = []
        self.motor = False

    def state(self):
        self.count += 1
        if self.count > self.max_states:
            raise ModelError(f'expanded model exceeds {self.max_states} states')
        return f'pc-{self.count}'

    def rule(self, source, target, label, conditions='', actions='', updates=''):
        production = (
            f'  ;; {label}\n'
            f'  (p rule-{len(self.productions) + 1}\n'
            f'    =goal>\n      isa goms-state\n      pc {source}\n'
            f'{conditions}'
            f'    ==>\n'
            f'    =goal>\n      pc {target}\n{updates}{actions}  )\n')
        if self.max_output_bytes is not None:
            self.output_bytes += len(production.encode('utf-8')) + 1
            if self.output_bytes > self.max_output_bytes:
                raise ModelError(f'generated Lisp exceeds {self.max_output_bytes} bytes')
        self.productions.append(production)

    def step(self, step, continuation, path):
        if 'goal' in step:
            return self.goal(step['goal'], continuation, path)
        op = step['op']
        if op == 'type_text':
            for char in reversed(step['text']):
                continuation = self.step({'op': 'press_key', 'key': 'space' if char == ' ' else char}, continuation, path)
            return continuation
        start = self.state()
        if op == 'set':
            updates = ''.join(f'      s-{k} {literal(v)}\n' for k, v in step['values'].items())
            self.rule(start, continuation, path, updates=updates)
        elif op == 'emit':
            # A fixed format string prevents user text from becoming a FORMAT program.
            self.rule(start, continuation, path, actions=f'    !eval! (format t "~&~a~%" {literal(step["text"])})\n')
        elif op == 'think':
            self.rule(start, continuation, path)
        else:
            module = 'manual' if op == 'press_key' else 'vocal'
            command = 'press-key' if op == 'press_key' else 'speak'
            slot = 'key' if op == 'press_key' else 'string'
            value = step['key'] if op == 'press_key' else step['text']
            self.motor |= module == 'manual'
            wait = self.state()
            query = f'    ?{module}>\n      state free\n'
            self.rule(start, wait, path + ' / request', conditions=query,
                      actions=f'    +{module}>\n      cmd {command}\n      {slot} {literal(value)}\n')
            self.rule(wait, continuation, path + ' / completion', conditions=query)
        return start

    def goal(self, goal, continuation, path):
        methods = self.model['goals'][goal]
        choice = self.state()
        entry = choice
        for i, method in enumerate(methods):
            label = f'{path} / {goal}.{method["name"]}'
            body = continuation
            for j in reversed(range(len(method['steps']))):
                body = self.step(method['steps'][j], body, label + f' / step {j + 1}')
            guard = method.get('when')
            if guard:
                bindings = ''.join(f'      s-{k} =v{n}\n' for n, k in enumerate(guard))
                # Strings use EQUAL, numbers use = to match the preview semantics.
                tests = ' '.join(f'({"equal" if isinstance(v, str) else "equalp"} =v{n} {literal(v)})' for n, v in enumerate(guard.values()))
                test = f'(and {tests})'
                next_choice = self.state() if i < len(methods) - 1 else 'failed'
                self.rule(choice, body, label + ' / selected', bindings + f'    !eval! {test}\n')
                self.rule(choice, next_choice, label + ' / skipped', bindings + f'    !eval! (not {test})\n')
                choice = next_choice
            else:
                self.rule(choice, body, label + ' / selected')
        return entry

    def compile(self):
        try:
            entry = self.goal(self.model['entry'], 'done', 'entry')
        except RecursionError as exc:
            raise ModelError('expanded hierarchy is too deep') from exc
        slots = ''.join(f' s-{key}' for key in self.model.get('state', {}))
        initial = ''.join(f' s-{k} {literal(v)}' for k, v in self.model.get('state', {}).items())
        setup = '  (install-device \'("motor" "keyboard"))\n' if self.motor else ''
        result = (f';; Generated by goms-to-actr v0.1.0. Load after ACT-R 7.\n'
                f';; Terminal goal pc: done (success), failed (no applicable method).\n'
                f'(define-model goms-{self.model["name"]}\n'
                f'  (sgp :v t :esc nil)\n'
                f'  (chunk-type goms-state pc{slots})\n'
                f'  (define-chunks (goms-initial isa goms-state pc {entry}{initial}))\n'
                f'  (goal-focus goms-initial)\n{setup}\n' + '\n'.join(self.productions) + ')\n')
        if self.max_output_bytes is not None and len(result.encode('utf-8')) > self.max_output_bytes:
            raise ModelError(f'generated Lisp exceeds {self.max_output_bytes} bytes')
        return result


def compile_model(model, *, max_states=10000, max_output_bytes=None):
    """Return ACT-R 7 Common Lisp; raise ModelError on unsupported input."""
    return Compiler(model, max_states=max_states, max_output_bytes=max_output_bytes).compile()
