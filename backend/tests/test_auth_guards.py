"""Authentication and per-production authorization guards.

The rule under test: knowing a project_id grants nothing. A non-member gets a
404 (not a 403) so they cannot even confirm a production exists; a member whose
role is too low gets a 403.
"""
import pytest
from fastapi import HTTPException

from core.auth import security
from core.auth.deps import current_user, optional_user, require_member, require_owner, require_producer
from core.auth.models import Session, role_at_least


def _status(excinfo):
    return excinfo.value.status_code


# ------------------------------------------------------------------- 401 --


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer   ", "token abc123", "Basic abc123"])
def test_missing_or_malformed_authorization_header_is_401(header):
    with pytest.raises(HTTPException) as exc:
        current_user(authorization=header)
    assert _status(exc) == 401


def test_unknown_session_token_is_401(state_dir):
    with pytest.raises(HTTPException) as exc:
        current_user(authorization=f"Bearer {security.new_token()}")
    assert _status(exc) == 401


def test_expired_session_is_401_and_is_cleaned_up(state_dir, signed_in):
    from services import auth_store

    _, token = signed_in(ttl_hours=-1)
    with pytest.raises(HTTPException) as exc:
        current_user(authorization=f"Bearer {token}")

    assert _status(exc) == 401
    assert "expired" in exc.value.detail.lower()
    assert auth_store.get_session(token) is None, "expired session should be deleted"


def test_session_for_a_deleted_account_is_401(state_dir, make_user):
    from services import auth_store

    make_user()
    token = security.new_token()
    auth_store.save_session(
        Session(
            token_fingerprint=security.fingerprint(token),
            user_id="usr_does_not_exist",
            created_at=security.iso(security.now()),
            expires_at=security.expires_in(12),
        )
    )
    with pytest.raises(HTTPException) as exc:
        current_user(authorization=f"Bearer {token}")

    assert _status(exc) == 401
    assert "no longer exists" in exc.value.detail


def test_valid_session_resolves_to_the_user(state_dir, signed_in):
    user, token = signed_in()
    assert current_user(authorization=f"Bearer {token}").id == user.id
    assert current_user(authorization=f"bearer {token}").id == user.id, "scheme is case-insensitive"


def test_optional_user_returns_none_instead_of_raising(state_dir):
    assert optional_user(authorization=None) is None
    assert optional_user(authorization="Bearer nonsense") is None


# ------------------------------------------------------------------- 404 --


def test_non_member_gets_404_not_403(state_dir, make_user, make_production):
    """A stranger must not be able to tell a production apart from a typo."""
    owner, _ = make_user(email="ava@neonnights.film")
    make_production(owner, "PROJ_NEON_NIGHTS")

    outsider, _ = make_user(email="mallory@other.studio")
    with pytest.raises(HTTPException) as exc:
        require_member(project_id="PROJ_NEON_NIGHTS", user=outsider)
    assert _status(exc) == 404


def test_the_real_and_imaginary_404s_are_indistinguishable(state_dir, make_user, make_production):
    """Same status and same wording, or the 404 leaks existence anyway."""
    owner, _ = make_user(email="ava@neonnights.film")
    make_production(owner, "PROJ_NEON_NIGHTS")
    outsider, _ = make_user(email="mallory@other.studio")

    with pytest.raises(HTTPException) as real:
        require_member(project_id="PROJ_NEON_NIGHTS", user=outsider)
    with pytest.raises(HTTPException) as fake:
        require_member(project_id="PROJ_NEON_NIGHTS_TYPO", user=outsider)

    assert _status(real) == _status(fake) == 404
    assert real.value.detail.replace("PROJ_NEON_NIGHTS", "X") == \
           fake.value.detail.replace("PROJ_NEON_NIGHTS_TYPO", "X")


# ------------------------------------------------------------------- 403 --


def test_crew_can_read_but_cannot_write(state_dir, make_user, make_production):
    user, _ = make_user()
    make_production(user, "PROJ_NEON_NIGHTS", role="crew")

    assert require_member(project_id="PROJ_NEON_NIGHTS", user=user).role == "crew"
    with pytest.raises(HTTPException) as exc:
        require_producer(project_id="PROJ_NEON_NIGHTS", user=user)
    assert _status(exc) == 403
    assert "read-only" in exc.value.detail


def test_producer_can_write_but_is_not_an_owner(state_dir, make_user, make_production):
    user, _ = make_user()
    make_production(user, "PROJ_NEON_NIGHTS", role="producer")

    assert require_producer(project_id="PROJ_NEON_NIGHTS", user=user).role == "producer"
    with pytest.raises(HTTPException) as exc:
        require_owner(project_id="PROJ_NEON_NIGHTS", user=user)
    assert _status(exc) == 403


def test_owner_passes_every_guard(state_dir, make_user, make_production):
    user, _ = make_user()
    make_production(user, "PROJ_NEON_NIGHTS", role="owner")
    for guard in (require_member, require_producer, require_owner):
        assert guard(project_id="PROJ_NEON_NIGHTS", user=user).role == "owner"


def test_a_role_on_one_production_does_not_carry_to_another(state_dir, make_user, make_production):
    user, _ = make_user()
    make_production(user, "PROJ_NEON_NIGHTS", role="owner")
    make_production(user, "PROJ_MACBETH", role="crew")

    assert require_owner(project_id="PROJ_NEON_NIGHTS", user=user).role == "owner"
    with pytest.raises(HTTPException) as exc:
        require_owner(project_id="PROJ_MACBETH", user=user)
    assert _status(exc) == 403


@pytest.mark.parametrize(
    "role, minimum, expected",
    [("owner", "producer", True), ("producer", "producer", True), ("crew", "producer", False),
     ("producer", "owner", False), ("stowaway", "crew", False)],
)
def test_role_ranking(role, minimum, expected):
    assert role_at_least(role, minimum) is expected
