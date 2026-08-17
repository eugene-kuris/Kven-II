# Engineering method

The public Kven II method is deliberately small.

## Necessity only

**Nothing except what is strictly necessary to accomplish the task.**

If removing code, configuration, documentation, tests, controls, or process steps leaves the required result intact without materially increasing a concrete task-relevant risk, remove them.

## Bounded flow

1. Verify the actual starting state.
2. Inspect before editing.
3. Measure before redesigning.
4. Make the smallest coherent change.
5. Run the tests that directly cover the changed risk.
6. Broaden testing only when evidence justifies it.
7. Perform one bounded acceptance check.
8. Stop at the cheapest trustworthy failure boundary.
9. Return compact evidence, not ceremonial process.

## Retry discipline

Rollback restores state. It does not restore:

- model tokens;
- API credits;
- elapsed time;
- compute;
- human attention.

A failed attempt should therefore produce diagnosis before another mutation is attempted.

## Evidence

A PASS should correspond to an observable condition, not a convenient narrative. Read-only diagnostic work should be able to finish without fake commits or unrelated changes.

## Architecture implication

The method is part of the product architecture because it constrains how changes enter a stateful AI system. Continuity is undermined if the engineering process itself allows ambiguous state transitions, hidden retries, or undocumented mutation.
