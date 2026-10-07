"""
Accounts: only a 9-digit SDU address with a strong password gets in, and the
main page stays closed until it does.
"""
import json

import pytest

from app.auth import AuthError, hash_password, normalise_email, password_problems, verify_password
from conftest import TEST_EMAIL, TEST_NAME, TEST_PASSWORD


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
                    json={"email": "240103048@gmail.com", "password": TEST_PASSWORD, "full_name": TEST_NAME})
    assert res.status_code == 400
    assert res.json()["detail"]["field"] == "email"


def test_registration_is_refused_for_a_weak_password(anon):
    res = anon.post("/api/auth/register",
                    json={"email": "111222333@sdu.edu.kz", "password": "qwerty", "full_name": TEST_NAME})
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
    res = client.post("/api/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD,
                                                  "full_name": TEST_NAME})
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


# ---------------------------------------------------------- forgotten password
RESET_EMAIL = "555666777@sdu.edu.kz"
RESET_OLD = "Campus#2026"
RESET_NEW = "Library!2027"


@pytest.fixture()
def mailbox(monkeypatch):
    """A deployed site with mail set up; every reset link it would mail lands here."""
    import app.main
    sent = []
    monkeypatch.setattr(app.main, "mail_configured", lambda: True)
    monkeypatch.setattr(app.main, "PUBLIC_URL", "https://campus.example")
    monkeypatch.setattr(app.main, "send_reset_link",
                        lambda email, link, minutes: sent.append((email, link)))
    return sent


@pytest.fixture()
def account(anon):
    """A fresh account with a known password, and the reset rows of any earlier test gone."""
    from app.main import users
    with users._connect() as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (RESET_EMAIL,))
    anon.post("/api/auth/register", json={"email": RESET_EMAIL, "password": RESET_OLD,
                                          "full_name": TEST_NAME})
    anon.post("/api/auth/logout")
    return RESET_EMAIL


def _token(link):
    assert "#reset=" in link, "the token belongs in the fragment, never in the query string"
    return link.split("#reset=", 1)[1]


def test_forgot_answers_the_same_for_unknown_and_known_addresses(anon, account, mailbox):
    known = anon.post("/api/auth/forgot", json={"email": account})
    unknown = anon.post("/api/auth/forgot", json={"email": "123123123@sdu.edu.kz"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [email for email, _ in mailbox] == [account], "only a real account gets a link"


def test_forgot_refuses_an_address_that_is_not_an_sdu_one(anon, mailbox):
    res = anon.post("/api/auth/forgot", json={"email": "someone@gmail.com"})
    assert res.status_code == 400 and res.json()["detail"]["field"] == "email"
    assert mailbox == []


def test_a_reset_link_sets_a_new_password_once(anon, account, mailbox):
    anon.post("/api/auth/forgot", json={"email": account})
    token = _token(mailbox[-1][1])

    weak = anon.post("/api/auth/reset", json={"token": token, "password": "qwerty"})
    assert weak.status_code == 400 and weak.json()["detail"]["field"] == "password"

    done = anon.post("/api/auth/reset", json={"token": token, "password": RESET_NEW})
    assert done.status_code == 200 and done.json()["user"]["email"] == account
    assert anon.get("/api/auth/me").status_code == 200, "a reset signs you straight in"

    assert anon.post("/api/auth/login", json={"email": account, "password": RESET_OLD}).status_code == 400
    assert anon.post("/api/auth/login", json={"email": account, "password": RESET_NEW}).status_code == 200

    again = anon.post("/api/auth/reset", json={"token": token, "password": "Another#2028"})
    assert again.status_code == 400 and again.json()["detail"]["field"] == "token"


def test_a_reset_signs_the_account_out_everywhere_else(account, mailbox):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as elsewhere, TestClient(app) as here:
        elsewhere.post("/api/auth/login", json={"email": account, "password": RESET_OLD})
        assert elsewhere.get("/api/auth/me").status_code == 200
        here.post("/api/auth/forgot", json={"email": account})
        here.post("/api/auth/reset", json={"token": _token(mailbox[-1][1]), "password": RESET_NEW})
        assert elsewhere.get("/api/auth/me").status_code == 401


def test_an_expired_or_made_up_link_is_refused(anon, account, mailbox):
    from app.main import users
    anon.post("/api/auth/forgot", json={"email": account})
    token = _token(mailbox[-1][1])
    with users._connect() as conn:
        conn.execute("UPDATE password_resets SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert anon.post("/api/auth/reset", json={"token": token, "password": RESET_NEW}).status_code == 400
    assert anon.post("/api/auth/reset", json={"token": "made-up", "password": RESET_NEW}).status_code == 400


def test_asking_twice_in_a_minute_sends_one_link(anon, account, mailbox):
    anon.post("/api/auth/forgot", json={"email": account})
    anon.post("/api/auth/forgot", json={"email": account})
    assert len(mailbox) == 1


def test_only_the_hash_of_a_reset_token_is_stored(anon, account, mailbox):
    from app.main import users
    anon.post("/api/auth/forgot", json={"email": account})
    token = _token(mailbox[-1][1])
    with users._connect() as conn:
        stored = [r[0] for r in conn.execute("SELECT token_hash FROM password_resets")]
    assert token not in stored and len(stored) == 1


def test_the_sign_in_page_offers_the_reset(anon):
    page = anon.get("/login").text
    assert "Forgot password?" in page



# ------------------------------------------------------------------ the full name
@pytest.mark.parametrize("name", ["", "   ", "A", "12345", "Aidana 2", "<script>", "x" * 81])
def test_an_account_needs_a_real_full_name(anon, name):
    res = anon.post("/api/auth/register", json={"email": "333444555@sdu.edu.kz",
                                                "password": TEST_PASSWORD, "full_name": name})
    assert res.status_code == 400 and res.json()["detail"]["field"] == "full_name"


def test_registering_without_a_name_field_is_refused(anon):
    res = anon.post("/api/auth/register", json={"email": "333444555@sdu.edu.kz", "password": TEST_PASSWORD})
    assert res.status_code == 400 and res.json()["detail"]["field"] == "full_name"


@pytest.mark.parametrize("name, stored", [
    ("Aidana Serikova", "Aidana Serikova"),
    ("  Әлия   Нұрланқызы ", "Әлия Нұрланқызы"),        # Kazakh letters, spaces tidied
    ("Анна-Мария О’Нил", "Анна-Мария О’Нил"),           # hyphen and apostrophe inside a name
])
def test_names_in_any_alphabet_are_accepted_and_tidied(name, stored):
    from app.auth import normalise_name
    assert normalise_name(name) == stored



# ------------------------------------------- how the reset link reaches a person
def test_a_deployed_site_mails_a_link_to_its_own_address(anon, account, mailbox):
    res = anon.post("/api/auth/forgot", json={"email": account}).json()
    assert res["delivery"] == "email" and "reset_url" not in res
    assert mailbox[-1][1].startswith("https://campus.example/login?mode=reset#reset=")


def test_a_deployed_site_without_mail_says_so_instead_of_promising_a_letter(anon, account, monkeypatch):
    import app.main
    monkeypatch.setattr(app.main, "mail_configured", lambda: False)
    monkeypatch.setattr(app.main, "PUBLIC_URL", "https://campus.example")
    res = anon.post("/api/auth/forgot", json={"email": account}).json()
    assert res["ok"] is False and res["delivery"] == "unavailable" and "reset_url" not in res


@pytest.fixture()
def on_this_computer(account, monkeypatch):
    """The app run on a developer's machine: no mail server, opened at localhost."""
    import app.main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app.main, "mail_configured", lambda: False)
    monkeypatch.setattr(app.main, "PUBLIC_URL", "")
    with TestClient(app.main.app, base_url="http://localhost:8000", client=("127.0.0.1", 50000)) as c:
        yield c


def test_on_this_computer_the_link_is_handed_over_and_resets_the_password(on_this_computer, account):
    res = on_this_computer.post("/api/auth/forgot", json={"email": account}).json()
    assert res["delivery"] == "screen" and res["reset_url"].startswith("/login?mode=reset#reset=")
    token = res["reset_url"].split("#reset=", 1)[1]
    # the link opens the sign-in page in reset mode, even for a browser that is signed in
    page = on_this_computer.get(res["reset_url"].split("#")[0], follow_redirects=False)
    assert page.status_code == 200 and 'id="field-confirm"' in page.text
    done = on_this_computer.post("/api/auth/reset", json={"token": token, "password": RESET_NEW})
    assert done.status_code == 200
    assert on_this_computer.post("/api/auth/login", json={"email": account, "password": RESET_NEW}).status_code == 200


def test_on_this_computer_an_unknown_address_gets_no_link(on_this_computer):
    res = on_this_computer.post("/api/auth/forgot", json={"email": "121212121@sdu.edu.kz"}).json()
    assert res["delivery"] == "screen" and res["reset_url"] is None


@pytest.mark.parametrize("client_host, host", [("10.0.0.7", "localhost:8000"),        # someone else
                                               ("127.0.0.1", "campus.example")])     # a proxy in front
def test_the_link_is_never_shown_to_anyone_but_this_computer(account, monkeypatch, client_host, host):
    import app.main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app.main, "mail_configured", lambda: False)
    monkeypatch.setattr(app.main, "PUBLIC_URL", "")
    with TestClient(app.main.app, base_url=f"http://{host}", client=(client_host, 50000)) as c:
        res = c.post("/api/auth/forgot", json={"email": account}).json()
    assert res["delivery"] == "unavailable" and "reset_url" not in res


def test_the_mailer_sends_a_real_letter_through_smtp(monkeypatch):
    """The SMTP conversation itself, against a stand-in server."""
    import app.mailer as mailer
    talk = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            talk["server"] = (host, port)
        def starttls(self, context):
            talk["tls"] = True
        def login(self, user, password):
            talk["login"] = (user, password)
        def send_message(self, msg):
            talk["msg"] = msg
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    for key, value in {"CAMPUS_SMTP_HOST": "smtp.example", "CAMPUS_SMTP_PORT": "587",
                       "CAMPUS_SMTP_USER": "noreply@example", "CAMPUS_SMTP_PASSWORD": "app-password"}.items():
        monkeypatch.setenv(key, value)
    mailer.send_reset_link("240103048@sdu.edu.kz", "https://campus.example/login?mode=reset#reset=abc", 30)
    assert talk["server"] == ("smtp.example", 587) and talk["tls"]
    assert talk["login"] == ("noreply@example", "app-password")
    msg = talk["msg"]
    assert msg["To"] == "240103048@sdu.edu.kz" and "Reset" in msg["Subject"]
    assert "https://campus.example/login?mode=reset#reset=abc" in msg.get_body(("plain",)).get_content()
    assert 'href="https://campus.example/login?mode=reset#reset=abc"' in msg.get_body(("html",)).get_content()


class _BrevoReply:
    status = 201
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False


def test_brevo_carries_the_letter_over_https(monkeypatch):
    """With a Brevo key the mail goes through Brevo's HTTP API, not SMTP: hosts
    such as free Render block the SMTP ports."""
    import app.mailer as mailer
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"], sent["headers"] = request.full_url, dict(request.header_items())
        sent["body"] = json.loads(request.data)
        return _BrevoReply()

    monkeypatch.setattr(mailer.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mailer.smtplib, "SMTP", lambda *a, **k: pytest.fail("SMTP used instead of Brevo"))
    monkeypatch.setenv("CAMPUS_BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("CAMPUS_SMTP_HOST", "smtp.example")
    monkeypatch.setenv("CAMPUS_MAIL_FROM", "campus@example.org")
    assert mailer.mail_configured()
    assert mailer.send_reset_link("240103048@sdu.edu.kz", "https://campus.example/login?mode=reset#reset=abc", 30)
    assert sent["url"] == "https://api.brevo.com/v3/smtp/email"
    assert sent["headers"]["Api-key"] == "xkeysib-test"
    body = sent["body"]
    assert body["sender"]["email"] == "campus@example.org"
    assert body["to"] == [{"email": "240103048@sdu.edu.kz"}]
    assert "#reset=abc" in body["textContent"] and "#reset=abc" in body["htmlContent"]


def test_a_brevo_refusal_is_logged_not_raised(monkeypatch, caplog):
    """An unverified sender or a wrong key: the person was already answered, so
    the reason goes to the log for whoever runs the site."""
    import io
    import urllib.error
    import app.mailer as mailer

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {},
                                     io.BytesIO(b'{"message":"sender not valid"}'))

    monkeypatch.setattr(mailer.urllib.request, "urlopen", refuse)
    monkeypatch.setenv("CAMPUS_BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("CAMPUS_MAIL_FROM", "campus@example.org")
    assert mailer.send_reset_link("240103048@sdu.edu.kz", "https://campus.example/x", 30) is False
    assert "sender not valid" in caplog.text
