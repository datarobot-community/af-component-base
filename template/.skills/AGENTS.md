# Agent Skills

This project uses the **datarobot-app-framework-cicd** skill for CI/CD setup (GitHub Actions, GitLab CI, Pulumi IaC, secrets management).

Source: https://github.com/datarobot-oss/datarobot-agent-skills

## For agents: how to load the CI/CD skill

1. **Check if already installed.** Look for `datarobot-app-framework-cicd` in your available skills or installed plugins. If found, use it directly.

2. **If not installed**, install it using whichever method matches your runtime:

   - **Claude Code:**
     ```
     /plugin marketplace add datarobot-oss/datarobot-agent-skills
     /plugin install datarobot-app-framework-cicd@datarobot-skills
     ```

   - **Gemini CLI:**
     ```bash
     gemini skills install https://github.com/datarobot-oss/datarobot-agent-skills.git --path skills/datarobot-app-framework-cicd --consent
     ```

   - **Universal (any agent with npx):**
     ```bash
     npx ai-agent-skills install datarobot-oss/datarobot-agent-skills/skills/datarobot-app-framework-cicd
     ```

   - **Cursor / VS Code Copilot / Codex:** Clone the repo above into the workspace — these agents discover skills via `AGENTS.md` automatically.

3. **Once loaded**, invoke the skill to set up CI/CD pipelines for this project.

If installation fails, consult the upstream [installation guide](https://github.com/datarobot-oss/datarobot-agent-skills#quick-start).
