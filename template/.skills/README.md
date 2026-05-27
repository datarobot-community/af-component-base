# Agent Skills

This template uses skills from [datarobot-agent-skills](https://github.com/datarobot-oss/datarobot-agent-skills).

## Install

The universal installer works for all supported agents at once:

```bash
npx ai-agent-skills install datarobot-oss/datarobot-agent-skills/skills/datarobot-app-framework-cicd
```

### Per-agent alternatives

**Claude Code**
```bash
/plugin marketplace add datarobot-oss/datarobot-agent-skills
/plugin install datarobot-app-framework-cicd@datarobot-skills
```

**Gemini CLI**
```bash
gemini extensions install https://github.com/datarobot-oss/datarobot-agent-skills.git --consent
```

**Cursor / VS Code Copilot / Codex**

These agents read `AGENTS.md` automatically — install the skills repo into your workspace and skills are available immediately.

**OpenCode**

Add to `~/.config/opencode/opencode.json`:
```json
{ "plugin": ["opencode-datarobot-skills"] }
```

If you run into issues, see the full [installation guide](https://github.com/datarobot-oss/datarobot-agent-skills#quick-start).
