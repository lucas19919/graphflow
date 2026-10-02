# GEMINI.md — Architecture-First Development Rule

This workspace renders system thinking before system building. The `graph`
engine (`graph.py`, pure stdlib) is the blueprint tool. Skill:
`.agents/skills/graph-engine/SKILL.md`.

## When this rule fires

Any task that (a) adds/alters a database table, column, or relation,
(b) adds/changes inter-service or inter-module communication (APIs, events, RPCs),
(c) introduces a component, worker, queue, or scheduled job, or
(d) encodes branching business logic with more than 3 decision points.

Trivial edits (typos, copy, styling) are exempt. When in doubt, the rule fires.

## The contract

1. **Blueprint first.** Draft the affected view with `graph`
   (`arch` for services, `schema` for tables, `seq` for calls, `flow` for logic).
2. **Gates pass.** `validate` exit 0 before render; `audit` exit 0 after.
   Never present an unaudited diagram.
3. **Align, then code.** Link the `.svg`/`.html` artifact in the task plan and
   treat the approved diagram as the inviolable build spec.
4. **Stay in sync.** Changing a boundary without updating its diagram is a
   defect. `graph monitor --map graph.monitor.json --ci` is the CI gate;
   `graph doc` keeps fenced specs compiled. The auto-fix bot
   (`graph sync --map graph.monitor.json [--commit]`) may apply mechanical
   syncs itself — every auto-applied spec must still pass `validate`+`audit`,
   and `--commit` never pushes.

## Budgets (non-negotiable, machine-enforced)

9 nodes · 12 edges · 2 focal · 6 seq actors / 16 messages · 6 tables per view.
Over budget → split views, never cram.
