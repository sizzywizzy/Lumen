"""Generate embeddings for all actors already loaded into PostgreSQL."""
import argparse

from services.casting_kb.embeddings import generate_actor_embeddings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    print(f"Generated {generate_actor_embeddings(args.limit)} actor embeddings")


if __name__ == "__main__":
    main()