# Actor knowledge base

An optional casting aid: actors imported from TMDb into PostgreSQL with
pgvector, embedded with `sentence-transformers`, and searched by character
description. Nothing else in Lumen needs it, and the pipeline runs without it.

## Setup

1. Run `backend/migrations/001_actor_knowledge_base.sql` against a PostgreSQL
   database with pgvector enabled.
2. Install the backend requirements, plus `sentence-transformers` for the
   embeddings (it is commented out in `requirements.txt` because it pulls in
   PyTorch).
3. Set `DATABASE_URL` and `TMDB_API_KEY`, and optionally
   `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS` (see `.env.example`).

## Use

Populate and search it through the casting API. The knowledge base is shared
across productions, so these routes are not scoped to one, but they do need a
signed-in account: sign in first and send the session token as a bearer.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"your-password"}' \
  | python -c 'import json, sys; print(json.load(sys.stdin)["token"])')
curl -X POST http://localhost:8000/api/casting/actors/ingest \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"actor_ids":[6193,500]}'
curl -X POST http://localhost:8000/api/casting/actors/embeddings \
  -H "Authorization: Bearer $TOKEN"
curl -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8000/api/casting/actors/search?character_description=cunning%20detective%20in%20her%20forties&gender=1&min_age=35&max_age=49'
```

TMDb does not normally provide physical measurements or appearance traits, so
the ingestion code stores only explicitly supplied trait fields and does not
infer sensitive attributes from photos or names.
