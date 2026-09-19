# Does the actor search find the right actor?

Lumen will take a character description and hand back a ranked list of actors
who fit it ([`services/casting_kb`](../../services/casting_kb/README.md)): the
brief is embedded, the actors are embedded, and pgvector ranks them by cosine
distance. That is a claim about retrieval, so it can be measured like one.

**The question.** Given a casting brief for a real part, how often does the
search put the actor who actually played it in the top five — and does the
embedding model do better than counting shared words?

The second half is the part that decides something. A sentence-transformer, half
a gigabyte of PyTorch and a pgvector column are a lot of apparatus. If TF-IDF
ranks as well, the apparatus is decoration.

## The design

| | |
|---|---|
| **Briefs** | 52, written by hand in [`labels.py`](labels.py), one per real part |
| **Right answer** | Resolved from TMDb: the film's cast list, that character, whoever TMDb says played them |
| **Corpus** | The 50 answers plus ~1,000 distractors from TMDb's popular-people pages, actors only, each with a biography or at least three credits |
| **Held out** | Each answer's own credit for the film its brief came from, removed before anything is embedded |
| **Indexes** | `semantic` (what ships) · `semantic_roles_first` (a diagnostic) · `lexical` (TF-IDF) · `chance` (a shuffle) |
| **Metrics** | recall@5, recall@10 with a Wilson interval, MRR, and a paired bootstrap on the recall@10 gap |

Five choices are doing the real work.

**No brief names anything.** Not the actor, not the film, not the character. An
actor's stored record is literally `Actor: {name}. Biography: {bio}. Past roles:
{character} in {title}`, so a brief that mentions any of them is testing string
matching and would report a fine number for a system that does nothing. This is
not left to my discipline:
[`test_casting_recall.py`](../../tests/test_casting_recall.py) checks all 52
briefs for all three, and for any distinctive word from a name. Seven ordinary
nouns — "detective", "wedding", "queen" and four others — are allowed through by
name, because a brief that could not say what the part *is* would not be a
casting brief, and a second test fails if one of those permissions stops being
used.

**The answers come from TMDb, not from me.** I wrote the briefs; I did not write
the labels. `resolve` searches the film, finds the character in its cast and
records whoever TMDb lists. A label that does not resolve to exactly one actor is
printed and dropped rather than guessed at — five were, the first time, because
TMDb spells a character differently than the credits do ("Fletcher", not "Terence
Fletcher"), and the fix was to correct the spelling rather than to loosen the
match.

**The part is held out.** An actor's record keeps their ten most popular credits.
If the part a brief describes is among them, the search is being asked to find an
actor from a record containing the answer. Each answer's credit for that film is
therefore removed before embedding, which turns the question into the one worth
asking: from an actor's *other* work, can the search tell they would be right for
this part? It is a harder question than the product faces in practice, and the
number should be read as a floor because of it.

**The distractors have to be real.** An actor with no biography and no credits is
a distractor no search would ever rank highly, and a corpus padded with them
reports a recall the real corpus would not reproduce. So the pool is filtered to
people TMDb files under Acting who have a biography or at least three credits,
and the number skipped is recorded.

**`chance` and `lexical` are in the comparison.** Recall@10 over a pool of a
thousand is 1% by chance, and any result near that line is evidence of nothing.
TF-IDF is the harder floor: it is free, it has no dependencies, and if it wins
then the embedding is not earning its place. The audience evaluation next door
keeps a `constant` baseline for the same reason, and it is usually the baseline
that would have changed the conclusion.

## What came out of it

| index | recall@5 | recall@10 | MRR | never found |
|---|---:|---:|---:|---:|
| `semantic` — `all-MiniLM-L6-v2`, what ships | 17% | 19% | 0.082 | 27 |
| `semantic_roles_first` — the same, reordered | 17% | 17% | 0.106 | 28 |
| `lexical` — TF-IDF | **33%** | **35%** | **0.205** | 21 |
| `semantic` — `bge-small-en-v1.5` | 27% | 33% | 0.170 | **19** |
| `chance` | 0% | 0% | 0.000 | 52 |

**The shipped model loses to counting words.** 19% against 35% at ten, with the
gap's 95% interval running from -29 to -2 points — entirely below zero, so it is
not this sample. Everything beats chance decisively, so the search works; it is
just beaten by a baseline with no dependencies.

**Truncation is real and is not the reason.** `all-MiniLM-L6-v2` reads 256
tokens, and `actor_description` puts the biography before the past roles: 683 of
the 1,159 records here run past that limit and 503 lose their roles entirely, so
the casting signal never reaches the vector. That looked like the whole
explanation. Reordering the text moved recall@10 by one brief out of 52, which
rules it out — the `semantic_roles_first` row exists to record that, because
without the test this would have been reported as the cause.

**A different model closes almost all of the gap.** `bge-small-en-v1.5` scores
33% against TF-IDF's 35%, an interval of -17 to +13 that crosses zero, and it
misses fewer briefs outright than any other index. It is built for short queries
against long documents, which is exactly this task and exactly what MiniLM is
not. It is also 384-dimensional, so it is a drop-in: `EMBEDDING_MODEL` and a
re-run of `scripts/generate_actor_embeddings.py`, with no schema migration.

What that adds up to, for whoever picks this up: the approach is sound, the model
is the wrong one, and the honest position today is that a dependency-free TF-IDF
ranking would serve users at least as well as what ships. A hybrid of the two is
the obvious next thing to try and is **not** tested here.

One change came out of this directly, in the product rather than the evaluation:
`match_actors` now refuses to search when `actor_embeddings.model_name` disagrees
with `EMBEDDING_MODEL`. Both models above are 384-dimensional, so swapping one
for the other used to pass every check and return confident nonsense.

## Running it

```bash
cd backend
pip install sentence-transformers   # ~500MB of PyTorch; left out of requirements.txt on purpose

# 1. briefs -> right answers, from TMDb. Needs TMDB_API_KEY (free).
python -m eval.casting.run resolve

# 2. fetch the corpus, parts held out. ~1,000 TMDb reads, a few minutes.
python -m eval.casting.run build --distractor-pages 60

# 3. rank every brief three ways. Local, no API, no quota, no database.
python -m eval.casting.run score

# 4. compute the metrics and write REPORT.md
python -m eval.casting.run report

# optional: is it the approach or the model? Scores a different one and keeps
# both rows, so the comparison is in one table.
python -m eval.casting.run score --index semantic --embedding-model BAAI/bge-small-en-v1.5
```

The steps are separate on purpose. Rebuilding the corpus after seeing a result
would let the pool be tuned until the numbers improve, which is the exact failure
the committed `queries.json` and `actors.json` prevent.

## Two things that will bite you

**One model, both sides.** A brief and an actor record must be embedded by the
same model or the comparison is between two unrelated coordinate systems and the
recall collapses to chance. `EMBEDDING_MODEL` is read once and used for both here
— but in the product, `actor_embeddings.model_name` is written and never checked
at query time, so a database embedded with a different 384-dimension model would
mismatch in silence. Re-embed after changing the setting.

**The ranking runs in memory, not in Postgres.** pgvector's `<=>` is cosine
distance over normalised vectors; `search.py` computes the same thing as a dot
product. That is what lets this run on a laptop with no database — which matters,
because Supabase pauses a free project after about a week and the host stops
resolving, as it had when this was written. The product's SQL also applies age
and gender filters that are not measured here at all.

## What a result here cannot tell you

- **A thousand actors is not a casting database.** Recall falls as the pool
  grows, so this is an upper bound on the same search over every working actor.
- **The distractors are famous.** TMDb's popular pages are a more uniform pool
  than a real roster of local actors with thin credits. Which way that biases the
  number is not obvious and is not measured.
- **One right answer per brief.** Several actors could play most of these parts.
  A brief whose top five are all plausible scores as a miss unless the one who
  got the part is among them, so recall understates usefulness.
- **The briefs are mine, written knowing the answer.** They name no actor, film
  or character, and a test enforces that — but a subtler echo of the performance
  I had in mind is possible, and no test can rule it out.
- **n = 52.** Enough for a large difference, not a subtle one. Every recall
  carries an interval and every comparison a bootstrap for that reason.
- **Nothing here measures the filters** the product applies on age and gender,
  which could only help.

## Files

| | |
|---|---|
| `labels.py` | the 52 hand-written briefs, with the film and part each came from |
| `corpus.py` | resolving labels against TMDb, and building the corpus with parts held out |
| `search.py` | the three indexes: `semantic`, `lexical`, `chance` |
| `metrics.py` | recall@k, MRR, Wilson interval, paired bootstrap — stdlib only |
| `run.py` | the `resolve` / `build` / `score` / `report` CLI |
| `queries.json` | the committed labelled set |
| `actors.json` | the committed corpus, so the pool cannot drift under the result |
| `REPORT.md` | the generated report, caveats included |
