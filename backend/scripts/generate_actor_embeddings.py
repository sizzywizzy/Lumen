"""Generate embeddings for all actors already loaded into PostgreSQL.

    cd backend
    python scripts/generate_actor_embeddings.py [--limit N]
"""
import argparse
import sys
from pathlib import Path

# Runnable as `python scripts/generate_actor_embeddings.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.casting_kb.embeddings import generate_actor_embeddings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    print(f"Generated {generate_actor_embeddings(args.limit)} actor embeddings")


if __name__ == "__main__":
    main()