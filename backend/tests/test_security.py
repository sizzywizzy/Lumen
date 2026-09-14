"""Password hashing, token minting and the shared strength rule."""
import pytest

from core.auth import security


def test_hash_has_the_documented_encoding():
    algo, iterations, salt, digest = security.hash_password("neon-nights-2026").split("$")
    assert algo == "pbkdf2_sha256"
    assert int(iterations) == security.PBKDF2_ITERATIONS
    assert len(bytes.fromhex(salt)) == 16
    assert len(bytes.fromhex(digest)) == 32


def test_correct_password_verifies_and_wrong_one_does_not():
    encoded = security.hash_password("neon-nights-2026")
    assert security.verify_password("neon-nights-2026", encoded)
    assert not security.verify_password("wrong-password-1", encoded)
    assert not security.verify_password("NEON-NIGHTS-2026", encoded)


def test_same_password_hashes_differently_each_time():
    """A fresh random salt per hash — identical passwords must not collide."""
    assert security.hash_password("neon-nights-2026") != security.hash_password("neon-nights-2026")


@pytest.mark.parametrize(
    "encoded",
    ["", "not-a-hash", "bcrypt$1$aa$bb", "pbkdf2_sha256$600000$zz", "pbkdf2_sha256$x$aa$bb"],
)
def test_malformed_hashes_fail_closed(encoded):
    assert security.verify_password("neon-nights-2026", encoded) is False


@pytest.mark.parametrize(
    "password, expect",
    [
        ("neon-nights-2026", None),
        ("a1-short", "at least"),
        ("  neon-nights-2026  ", "whitespace"),
        ("1234567890123", "mix letters"),
        ("onlylettershere", "mix letters"),
    ],
)
def test_password_strength_rule(password, expect):
    problem = security.password_problem(password)
    assert problem is None if expect is None else expect in problem


def test_fingerprint_is_deterministic_and_hides_the_token():
    token = security.new_token()
    assert security.fingerprint(token) == security.fingerprint(token)
    assert token not in security.fingerprint(token)
    assert len(security.fingerprint(token)) == 64


def test_tokens_are_unique_and_long_enough():
    tokens = {security.new_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(t) >= 32 for t in tokens)


@pytest.mark.parametrize(
    "value, expired",
    [(security.expires_in(-1), True), (security.expires_in(1), False), ("", True), ("not-a-date", True)],
)
def test_expiry_helpers_fail_closed_on_junk(value, expired):
    assert security.is_expired(value) is expired


def test_project_id_is_slugified_from_the_name():
    assert security.project_id_from_name("Neon Nights") == "PROJ_NEON_NIGHTS"
    assert security.project_id_from_name("  a  b!! ") == "PROJ_A_B"
    assert security.project_id_from_name("!!!") == "PROJ_UNTITLED"
