-- CineNode auth schema (Supabase / Postgres).
--
-- Only needed when SUPABASE_URL + SUPABASE_KEY are configured. With no
-- credentials the same tables are kept as JSON under backend/.state/auth/,
-- so local dev and the demo need none of this.
--
-- Nothing reversible is stored: `password_hash` is a PBKDF2-SHA256 digest and
-- session/invite tokens are kept only as SHA-256 fingerprints.

create table if not exists cn_users (
    id            text primary key,
    email         text unique not null,
    name          text not null,
    password_hash text not null,
    created_at    text not null
);

create table if not exists cn_productions (
    id         text primary key,           -- also GlobalState.project_id
    name       text not null,
    owner_id   text not null references cn_users (id) on delete cascade,
    created_at text not null
);

create table if not exists cn_memberships (
    user_id    text not null references cn_users (id) on delete cascade,
    project_id text not null references cn_productions (id) on delete cascade,
    role       text not null default 'crew' check (role in ('owner', 'producer', 'crew')),
    created_at text not null,
    primary key (user_id, project_id)
);

create table if not exists cn_invites (
    id                text primary key,
    project_id        text not null references cn_productions (id) on delete cascade,
    token_fingerprint text unique not null,  -- sha256(token); the token is never stored
    role              text not null default 'crew' check (role in ('producer', 'crew')),
    created_by        text not null references cn_users (id) on delete cascade,
    created_at        text not null,
    expires_at        text not null,
    max_uses          integer not null default 1,
    uses              integer not null default 0,
    revoked           boolean not null default false,
    label             text not null default ''
);

create table if not exists cn_sessions (
    token_fingerprint text primary key,     -- sha256(token)
    user_id           text not null references cn_users (id) on delete cascade,
    created_at        text not null,
    expires_at        text not null
);

create index if not exists cn_memberships_project_idx on cn_memberships (project_id);
create index if not exists cn_invites_project_idx     on cn_invites (project_id);
create index if not exists cn_sessions_user_idx       on cn_sessions (user_id);

-- The API reaches Supabase with the service key and enforces membership itself
-- (see core/auth/deps.py), so these tables must never be exposed to anon
-- clients. Deny-all RLS makes that explicit.
alter table cn_users       enable row level security;
alter table cn_productions enable row level security;
alter table cn_memberships enable row level security;
alter table cn_invites     enable row level security;
alter table cn_sessions    enable row level security;

-- Housekeeping: drop sessions that have aged out.
--   delete from cn_sessions where expires_at < to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"');
