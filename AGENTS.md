# Agent guide for af-component-base

This repo is a [copier](https://copier.readthedocs.io/) template that scaffolds new [DataRobot App Framework](https://af.datarobot.com) projects. It is **not** a runnable application — source files live under `template/`, and copier renders them into a target project at apply time.

## Where changes go

- `template/` — files that get rendered into generated projects. Filenames containing `{{ ... }}` or `{% if ... %}` are jinja templates. Files ending in `.jinja` have their suffix stripped on render.
- `copier.yml` — template questions and defaults (e.g. `template_name`, `include_core`).
- `.github/workflows/validate-template.yaml` — CI for *this* repo.

Files under `template/.github/workflows/` are workflows that ship to generated projects. They do not run in this repo's CI.

## Validating a change

The one command to verify a change locally is:

```bash
task validate
```

It renders the template twice — once with `include_core=true` into `mytemplate/` and once with `include_core=false` into `mytemplate-no-core/` — runs `yamlfmt -lint` on both, then invokes the rendered project's checks through `dr task` (the workflow end users will run). This is the exact same sequence the GitHub Actions workflow runs.

For fast iteration during edits, the granular subtasks are:

| Task                      | What it does                                                                                              |
|---------------------------|-----------------------------------------------------------------------------------------------------------|
| `task render:with-core`   | `uvx copier copy . mytemplate --data include_core=true --defaults`                                        |
| `task render:no-core`     | Same with `include_core=false` → `mytemplate-no-core/`                                                    |
| `task render`             | Both of the above                                                                                         |
| `task lint:yaml`          | yamlfmt -lint on both rendered outputs                                                                    |
| `task validate:with-core` | `cd mytemplate && dr task install && dr task core:lint-check && dr task infra:lint-check && dr task core:test && dr task infra:unit` |
| `task validate:no-core`   | `cd mytemplate-no-core && dr task install && dr task infra:lint-check && dr task infra:unit`              |
| `task clean`              | `rm -rf mytemplate mytemplate-no-core`                                                                    |

The `install` / `lint-check` / `test` / `unit` tasks invoked inside the rendered projects come from `template/{% if include_core %}core{% endif %}/Taskfile.yaml` and `template/infra/Taskfile.yaml.jinja` — read those to see what tooling actually runs (ruff, mypy, pytest). `dr task` composes a root Taskfile from the rendered subdirectories on first invocation.

### Why namespaced `dr task <ns>:<task>` instead of `dr task lint` / `dr task test`?

The composed aggregators have two gaps we can't paper over from this side:

1. `dr task lint` runs each component's `lint` task, which **auto-fixes** (`ruff format`, `ruff check --fix`). For CI we need a read-only check, so we call `dr task core:lint-check` and `dr task infra:lint-check` directly.
2. `dr task test` only aggregates components whose task name is literally `test`. `infra/Taskfile.yaml` exposes `unit`, not `test`, so it would be silently skipped. We call `dr task core:test` and `dr task infra:unit` explicitly.

A follow-up could ship a `.Taskfile.template` in the rendered project that produces correct `lint-check` and `test` aggregators — at that point the root Taskfile here can simplify to `dr task lint-check` + `dr task test`.

## Two-branch rule

`include_core` is a boolean question that gates the entire rendered `core/` directory and one workflow file (`template/.github/workflows/{% if include_core %}core-python.yml{% endif %}`). **Always exercise both branches.** `task validate` does this for you; rendering with only the default value will silently skip the `include_core=false` path.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) — provides `uvx copier`
- [Task](https://taskfile.dev) — task runner
- [`yamlfmt`](https://github.com/google/yamlfmt) — `go install github.com/google/yamlfmt/cmd/yamlfmt@latest`
- `go` — only needed to install `yamlfmt`

## CI parity

`.github/workflows/validate-template.yaml` runs `task validate` across Python 3.11 / 3.12 / 3.13. If you change either the workflow or the Taskfile, update the other so they stay in sync — drift between local and CI is the whole problem this setup exists to prevent.
