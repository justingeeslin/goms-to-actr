# Executable NGOMSL

NGOMSL files are a human-readable input to the same ACT-R compiler used for JSON.
The parser implements a **bounded NGOMSL subset**, with explicit metadata and a
small operator vocabulary. It does not interpret arbitrary prose or implement
all of NGOMSL or GOMSL/GLEAN.

The method, subgoal, numbered-step, return, and selection-rule notation follows
[David Kieras's NGOMSL guide](https://www.cosc.brocku.ca/~bockusd/3p94/kieras96guide.pdf),
especially sections 2.2–2.4. `Model`, `Initial goal`, `Initial state`, the literal
operator vocabulary below, `Otherwise`, and ordered rule selection specify this
project's executable dialect.

## Use it

```sh
python3 -m goms_to_actr validate examples/write-message.ngomsl
python3 -m goms_to_actr simulate examples/write-message.ngomsl
python3 -m goms_to_actr compile examples/write-message.ngomsl -o message.lisp
```

`load` and every CLI command automatically recognize `.ngomsl` (case insensitive).
Other extensions default to JSON. For an NGOMSL file with another extension, use
`--format ngomsl`. `--format json` explicitly chooses the existing JSON reader.
Files use UTF-8.

```python
from goms_to_actr import compile_model, load, load_ngomsl, parse_ngomsl, simulate

model = load("examples/write-message.ngomsl")
lisp = compile_model(model)
preview = simulate(model)

# Explicit file loading or parsing text is also supported:
model = load_ngomsl("examples/write-message.ngomsl")
model = parse_ngomsl(source_text, source="my-model.ngomsl")
```

The parser returns the same validated version-1 dictionary as the JSON reader.
`compile_model`, `simulate`, and their resource limits work with that dictionary.
Syntax errors report a source name and line number; shared model validation also
rejects invalid operators, recursive goal cycles, and excessively deep hierarchies.

## Complete example

```text
Model: greeting.
Initial goal: greet the user.
Initial state:
  channel = "voice".
  finished = "no".

Selection rule set for goal: greet the user
  If channel is "voice", then accomplish goal: say hello.
  Otherwise accomplish goal: type hello.
  Return with goal accomplished.

Method for goal: say hello
  Step 1. Speak "Hello".
  Step 2. Accomplish goal: finish greeting.
  Step 3. Return with goal accomplished.

Method for goal: type hello
  Step 1. Type text "hello".
  Step 2. Accomplish goal: finish greeting.
  Step 3. Return with goal accomplished.

Method for goal: finish greeting
  Step 1. Set finished to "yes".
  Step 2. Return with goal accomplished.
```

## Syntax and values

- Declare `Model` and `Initial goal` once, before any goal definitions. An optional
  `Initial state:` block declares slots and initial values with `slot = value.`.
  Multiple assignments can share a statement: `x = 1 and y = "ready".`.
- Goal and model names can be phrases of ASCII words, digits, underscores, and
  hyphens, beginning with a letter. Case is ignored; spaces become hyphens in the
  shared model and generated Lisp. `Send Message` and `send-message` identify the
  same goal. Duplicate definitions after normalization are errors.
- State slots use the JSON identifier form: a letter followed by letters, digits,
  underscores, or hyphens. They are normalized to lowercase. Declare every slot
  before testing or assigning it.
- Values are JSON double-quoted strings or finite numbers. Strings compare exactly;
  numbers compare numerically. Booleans, null, arrays, objects, control characters,
  and unpaired Unicode surrogates are rejected. JSON string escapes are supported.
- Keywords are case insensitive. Headers may end with a period. All other
  statements must end with a period, including every step and return. Write one
  statement per line or wrap a statement over several lines; keep each quoted
  string on one physical line.
- `#` starts a comment outside quoted strings. Blank lines and indentation do not
  affect meaning. Comments can explain what an abstract `Think` step represents.

## Methods and operators

Each `Method for goal: <goal>` defines one method for that goal. Number its steps
consecutively from 1 and end with a numbered `Return with goal accomplished.`.
A method containing only that return is allowed. Subgoals return to the following
step; state is shared. Forward references are allowed.

| Step body | Shared-model meaning |
| --- | --- |
| `Accomplish goal: compose.` | Call a subgoal. |
| `Think.` | One abstract cognitive step. |
| `Set sent to "yes".` | Assign a declared state slot. |
| `Set sum to 5 and count to 0.` | Assign multiple slots in one step. |
| `Emit "Message sent".` | Print literal trace text. |
| `Press key "return".` | Request a key and wait for manual completion. |
| `Type text "hello world".` | Request and await each key in sequence. |
| `Speak "Hello".` | Request speech and wait for vocal completion. |
| `Return with goal accomplished.` | Finish this method and resume its caller. |

Keyboard and text restrictions are the same as JSON: lowercase ASCII letters,
digits, and spaces for typed text; single letters/digits or `space`, `return`,
`tab`, `delete`, and `escape` for keys. Text arguments must be quoted strings.
Unknown natural-language actions are rejected rather than treated as `Think`.

## Selection rules

Use `Selection rule set for goal: <general goal>` to dispatch to specific goals.
A goal has either a method or a selection rule set, never both. End the set with
an unnumbered `Return with goal accomplished.`.

```text
Selection rule set for goal: check bird
  If candidate is "bird" and category is "bird", then
    accomplish goal: verify direct link.
  If candidate is "bird", then accomplish goal: follow bird parent.
  Return with goal accomplished.
```

Conditions support conjunctions of slot-to-literal equality tests. The **first
matching rule** wins, just as in the JSON compiler. An optional `Otherwise
accomplish goal: <goal>.` is an unconditional fallback and must be last. A set
must contain at least one rule. If none applies, execution fails and does not
resume the caller. Selection occurs once on entry, even if the selected method
later changes the tested slots.

Classical NGOMSL expects mutually exclusive selection conditions tested in
parallel. This implementation explicitly uses ordered checks to preserve the
existing compiler policy; the example above relies on that ordering. It makes
no claim to preserve NGOMSL statement times or learning-time predictions.

A method lowers to a shared-model method named `method`. Selection rules lower
to methods named `rule-1`, `rule-2`, etc., each calling its specific goal. The
explicit dispatch goals can add goal-entry events and ACT-R sequencing productions
compared with the compact JSON representation. A return uses the compiler's
continuation and does not add an independent timed return operator.

## Examples and limits

Every stored JSON example has a neighboring `.ngomsl` source and a generated
`.ngomsl.lisp` file. Tests compare final state, operator events, alternative paths,
failed guards, and the emitted production control flow across both formats.
The two representations of an example use the same ACT-R model name; load the
representation you want to run.

`Decide`, `Goto`, loops, parameterized goals, perceptual operators, retrieval,
learning, arbitrary Lisp, and free-form operators are unsupported. Counting,
addition, and semantic chaining remain the finite task-level adaptations
described in the [tutorial guide](../examples/tutorials/README.md).
`simulate` is an untimed source preview. Actual ACT-R runtime acceptance and
timing have not been verified in this environment.
