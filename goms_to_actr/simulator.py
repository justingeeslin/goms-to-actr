"""Untimed source semantics preview, independent of the ACT-R compiler."""
from .model import ModelError, validate


def simulate(model, *, max_steps=10000):
    validate(model)
    state = dict(model.get('state', {}))
    events = []
    pending = [{'goal': model['entry']}]
    count = 0
    while pending:
        count += 1
        if count > max_steps:
            raise ModelError(f'preview exceeds {max_steps} steps')
        step = pending.pop()
        if 'goal' in step:
            goal = step['goal']
            method = next((m for m in model['goals'][goal]
                           if all(state[k] == v for k, v in m.get('when', {}).items())), None)
            if method is None:
                return {'status': 'failed', 'goal': goal, 'state': state, 'events': events}
            events.append({'goal': goal, 'method': method['name']})
            pending.extend(reversed(method['steps']))
        elif step['op'] == 'set':
            state.update(step['values'])
            events.append(dict(step))
        elif step['op'] == 'type_text':
            if len(step['text']) + count > max_steps:
                raise ModelError(f'preview exceeds {max_steps} steps')
            pending.extend({'op': 'press_key', 'key': 'space' if c == ' ' else c} for c in reversed(step['text']))
        else:
            events.append(dict(step))
    return {'status': 'done', 'state': state, 'events': events}
