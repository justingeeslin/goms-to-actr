# ACT-R tutorial tasks expressed as GOMS

These five runnable examples are original task-level GOMS descriptions of three ACT-R Unit 1 tutorial models. They use this project's version 1 JSON format and compile without extensions. Each JSON file has an accompanying generated `.lisp` file.

The task definitions were checked against the tutorial Lisp files in the [asmaloney mirror of the official ACT-R implementation](https://github.com/asmaloney/ACT-R). This mirror is a historical snapshot, not a claim about the newest tutorial release. No upstream Lisp implementation is bundled here.

| GOMS source | Tutorial task | Expected result |
| --- | --- | --- |
| [count.json](count.json) | Count from 2 through 4 | Emits `2`, `3`, `4`; final `count` is 4 |
| [addition.json](addition.json) | Add 5 and 2 by counting up | Emits `7`; final `sum` is 7 and `count` is 2 |
| [semantic-direct.json](semantic-direct.json) | Is a canary a bird? | `judgment` becomes `yes` after one category link |
| [semantic-chain.json](semantic-chain.json) | Is a canary an animal? | `judgment` becomes `yes` after two category links |
| [semantic-failure.json](semantic-failure.json) | Is a canary a fish? | `judgment` becomes `no` after exhausting the category chain |

All five end with source state `status: "complete"` and generated goal `pc done`. A negative category judgment is a successful task completion, so the semantic-failure example ends at `done`, not `failed`. `pc failed` means that no GOMS method was applicable.

## Run and inspect

From the repository root:

```sh
python3 -m goms_to_actr validate examples/tutorials/count.json
python3 -m goms_to_actr simulate examples/tutorials/count.json
python3 -m goms_to_actr simulate examples/tutorials/addition.json
python3 -m goms_to_actr simulate examples/tutorials/semantic-chain.json
python3 -m goms_to_actr compile examples/tutorials/count.json -o examples/tutorials/count.lisp
python3 -m unittest discover -s tests -v
```

Use the same commands with any of the other filenames. The preview's `events` list shows the selected methods and intermediate state assignments, including the separate running-sum and increment-counter updates in addition.

To regenerate all five Lisp files:

```sh
for model in examples/tutorials/*.json; do
  python3 -m goms_to_actr compile "$model" -o "${model%.json}.lisp"
done
```

After loading ACT-R 7 in a Lisp REPL:

```lisp
(load "/absolute/path/to/goms-to-actr/examples/tutorials/semantic-chain.lisp")
(run 10)
(buffer-read 'goal)
```

The final goal should contain `s-judgment "yes"`, `s-object "bird"`, `s-candidate "animal"`, and `pc done`. The model names are distinct, so the examples can coexist. See the main README for runtime setup and limitations. Actual ACT-R execution remains unverified here; automated tests check source results and the emitted control flow using a small sequencing interpreter.

## Counting: bounded successor steps

Upstream: [tutorial/unit1/count.lisp](https://github.com/asmaloney/ACT-R/blob/main/tutorial/unit1/count.lisp), Git blob `32b22a9a1fda4d3552f74c13678a0a51fc2f6ab9`.

**Goal:** enumerate the inclusive interval from two to four. **Method:** initialize the current number, report it, follow two successor steps, and report the endpoint. **Operators:** abstract `think`, state assignment, and literal trace output. **Selection rules:** the entry method requires `start = 2` and `end = 4`; successor and completion methods check the expected current number.

The tutorial uses declarative successor chunks and retrieval requests. This GOMS instance explicitly represents the two successor transitions. `think` marks an abstract cognitive step; it performs no retrieval. Outputs use digit strings in place of the tutorial's symbolic number names. The final goal is retained for inspection instead of cleared. Changing the interval requires editing the method sequence; changing only `start` or `end` makes the entry method inapplicable.

## Addition: separate sum and count subgoals

Upstream: [tutorial/unit1/addition.lisp](https://github.com/asmaloney/ACT-R/blob/main/tutorial/unit1/addition.lisp), Git blob `5f8c9966167d4bda02ef95b97a0fb3bd1b4f4fd5`.

**Goal:** solve five plus two. **Method:** initialize `sum = 5`, `count = 0`; advance the sum, advance the counter, and repeat once; report seven. **Operators:** abstract successor steps, assignments, and trace output. **Selection rules:** the entry method requires the fixed operands; each subgoal checks its expected sum/counter pair; reporting requires both increments to be complete.

The visible state progression is `(sum, count) = (5, 0) → (6, 0) → (6, 1) → (7, 1) → (7, 2)`. This retains the tutorial's distinction between incrementing the sum and incrementing the counter. Successor retrieval and the counting loop become explicit subgoals for this particular problem. The final counter remains 2 for inspection; the tutorial clears its count slot on termination. This is not a general arithmetic implementation, and changing the operands alone makes the entry method inapplicable.

## Semantic judgments: direct, chained, and negative

Upstream: [tutorial/unit1/semantic.lisp](https://github.com/asmaloney/ACT-R/blob/main/tutorial/unit1/semantic.lisp), Git blob `9336ea0c988650082250dbc6b9345343cdf4d1b5`.

**Goal:** decide whether a canary belongs to the requested category. **Method:** follow the finite chain `canary → bird → animal`, comparing each candidate category with the query. **Operators:** abstract access steps and assignments. **Selection rules:** choose direct verification when the candidate matches the target; otherwise follow the next link; after exhausting the animal link, answer no.

The three examples correspond to the tutorial's `g1`, `g2`, and `g3` queries. Their goal/method definitions are identical; only the initial target category and model name differ. The default direct example follows one link, the chained example follows two, and the negative example also performs an abstract unsuccessful access at the top of the hierarchy. The `object` slot advances as in the tutorial, while `candidate` makes the accessed category explicit.

The original model retrieves category-property chunks, chains dynamically, and detects retrieval failure. Here the relevant category facts are encoded as explicit method steps; no declarative memory is created. The final negative answer represents exhaustion of this supplied hierarchy, not a universal claim that absence of a known category link proves nonmembership. Other tutorial objects and properties, such as shark, salmon, and wings, are outside these examples.

## What the adaptation preserves

These examples preserve the specified task answers, goal decomposition, selected intermediate states, and finite decision paths. They illustrate how to write GOMS for a known task and inspect the resulting productions. They do not reproduce the tutorial's retrieval mechanisms, chunk representations, production counts, or timing. The generated `think`, selection, and sequencing productions are the compiler's chosen abstraction; matching answers does not establish cognitive or timing equivalence.
