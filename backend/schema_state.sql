-- Lumen pipeline-state and audience-simulation schema (Supabase / Postgres).
--
-- Only needed when SUPABASE_URL + SUPABASE_KEY are configured. With no
-- credentials the same records are kept as JSON under backend/.state/.
-- Written by services/supabase_client.py (global_state),
-- services/simulation_store.py (cn_simulations, cn_simulations_panel),
-- services/poster_store.py (cn_posters) and
-- services/pipeline_store.py (cn_pipeline_runs).

-- One GlobalState document per production: every phase's output, the A2A
-- event log the Live Agent Terminal polls, and the screenplay from intake.
create table if not exists global_state (
    project_id text primary key,          -- == cn_productions.id
    state      jsonb not null
);

-- One summary row per audience simulation, upserted after every stage.
-- PostgREST rejects a write that names a column the table lacks, so every key
-- domains/audience/router.py writes onto a run record has a column here.
create table if not exists cn_simulations (
    simulation_id            text primary key,   -- SIM_<hex>
    project_id               text not null,      -- == GlobalState.project_id
    status                   text not null check (status in ('running', 'complete', 'failed')),
    created_at               text not null,
    completed_at             text,
    disclaimer               text,
    config                   jsonb not null default '{}'::jsonb,  -- panel size, seed, markets, material fingerprint
    stages                   jsonb not null default '[]'::jsonb,
    report                   jsonb,               -- overall score, segments, would-watch
    analysis                 jsonb,
    sensitivity              jsonb,               -- cultural scan per market
    recommendations          jsonb,
    provenance               jsonb,               -- per-call live-vs-fallback trace
    dimensions               jsonb,
    distribution_fingerprint text,
    cohort_summary           jsonb,
    error                    text,
    traceback                text                 -- server-side only
);

create index if not exists cn_simulations_project_idx on cn_simulations (project_id, created_at desc);

-- The full persona panel and every individual response, kept out of the
-- summary row because only the audit view reads them.
create table if not exists cn_simulations_panel (
    simulation_id text primary key,       -- == cn_simulations.simulation_id
    project_id    text not null,
    panel         jsonb not null          -- personas, responses, cohorts, distribution
);

-- The production's poster (agent_visual key art): one row per production,
-- replaced only once a new poster has painted. Every key
-- services/poster_store.py writes has a column here.
create table if not exists cn_posters (
    project_id         text primary key,    -- == GlobalState.project_id
    poster_id          text not null,       -- PST_<hex>, new with every poster
    created_at         text not null,
    started_by         text,                -- the user whose run or request painted it
    script_fingerprint text,                -- the screenplay it was painted from
    title              text,
    style              jsonb not null default '{}'::jsonb,  -- the style drawn at random
    concept            jsonb not null default '{}'::jsonb,  -- tagline, scene, palette, alt text
    provenance         jsonb not null default '{}'::jsonb,  -- live model or offline sketch, per step
    image_mime         text not null,
    image_base64       text not null
);

-- One row per pipeline run (the whole plan, or one phase group), upserted at
-- every phase change. The run itself lives in the API process's memory; this
-- is what is left of it after a restart, so the dashboard can still say how
-- the production's last run ended. Every key domains/pipeline/jobs.py writes
-- onto a record has a column here.
create table if not exists cn_pipeline_runs (
    job_id      text primary key,       -- JOB_<hex>
    project_id  text not null,          -- == GlobalState.project_id
    scope       text not null check (scope in ('pipeline', 'casting', 'production', 'launch')),
    status      text not null check (status in ('running', 'complete', 'failed')),
    started_at  text not null,
    finished_at text,
    started_by  text,                   -- cn_users.id of the member who started it
    phases      jsonb not null default '[]'::jsonb,  -- key, title, status per phase
    log_start   integer,                -- where this run's envelopes begin in the event log
    events      integer,                -- how long the event log was once it was merged
    summary     jsonb,                  -- what the finished run reports to the page
    error       text
);

create index if not exists cn_pipeline_runs_project_idx on cn_pipeline_runs (project_id, started_at desc);

-- The API reaches Supabase with the secret key and enforces membership itself
-- (see core/auth/deps.py), so these tables must never be exposed to anon
-- clients. Deny-all RLS makes that explicit.
alter table global_state         enable row level security;
alter table cn_simulations       enable row level security;
alter table cn_simulations_panel enable row level security;
alter table cn_posters           enable row level security;
alter table cn_pipeline_runs     enable row level security;
