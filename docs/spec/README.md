# Spec: Developing This Project with an AI Assistant

This folder is the spec an AI coding assistant (such as Claude Code) or a person works from. It
follows the [GitHub Spec Kit](https://github.com/github/spec-kit) structure: rules first, then
what to build, how, and the tasks.

| File | Answers |
|---|---|
| [constitution.md](constitution.md) | Which rules can never be broken? |
| [spec.md](spec.md) | What must the platform do, and how do we know? (user stories, acceptance criteria, test IDs) |
| [plan.md](plan.md) | How is it built? (stack, where code lives, interfaces, engine behaviour to respect) |
| [tasks.md](tasks.md) | What is done, and what is next? |

[CLAUDE.md](../../CLAUDE.md) at the repository root points the assistant here, and lists the
commands and conventions.

## The Workflow

1. **Pick a task** from [tasks.md](tasks.md). For something new, first add a user story with
   acceptance criteria to [spec.md](spec.md), and a task for it.
2. **Ask the assistant for a plan, not code.** In Claude Code, use plan mode. Point it at the
   task, and have it read the constitution, the story and the plan.
3. **Review the plan** against the [constitution](constitution.md): it must keep every rule,
   name the test that proves the acceptance criterion, and add a mutation for any new guard.
   Send it back until it does.
4. **Implement test first:** write the failing test named in the acceptance criterion, then the
   code, then the mutation entry.
5. **Verify:**
   ```sh
   make test && ruff check . && ruff format --check .
   .venv/bin/python tests/mutation/run.py --only <your-guard>
   ```
6. **Update the spec in the same change:** tick the task, mark the criterion ✅, add the test to
   the [test plan](../../tests/README.md), and add an ADR if a decision was made.
7. **Open a pull request** (see [CONTRIBUTING.md](../../CONTRIBUTING.md)).

## A Prompt to Start With

```text
Read docs/spec/constitution.md, docs/spec/spec.md and docs/spec/plan.md.
Plan task T05 from docs/spec/tasks.md. Do not write code yet.
Your plan must: keep every rule in the constitution; name the test that proves acceptance
criterion US-1 #9 and the wrong answer it guards against; add a mutation entry for any new
guard; and list the docs to update. Flag anything in plan.md's "Engine behaviour to respect"
that applies.
```
