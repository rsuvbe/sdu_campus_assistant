"""
Shared fixtures.

The API needs a signed-in SDU account, so the test client registers one in a
throw-away users database. CAMPUS_USERS_DB has to be set before app.main is
imported, which is why it happens at module level here.
"""
import os
import tempfile
from pathlib import Path

import pytest

TMP_USERS_DB = Path(tempfile.mkdtemp(prefix="campus-tests-")) / "users.db"
os.environ["CAMPUS_USERS_DB"] = str(TMP_USERS_DB)

from fastapi.testclient import TestClient      # noqa: E402  (after the env var)

from app.main import app                       # noqa: E402

TEST_EMAIL = "240103048@sdu.edu.kz"
TEST_PASSWORD = "Campus#2026"
TEST_NAME = "Aidana Serikova"


@pytest.fixture(scope="session")
def client():
    """A client with a signed-in account; its cookie jar keeps the session."""
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD,
                                           "full_name": TEST_NAME})
        yield c


@pytest.fixture()
def anon():
    """A client that has never signed in."""
    with TestClient(app) as c:
        yield c
