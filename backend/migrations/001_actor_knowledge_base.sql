CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS actors (
    actor_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    gender SMALLINT,
    birth_year INTEGER,
    biography TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS actor_tags (
    actor_id BIGINT NOT NULL REFERENCES actors(actor_id) ON DELETE CASCADE,
    tag_name TEXT NOT NULL,
    PRIMARY KEY (actor_id, tag_name)
);

CREATE TABLE IF NOT EXISTS past_roles (
    actor_id BIGINT NOT NULL REFERENCES actors(actor_id) ON DELETE CASCADE,
    character_description TEXT NOT NULL,
    PRIMARY KEY (actor_id, character_description)
);

CREATE TABLE IF NOT EXISTS actor_embeddings (
    actor_id BIGINT PRIMARY KEY REFERENCES actors(actor_id) ON DELETE CASCADE,
    embedding vector(384) NOT NULL,
    model_name TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS actors_gender_birth_year_idx
    ON actors (gender, birth_year);
CREATE INDEX IF NOT EXISTS actor_tags_tag_name_idx
    ON actor_tags (tag_name);
CREATE INDEX IF NOT EXISTS actor_embeddings_embedding_idx
    ON actor_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);