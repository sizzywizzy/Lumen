"""Reset an account's password from the command line.

CineNode sends no email, so there is no self-service "forgot password" flow.
Whoever runs the backend resets a password here instead:

    cd backend
    python scripts/reset_password.py you@example.com

The new password is prompted for, never echoed and never taken as an argument,
so it stays out of shell history. Every existing session for the account is
revoked, so the change signs it out everywhere. Talks to whichever store the
API is using (local JSON under backend/.state/auth/, or Supabase), so run it
with the same interpreter and .env as the server.
"""
import argparse
import getpass
import sys
from pathlib import Path

# Runnable as `python scripts/reset_password.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import security  # noqa: E402
from core.auth.models import User  # noqa: E402
from services import auth_store  # noqa: E402


def reset_password(email: str, new_password: str) -> User:
    """Replace the stored digest and revoke the account's sessions."""
    problem = security.password_problem(new_password)
    if problem:
        raise ValueError(problem)
    user = auth_store.get_user_by_email(email)
    if user is None:
        raise LookupError(f"No account with email {email.strip().lower()!r}.")
    user.password_hash = security.hash_password(new_password)
    auth_store.save_user(user)
    auth_store.delete_sessions_for_user(user.id)
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a CineNode account's password.")
    parser.add_argument("email", help="email of the account to reset")
    args = parser.parse_args()

    user = auth_store.get_user_by_email(args.email)
    if user is None:
        print(f"No account with email {args.email.strip().lower()!r}.", file=sys.stderr)
        return 1
    print(f"Resetting the password for {user.name} <{user.email}>")

    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat new password: "):
        print("Passwords do not match. Nothing changed.", file=sys.stderr)
        return 1
    try:
        reset_password(user.email, password)
    except ValueError as exc:
        print(f"{exc} Nothing changed.", file=sys.stderr)
        return 1
    print("Done. Existing sessions were signed out; sign in with the new password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
