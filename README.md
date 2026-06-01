<p align="center">
  <a href="https://github.com/datarobot-community/af-component-base">
    <img src="https://af.datarobot.com/img/datarobot_logo.avif" width="600px" alt="DataRobot Logo"/>
  </a>
</p>
<p align="center">
    <span style="font-size: 1.5em; font-weight: bold; display: block;">af-component-base</span>
</p>

<p align="center">
  <a href="https://datarobot.com">Homepage</a>
  ·
  <a href="https://af.datarobot.com">Documentation</a>
  ·
  <a href="https://docs.datarobot.com/en/docs/get-started/troubleshooting/general-help.html">Support</a>
</p>

<p align="center">
  <a href="https://github.com/datarobot-community/af-component-base/tags">
    <img src="https://img.shields.io/github/v/tag/datarobot-community/af-component-base?label=version" alt="Latest Release">
  </a>
  <a href="/LICENSE">
    <img src="https://img.shields.io/github/license/datarobot-community/af-component-base" alt="License">
  </a>
  <a href="https://join.slack.com/t/datarobot-community/shared_invite/zt-3uzfp8k50-SUdMqeux25ok9_5wr4okrg">
    <img src="https://img.shields.io/badge/%23applications-a?label=Slack&labelColor=30373D&color=81FBA6" alt="Slack #applications">
  </a>
</p>

The base component required for all AF built apps

`af-component-base` is a [copier](https://copier.readthedocs.io/) template that provides the foundational scaffold for every application built with the [DataRobot App Framework](https://af.datarobot.com). It is the first component applied to any new App Framework project.

When applied, it walks you through a short configuration wizard (template name, description, copyright year, and whether to include the shared `core` library), then writes the base project structure and answers file that all other App Framework components build on top of. Answers are stored in `.datarobot/answers/base.yml` and reused by subsequent `copier update` runs.

This component is intended for app developers starting a new App Framework project or bringing an existing project up to the standard structure.

# Table of contents

- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Component dependencies](#component-dependencies)
  - [Local development](#local-development)
  - [Updating](#updating)
- [Troubleshooting](#troubleshooting)
- [Next steps and cross-links](#next-steps-and-cross-links)
- [Contributing, changelog, support, and legal](#contributing-changelog-support-and-legal)

# Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) installed
- [`dr`](https://cli.datarobot.com) installed

A DataRobot account and environment are required to deploy the resulting application. See [DataRobot getting started](https://docs.datarobot.com/en/docs/get-started/) for account setup.

# Quick start

Run the following command in your project directory:

```bash
dr component add https://github.com/datarobot-community/af-component-base .
```

If you need additional control, you can run this to use copier directly:

```bash
uvx copier copy datarobot-community/af-component-base .
```

The wizard prompts for:

- **Template name**&mdash;human-readable display name (e.g. `My Sales Assistant`).
- **Template code name**&mdash;auto-derived lowercase slug; override if needed.
- **Template description**&mdash;Markdown-compatible description shown in the App Framework gallery.
- **Copyright year**&mdash;defaults to the current year.
- **Include core library**&mdash;whether to include the shared `core` package for multi-component recipes (default: yes).

# Component dependencies

`af-component-base` has no required component dependencies. It is the root of the App Framework component graph — all other components build on top of it.

## Local development

`af-component-base` is a copier template, not a runnable service. All source files live under `template/`, which copier renders into the target project directory at apply time.

To work on the template itself:

1. Clone this repository.
2. Edit files under `template/` or update questions in `copier.yml`.
3. Test your changes against a scratch directory:

```bash
uvx copier copy . /tmp/my-test-app
```

The `copier.yml` at the repo root defines all template questions and their defaults. The answers file path is `.datarobot/answers/base.yml` in the target project.

## Updating

All components should be regularly updated to pick up bug fixes, new features,
and compatibility with the latest DataRobot App Framework.

For automatic updates to the latest version, run the following command in your project directory:
```bash
dr component update .datarobot/answers/base.yml
```

If you need more fine grained control and prefer using copier directly,
you can run this to have more control over the process:

```bash
uvx copier update -a .datarobot/answers/base.yml -A
```

# Troubleshooting

This section covers common issues when applying or updating the component.

**copier asks questions I already answered**

`.datarobot/answers/base.yml` may be missing or out of date. Run the update command with `-A` to skip interactive prompts and use saved answers:

```bash
uvx copier update -a .datarobot/answers/base.yml -A
```

**`dr component add` is not found**

Install or update the DataRobot CLI. See [cli.datarobot.com](https://cli.datarobot.com) for installation instructions.

**Template conflicts after `copier update`**

Copier shows a diff for any file with local modifications. Review each conflict, keep your changes where appropriate, and commit the result.

# Next steps and cross-links

After applying this component, add further functionality by layering additional App Framework components on top.

- [App Framework documentation](https://af.datarobot.com)&mdash;full component catalog, architecture guide, and deployment docs.
- [DataRobot CLI](https://cli.datarobot.com)&mdash;`dr component add`, `dr deploy`, and other workflow commands.
- [App Framework Studio (internal)](https://datarobot.atlassian.net/wiki/spaces/BOPS/pages/6542032899/App+Framework+-+Studio)&mdash;internal design and planning context.

# Contributing, changelog, support, and legal

**Contributing**: Fork the repository and open a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide, including how to report bugs and the maintainer response SLA.

**Getting help**: Open a [GitHub Issue](https://github.com/datarobot-community/af-component-base/issues) for bugs and feature requests. For security vulnerabilities, email the maintainers directly or contact [oss-community-management@datarobot.com](mailto:oss-community-management@datarobot.com).

**License**: This project is licensed under the terms in [LICENSE](LICENSE).
