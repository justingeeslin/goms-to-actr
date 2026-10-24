# GOMS → ACT-R

An MIT-licensed Python compiler from a structured GOMS format to ACT-R 7 Common Lisp. Python 3.10+; no runtime dependencies. Includes a command-line interface, a library, input validation, an untimed source preview, and runnable examples.

This is a new implementation. It does not reproduce G2A or parse arbitrary prose, GOMSL, NGOMSL, or CPM-GOMS files. Version 1 uses the JSON dialect below so translation decisions can be explicit and testable.

## Try it

From this directory, without installing anything:

```sh
python3 -m goms_to_actr validate examples/write-message.json
python3 -m goms_to_actr simulate examples/write-message.json
python3 -m goms_to_actr compile examples/write-message.json -o examples/write-message.lisp
python3 -m unittest discover -s tests -v
```

Optionally install with `python3 -m pip install -e .` to use the `goms-to-actr` command with the same arguments. Compile writes Lisp to stdout unless `-o` is supplied. Invalid input returns exit code 2; an untimed preview with no applicable method returns 1. Compilation never evaluates source text as Python or Lisp.

## Tutorial examples

The [tutorial examples guide](examples/tutorials/README.md) includes GOMS versions of ACT-R Unit 1 counting (2 through 4), addition (5 + 2), and three semantic judgments (canary as bird, animal, or fish). Each includes JSON input and generated Lisp, expected results, upstream source links, and an explanation of the adaptations. These are finite task-level descriptions; retrieval and loops are represented by explicit steps.

```sh
python3 -m goms_to_actr simulate examples/tutorials/semantic-chain.json
python3 -m goms_to_actr compile examples/tutorials/addition.json -o addition.lisp
```

## Input format

```json
{
  "version": 1,
  "name": "greeting",
  "entry": "greet",
  "state": {"channel": "voice", "finished": "no"},
  "goals": {
    "greet": [
      {
        "name": "say-it",
        "when": {"channel": "voice"},
        "steps": [
          {"op": "speak", "text": "Hello"},
          {"goal": "finish"}
        ]
      },
      {
        "name": "type-it",
        "steps": [
          {"op": "type_text", "text": "hello"},
          {"goal": "finish"}
        ]
      }
    ],
    "finish": [
      {"name": "mark-finished", "steps": [
        {"op": "set", "values": {"finished": "yes"}}
      ]}
    ]
  }
}
```

- `version`, `name`, `entry`, and `goals` are required. `state` defaults to `{}`.
- Names start with a lowercase ASCII letter, followed by lowercase letters, digits, `_`, or `-`.
- State values are strings or finite numbers. Booleans, null, control characters, and unpaired Unicode surrogates are rejected. Declare every state slot before using it in a condition or assignment.
- Each goal contains a nonempty ordered list of uniquely named methods. Each method has `name`, `steps`, and optionally `when`. Empty steps are allowed.
- `when` is a nonempty map of state slots to required values. All equalities must hold. Strings compare exactly and numbers compare numerically. The **first matching method** wins. An unconditional method is a fallback and must be last.
- A step is either `{"goal": "name"}` or an operator object. Subgoals return to the following step. State is shared across calls. A method is chosen once on goal entry.
- Recursive goal cycles, unknown fields/operators/references, and duplicate JSON keys are rejected. The compiler defaults to a 10,000-state expansion limit. The preview defaults to 10,000 steps. Very deep hierarchies are rejected.

## Operators and translation

| Source step | Generated ACT-R behavior |
| --- | --- |
| `{"op":"think"}` | One production advances the goal state. This is an abstract cognitive step, not a calibrated mental operator. |
| `{"op":"set","values":{"slot":"value"}}` | One production updates declared goal slots. |
| `{"op":"emit","text":"message"}` | Prints literal text through a fixed Lisp format string; useful for tracing. |
| `{"op":"press_key","key":"a"}` | Waits for the manual module, requests `press-key`, then waits for the manual module to become free. |
| `{"op":"type_text","text":"hello world"}` | A sequence of key requests with a completion check after every key. Supports lowercase ASCII letters, digits, and spaces. |
| `{"op":"speak","text":"Hello"}` | Waits for the vocal module, requests `speak`, then waits for the module to become free. |

`press_key` supports `a`–`z`, `0`–`9`, `space`, `return`, `tab`, `delete`, and `escape`. Generated keyboard models install ACT-R's virtual keyboard and assume the default home-row hand positions. The model produces virtual keyboard events; it does not type into your operating system. Speech uses ACT-R's modeled vocal events.

Hierarchy is expanded at each call site with a distinct continuation. A program-counter slot in the goal buffer controls sequencing; each source state slot receives an `s-` prefix. Model names receive a `goms-` prefix. Generated comments identify the source goal, method, and step. Selection uses successive guard-check productions with complementary `!eval!` conditions; it does not rely on production utility to enforce ordering. A failed guard advances to the next method, so later methods incur additional selection productions.

Successful completion leaves goal `pc` at `done`. If all methods fail their guards, `pc` becomes `failed` and execution stops without returning to the caller. Both states have no outgoing productions. Empty methods simply return to their continuation.

## Run the output in ACT-R

Install and load the official Lisp-based ACT-R 7 distribution first. From its Lisp REPL:

```lisp
(load "/absolute/path/to/goms-to-actr/examples/write-message.lisp")
(run 30)
(buffer-read 'goal)
```

Inspect the trace and final goal chunk (`pc done`, `s-sent "yes"`). `run` takes simulated seconds; increase its limit for longer tasks. Use `(reset)` before rerunning the same model. The emitted file defines the model without calling `clear-all`, so it does not delete other loaded models.

The generated syntax follows the official ACT-R 7.30+ reference manual. The repository tests validate input handling, output structure, and generated control flow. **Execution in an actual ACT-R runtime has not been verified in this environment.** The `simulate` command executes source-level semantics only; it does not simulate ACT-R timing or perceptual/motor processes.

## Python API

```python
from goms_to_actr import load, compile_model, simulate

model = load("examples/write-message.json")
lisp = compile_model(model, max_states=10000)
preview = simulate(model, max_steps=10000)
```

`validate(model)` accepts an in-memory dictionary. Invalid models raise `ModelError`. File operations may also raise normal I/O errors.

## Modeling scope

GOMS does not uniquely determine an ACT-R model. This compiler makes one conservative, sequential mapping with explicit method selection. Goal transitions, selection tests, and completion checks add production cycles. `think` consumes one ordinary production cycle, rather than an assumed KLM mental duration. Generated models disable subsymbolic computation with `:esc nil`; this keeps the initial translation simple but does not eliminate motor/vocal timing.

Version 1 has no visual search, pointing, retrieval, learning, parallel operators, loops, parameterized goals, arbitrary Lisp extensions, or automatic fitting to human data. State is task bookkeeping in the goal buffer, not a theory of working memory. Use generated output as a starting model requiring domain validation; timings are not asserted to preserve GOMS/KLM predictions. The compiler's per-call-site expansion models hierarchy without claiming that people cognitively inline methods.

## Background

[G2A: Specifying ACT-R models of user interaction with a GOMS language](https://pure.psu.edu/en/publications/specifying-act-r-models-of-user-interaction-with-a-goms-language/) (St. Amant, Freed, & Ritter, 2005) describes alternative mappings from higher-level GOMS operators to ACT-R. It motivates making translation assumptions visible. This project is independent of that implementation.

[Official ACT-R 7.30+ reference manual](https://act-r.psy.cmu.edu/actr7.x/reference-manual.pdf): production conditions and actions, goal chunks, keyboard device installation, and manual/vocal requests.
