-- CineNode advisor-run schema (Supabase / Postgres).
--
-- Only needed when SUPABASE_URL + SUPABASE_KEY are configured. With no
-- credentials the same records are kept as JSON under backend/.state/skills/.
-- Written by services/skill_store.py, which upserts one row per run.

create table if not exists cn_skill_runs (
    run_id            text primary key,       -- RUN_<hex>
    project_id        text not null,          -- == GlobalState.project_id
    skill             text not null,          -- skills/<skill>/SKILL.md
    title             text,
    agent             text not null,          -- agent id from the SKILL.md metadata
    status            text not null check (status in ('running', 'complete', 'failed')),
    created_at        text not null,
    completed_at      text,
    started_by        text,                   -- cn_users.id of the member who pressed run
    params            jsonb not null default '{}'::jsonb,
    skill_version     text,
    skill_fingerprint text,                   -- sha256 prefix of the SKILL.md that ran
    stages            jsonb not null default '[]'::jsonb,
    result            jsonb,                  -- summary / highlights / findings / next_actions / data
    provenance        jsonb,                  -- per-call live-vs-fallback trace
    error             text,
    traceback         text                    -- server-side only; never returned by the API
);

create index if not exists cn_skill_runs_project_idx on cn_skill_runs (project_id, created_at desc);

-- The API reaches Supabase with the service key and enforces membership itself
-- (see core/auth/deps.py), so this table must never be exposed to anon clients.
alter table cn_skill_runs enable row level security;
