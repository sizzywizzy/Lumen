"""Three ways to rank actors for a brief: the product's, a cheap one, and chance.

`semantic` is what Lumen ships. The other two exist because a recall number on
its own is unreadable — it has to be read against what you would get for free.

**`lexical`** ranks by shared words (TF-IDF, cosine). If the embedding model does
not beat counting words, the sentence-transformer dependency, the 500MB of
PyTorch and the pgvector column are buying nothing, and that is worth knowing
before anyone builds more on top of them. This is the same role `constant` plays
in the audience evaluation next door.

**`chance`** shuffles. Its recall@k is k/N whatever the corpus, and any result
near that line is evidence of nothing.

The product ranks with pgvector's `<=>`, which is cosine distance over the same
normalised vectors this computes with a dot product; `test_casting_recall.py`
checks the two agree on a small corpus when a database is reachable. Ranking here
rather than in SQL is what lets the evaluation run on a laptop with no database,
which is the difference between a number that gets produced and one that does not.
"""
import hashlib
import math
import random
import re
from collections import Counter
from typing import Any, Optional, Protocol

WORD = re.compile(r"[a-z0-9']+")


class Index(Protocol):
    name: str

    def rank(self, brief: str, limit: int) -> list[int]:
        """The actor ids this brief retrieves, best first."""


def roles_first(actor: dict[str, Any], bio_chars: int = 400) -> str:
    """The same facts, reordered, with the biography cut short.

    `all-MiniLM-L6-v2` reads 256 tokens and silently drops the rest, and the
    product's `actor_description` puts the biography — often a thousand words of
    career summary — before the past roles. On this corpus that truncates 683 of
    1,159 records and cuts the roles off entirely for 503 of them, which is a
    real defect and looked like the obvious explanation for the semantic index's
    poor showing.

    It is not. Reordering changes recall@10 by one brief out of 52, so the
    truncation costs almost nothing here and the limitation is the model's grasp
    of the task, not the text it was given. The variant stays in the run because
    ruling an explanation out is worth as much as confirming one, and without it
    the truncation would have been reported as the cause.
    """
    roles = "; ".join(actor.get("past_roles") or [])
    bio = (actor.get("biography") or "")[:bio_chars]
    return f"Roles: {roles}. Actor: {actor.get('name', '')}. Biography: {bio}".strip()


class SemanticIndex:
    """What the product does: embed the brief, rank by cosine similarity."""

    name = "semantic"

    def __init__(self, actors: list[dict[str, Any]], model: Any, describe: Any = None):
        import numpy

        describe = describe or (lambda a: a["description"])
        self.ids = [int(a["actor_id"]) for a in actors]
        self.model = model
        # normalize_embeddings makes cosine similarity a dot product, which is
        # also what pgvector's `<=>` computes over these same vectors.
        self.matrix = numpy.asarray(
            model.encode([describe(a) for a in actors], normalize_embeddings=True,
                         batch_size=64, show_progress_bar=False),
            dtype="float32",
        )

    def rank(self, brief: str, limit: int) -> list[int]:
        import numpy

        query = numpy.asarray(
            self.model.encode([brief], normalize_embeddings=True, show_progress_bar=False)[0],
            dtype="float32",
        )
        order = numpy.argsort(-(self.matrix @ query))[:limit]
        return [self.ids[i] for i in order]


class LexicalIndex:
    """TF-IDF cosine over the same text. No model, no dependency, no excuse."""

    name = "lexical"

    def __init__(self, actors: list[dict[str, Any]]):
        self.ids = [int(a["actor_id"]) for a in actors]
        documents = [Counter(WORD.findall(a["description"].lower())) for a in actors]
        appearances: Counter = Counter()
        for document in documents:
            appearances.update(document.keys())
        total = len(documents) or 1
        self.idf = {
            word: math.log(total / (1 + count)) + 1.0 for word, count in appearances.items()
        }
        self.vectors = [self._weigh(document) for document in documents]

    def _weigh(self, counts: Counter) -> dict[str, float]:
        weighted = {
            word: (1 + math.log(n)) * self.idf.get(word, 0.0) for word, n in counts.items()
        }
        length = math.sqrt(sum(v * v for v in weighted.values())) or 1.0
        return {word: value / length for word, value in weighted.items()}

    def rank(self, brief: str, limit: int) -> list[int]:
        query = self._weigh(Counter(WORD.findall(brief.lower())))
        scored = [
            (sum(weight * vector.get(word, 0.0) for word, weight in query.items()), index)
            for index, vector in enumerate(self.vectors)
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [self.ids[index] for _score, index in scored[:limit]]


class ChanceIndex:
    """A shuffle, seeded per brief so a re-run gives the same answer."""

    name = "chance"

    def __init__(self, actors: list[dict[str, Any]], seed: int = 20260920):
        self.ids = [int(a["actor_id"]) for a in actors]
        self.seed = seed

    def rank(self, brief: str, limit: int) -> list[int]:
        digest = hashlib.sha256(f"{self.seed}:{brief}".encode()).hexdigest()[:8]
        shuffled = list(self.ids)
        random.Random(int(digest, 16)).shuffle(shuffled)
        return shuffled[:limit]


def build(kind: str, actors: list[dict[str, Any]], model: Optional[Any] = None) -> Index:
    if kind in ("semantic", "semantic_roles_first"):
        if model is None:
            raise ValueError("the semantic index needs an embedding model")
        index = SemanticIndex(actors, model, roles_first if kind.endswith("roles_first") else None)
        index.name = kind
        return index
    if kind == "lexical":
        return LexicalIndex(actors)
    if kind == "chance":
        return ChanceIndex(actors)
    raise ValueError(f"no index called {kind!r}")
