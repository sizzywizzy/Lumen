-- Lumen auth schema (Supabase / Postgres).
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

-- ---------------------------------------------------------------------------
-- Sign-up, as one transaction.
--
-- A producer's first sign-up writes four rows: the account, the production,
-- the owner membership and the production's first GlobalState. As four
-- separate statements they can fail half-way, so the API deleted the account
-- again when a later one failed — all-or-nothing on failure, but not one
-- transaction. PostgREST runs a function in a single transaction, so with
-- this one either the whole sign-up is there or none of it is.
--
-- The production id is claimed by the insert itself: PROJ_X, then PROJ_X_2,
-- PROJ_X_3, … until one is free, so two sign-ups naming the same production
-- cannot both take PROJ_X. A production id that already has a state row (an
-- adopted demo project) keeps it.
--
-- Returns {"project_id": "<the id it got>"}. A taken email raises
-- unique_violation (23505), which the API answers as 409. `global_state`
-- comes from schema_state.sql; run both files, in either order.
create or replace function cn_register_producer(
    p_user       jsonb,   -- id, email, name, password_hash, created_at
    p_project_id text,    -- the id to try first
    p_name       text,    -- the production's display name
    p_created_at text,
    p_state      jsonb    -- the production's first GlobalState
) returns jsonb
language plpgsql
as $$
declare
    v_id     text;
    v_suffix integer := 1;
begin
    insert into cn_users (id, email, name, password_hash, created_at)
    values (p_user ->> 'id', p_user ->> 'email', p_user ->> 'name',
            p_user ->> 'password_hash', p_user ->> 'created_at');

    loop
        v_id := case when v_suffix = 1 then p_project_id else p_project_id || '_' || v_suffix end;
        begin
            insert into cn_productions (id, name, owner_id, created_at)
            values (v_id, p_name, p_user ->> 'id', p_created_at);
            exit;
        exception when unique_violation then
            v_suffix := v_suffix + 1;
            if v_suffix >= 1000 then
                raise exception 'No free production id for %', p_project_id;
            end if;
        end;
    end loop;

    insert into cn_memberships (user_id, project_id, role, created_at)
    values (p_user ->> 'id', v_id, 'owner', p_created_at);

    insert into global_state (project_id, state)
    values (v_id, jsonb_set(p_state, '{project_id}', to_jsonb(v_id)))
    on conflict (project_id) do nothing;

    return jsonb_build_object('project_id', v_id);
end;
$$;
