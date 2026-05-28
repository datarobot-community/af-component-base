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

It renders the template twice — once with `include_core=true` into `mytemplate/` and once with `include_core=false` into `mytemplate-no-core/` — runs `yamlfmt -lint` on both, then runs `task install && task lint-check && task test|unit` inside the rendered `core/` and `infra/` projects. This is the exact same sequence the GitHub Actions workflow runs.

For fast iteration during edits, the granular subtasks are:

| Task                      | What it does                                                                |
|---------------------------|-----------------------------------------------------------------------------|
| `task render:with-core`   | `uvx copier copy . mytemplate --data include_core=true --defaults`          |
| `task render:no-core`     | Same with `include_core=false` → `mytemplate-no-core/`                      |
| `task render`             | Both of the above                                                           |
| `task lint:yaml`          | yamlfmt -lint on both rendered outputs                                      |
| `task test:core`          | `cd mytemplate/core && task install && task lint-check && task test`        |
| `task test:infra`         | `cd mytemplate/infra && task install && task lint-check && task unit`       |
| `task test:infra-no-core` | Same as `test:infra` against `mytemplate-no-core/infra`                     |
| `task clean`              | `rm -rf mytemplate mytemplate-no-core`                                      |

The `install` / `lint-check` / `test` / `unit` tasks invoked inside the rendered projects come from `template/{% if include_core %}core{% endif %}/Taskfile.yaml` and `template/infra/Taskfile.yaml.jinja` — read those to see what tooling actually runs (ruff, mypy, pytest).

## Two-branch rule

`include_core` is a boolean question that gates the entire rendered `core/` directory and one workflow file (`template/.github/workflows/{% if include_core %}core-python.yml{% endif %}`). **Always exercise both branches.** `task validate` does this for you; rendering with only the default value will silently skip the `include_core=false` path.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) — provides `uvx copier`
- [Task](https://taskfile.dev) — task runner
- [`yamlfmt`](https://github.com/google/yamlfmt) — `go install github.com/google/yamlfmt/cmd/yamlfmt@latest`
- `go` — only needed to install `yamlfmt`

## CI parity

`.github/workflows/validate-template.yaml` runs `task validate` across Python 3.11 / 3.12 / 3.13. If you change either the workflow or the Taskfile, update the other so they stay in sync — drift between local and CI is the whole problem this setup exists to prevent.
