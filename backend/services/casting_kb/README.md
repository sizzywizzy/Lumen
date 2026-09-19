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

## Does it work?

[`backend/eval/casting`](../../eval/casting/README.md) measures it: 52 casting
briefs written from real parts, each resolved to its actor through TMDb, ranked
against a pool of about a thousand with the part itself held out. It reports
recall@5, recall@10 and MRR against two baselines — TF-IDF over the same text,
and a shuffle — because a recall number with nothing to read it against says
nothing.

One thing that will bite you, and which the evaluation cannot catch for you:
`actor_embeddings.model_name` records the model each vector came from, and
`match_actors` does not check it. Change `EMBEDDING_MODEL` to another
384-dimension model and the stored vectors keep their dimension, pass every
check here, and mismatch every query in silence. Re-run the embeddings after any
change to that setting.
