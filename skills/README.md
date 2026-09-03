# Agent skills

A skill is a procedure an agent follows, written as `skills/<name>/SKILL.md`.
The format follows the open Agent Skills convention: YAML frontmatter with a
`name`, a `description` that says when to use the skill, and a `metadata` map,
followed by Markdown instructions.

```
skills/
├── audience-simulation/
│   └── SKILL.md
├── casting/
│   └── SKILL.md
├── scheduling/
│   └── SKILL.md
└── cultural-research/
    └── SKILL.md
```

How the backend uses them:

- `backend/core/skills/registry.py` discovers every `SKILL.md`, parses the
  frontmatter and exposes the body as the skill's instructions.
- `backend/domains/skills/agents.py` maps each skill to the agent that runs it
  (`metadata.agent`). The agent gathers facts from `GlobalState`, runs any
  prerequisite phase agents, then calls Gemini with **the SKILL.md body as its
  system instruction** and the facts as the prompt. With no `GEMINI_API_KEY`
  every skill still completes on a deterministic offline fallback computed from
  the same facts, and the run record says which path produced the answer.
- `POST /api/skills/<name>/run/<project_id>` starts a run in the background;
  the AI Advisors page in the dashboard polls it and renders the result.
- Every skill returns the same envelope so the UI can render any of them:
  `summary`, `highlights[]`, `findings[{title, detail, severity, ref}]`,
  `next_actions[]`, `confidence`, and a skill-specific `data` object.

The full catalogue of skills and the shared capabilities behind the pipeline
agents is in [`skills.md`](../skills.md) at the repo root.

Editing a SKILL.md takes effect on the next run; no restart is needed. Each run
records a fingerprint of the SKILL.md that produced it. To add a skill: create
the folder and file, add a runner in `agents.py`, and register the agent id in
`AGENT.md`.
