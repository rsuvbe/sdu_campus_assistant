"""
Accounts: only a 9-digit SDU address with a strong password gets in, and the
main page stays closed until it does.
"""
import pytest

from app.auth import AuthError, hash_password, normalise_email, password_problems, verify_password
from conftest import TEST_EMAIL, TEST_PASSWORD


# ------------------------------------------------------------------ the rules
@pytest.mark.parametrize("email", [
    "240103048@sdu.edu.kz",
    "999999999@SDU.EDU.KZ",     # case does not matter
    "  240103048@sdu.edu.kz ",  # nor does stray whitespace around it
])
def test_sdu_addresses_are_accepted(email):
    assert normalise_email(email).endswith("@sdu.edu.kz")


@pytest.mark.parametrize("email", [
    "24010304@sdu.edu.kz",       # 8 digits
    "2401030489@sdu.edu.kz",     # 10 digits
    "aidana@sdu.edu.kz",         # not digits
    "240103048@gmail.com",       # not SDU
    "240103048@student.sdu.edu.kz",
    "240103048sdu.edu.kz",
    "",
])
def test_everything_else_is_refused(email):
    with pytest.raises(AuthError):
        normalise_email(email)


@pytest.mark.parametrize("password, missing", [
    ("Short1!", "at least 8 characters"),
    ("campus#2026", "an uppercase letter"),
    ("CAMPUS#2026", "a lowercase letter"),
    ("CampusPass!", "a digit"),
    ("Campus2026", "a special character"),
    ("Campus #2026", "no spaces"),
    ("Sdu240103048!", "something other than your student ID"),
    ("Password1!", "a password that isn't on the common-password list"),
])
def test_weak_passwords_are_named_rule_by_rule(password, missing):
    assert missing in password_problems(password, TEST_EMAIL)


def test_a_good_password_breaks_no_rule():
    assert password_problems(TEST_PASSWORD, TEST_EMAIL) == []


def test_hashes_are_salted_and_verifiable():
    first, second = hash_password(TEST_PASSWORD), hash_password(TEST_PASSWORD)
    assert first != second, "the same password must not produce the same hash twice"
    assert TEST_PASSWORD not in first
    assert verify_password(TEST_PASSWORD, first)
    assert not verify_password(TEST_PASSWORD + "x", first)


# ------------------------------------------------------------------- the gate
def test_the_app_is_closed_without_an_account(anon):
    assert anon.get("/api/search", params={"q": "D103"}).status_code == 401
    assert anon.get("/api/map").status_code == 401
    assert anon.get("/", follow_redirects=False).headers["location"] == "/login"
    assert "Sign in" in anon.get("/login").text


def test_registration_is_refused_for_a_non_sdu_address(anon):
    res = anon.post("/api/auth/register",
                    json={"email": "240103048@gmail.com", "password": TEST_PASSWORD})
    assert res.status_code == 400
    assert res.json()["detail"]["field"] == "email"


def test_registration_is_refused_for_a_weak_password(anon):
    res = anon.post("/api/auth/register",
                    json={"email": "111222333@sdu.edu.kz", "password": "qwerty"})
    assert res.status_code == 400
    assert res.json()["detail"]["field"] == "password"


def test_sign_in_sign_out_round_trip(anon):
    anon.post("/api/auth/register", json={"email": "220900111@sdu.edu.kz",
                                          "password": "Almaty$7road", "full_name": "Test User"})
    assert anon.get("/api/auth/me").json()["user"]["student_id"] == "220900111"
    assert anon.get("/api/search", params={"q": "D103"}).status_code == 200

    anon.post("/api/auth/logout")
    assert anon.get("/api/auth/me").status_code == 401

    bad = anon.post("/api/auth/login", json={"email": "220900111@sdu.edu.kz", "password": "Wrong#1234"})
    assert bad.status_code == 400
    assert anon.post("/api/auth/login", json={"email": "220900111@sdu.edu.kz",
                                              "password": "Almaty$7road"}).status_code == 200
    assert anon.get("/api/auth/me").status_code == 200


def test_an_account_cannot_be_registered_twice(client):
    res = client.post("/api/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]["message"]


# --------------------------------------------------------- the seeded account
def test_a_seeded_account_survives_a_restart(tmp_path):
    """Free hosting wipes the disk on restart, so one account is recreated."""
    from app.auth import UserStore, seed_account
    db = tmp_path / "users.db"
    spec = "221100334@sdu.edu.kz:Kaskelen#42road"

    assert seed_account(UserStore(db), spec) == "221100334@sdu.edu.kz"
    store = UserStore(db)
    assert store.exists("221100334@sdu.edu.kz")
    assert store.authenticate("221100334@sdu.edu.kz", "Kaskelen#42road")["student_id"] == "221100334"

    # running again must not fail or change the password
    assert seed_account(store, spec) == "221100334@sdu.edu.kz"
    assert store.authenticate("221100334@sdu.edu.kz", "Kaskelen#42road")

    # and a fresh disk gets the account back
    fresh = UserStore(tmp_path / "wiped.db")
    assert not fresh.exists("221100334@sdu.edu.kz")
    seed_account(fresh, spec)
    assert fresh.exists("221100334@sdu.edu.kz")


@pytest.mark.parametrize("spec", [
    "", "240103048@sdu.edu.kz", "240103048@gmail.com:Campus#2026",
    "240103048@sdu.edu.kz:weak", ":Campus#2026",
])
def test_a_bad_seed_is_ignored_rather_than_breaking_the_deployment(tmp_path, spec):
    from app.auth import UserStore, seed_account
    store = UserStore(tmp_path / "users.db")
    assert seed_account(store, spec) is None


# ------------------------------------------------------------------ visitors
# US1 names students, staff AND visitors. A visitor has no university address,
# so they come in without an account and get everything US1 covers.
def test_a_visitor_can_come_in_without_an_account(anon):
    assert anon.get("/api/search", params={"q": "D103"}).status_code == 401

    body = anon.post("/api/auth/guest").json()
    assert body["user"]["role"] == "visitor"
    assert body["user"]["email"] is None

    assert anon.get("/api/auth/me").json()["user"]["role"] == "visitor"
    for path, params in [("/api/search", {"q": "Where is the Business School?"}),
                         ("/api/map", None), ("/api/services", None), ("/api/stats", None)]:
        assert anon.get(path, params=params).status_code == 200, path
    assert anon.get("/", follow_redirects=False).status_code == 200


def test_a_visitor_is_kept_out_of_anything_personal(anon):
    """The hook the later sprints hang their own features on."""
    from app.main import ROLE_VISITOR, require_account
    from fastapi import HTTPException

    anon.post("/api/auth/guest")
    visitor = anon.get("/api/auth/me").json()["user"]
    assert visitor["role"] == ROLE_VISITOR
    with pytest.raises(HTTPException) as raised:
        require_account(visitor)
    assert raised.value.status_code == 403

    member = {"user_id": 1, "role": "student"}
    assert require_account(member) is member


def test_leaving_ends_the_visitor_session(anon):
    anon.post("/api/auth/guest")
    assert anon.get("/api/auth/me").status_code == 200
    anon.post("/api/auth/logout")
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.get("/", follow_redirects=False).headers["location"] == "/login"


def test_an_account_still_signs_in_as_itself(client):
    assert client.get("/api/auth/me").json()["user"]["role"] == "student"
