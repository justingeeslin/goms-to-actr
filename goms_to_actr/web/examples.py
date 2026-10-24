"""A small equivalent example in both supported source languages."""
import json


MODEL = {
    'version': 1,
    'name': 'send-message',
    'entry': 'send-message',
    'state': {'sent': 'no'},
    'goals': {
        'send-message': [{
            'name': 'default',
            'steps': [
                {'op': 'think'},
                {'op': 'type_text', 'text': 'hello world'},
                {'op': 'press_key', 'key': 'return'},
                {'op': 'set', 'values': {'sent': 'yes'}},
                {'op': 'emit', 'text': 'Message sent'},
            ],
        }],
    },
}
EXAMPLES = {
    'ngomsl': '''Model: send-message.
Initial goal: send message.
Initial state:
  sent = "no".

Method for goal: send message
  Step 1. Think.
  Step 2. Type text "hello world".
  Step 3. Press key "return".
  Step 4. Set sent to "yes".
  Step 5. Emit "Message sent".
  Step 6. Return with goal accomplished.
''',
    'json': json.dumps(MODEL, indent=2) + '\n',
}
