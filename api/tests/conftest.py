"""Keep database-backed tests away from any database that holds real data.

Several tests delete rows (the retention cleanup removes every expired guest in the database, not only the
ones a test created). api/db.py loads `.env`, so an ordinary dev or production DATABASE_URL used to switch
those tests on. They now run only against an explicit, disposable database:

    TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/just_sing_test  pytest api/tests

The database name must contain "test"; anything else aborts the run. Without TEST_DATABASE_URL the
database tests skip (the header below says so) and DATABASE_URL from `.env` is ignored. Create the schema
first: `DATABASE_URL=<that url> alembic -c api/alembic.ini upgrade head`.
"""
import os

import pytest
from sqlalchemy.engine import make_url

_test_url = os.environ.get("TEST_DATABASE_URL", "")

if _test_url:
    if "test" not in (make_url(_test_url).database or "").lower():
        raise pytest.UsageError(
            "TEST_DATABASE_URL must point at a disposable database whose name contains 'test'; "
            "these tests delete rows.")
    os.environ["DATABASE_URL"] = _test_url
else:
    # An empty value is falsy for the tests' skipif checks, and load_dotenv() never overrides a variable
    # that is already set, so the DATABASE_URL in .env is not picked up.
    os.environ["DATABASE_URL"] = ""


def pytest_report_header(config):
    if _test_url:
        return f"database tests: running against {make_url(_test_url).render_as_string(hide_password=True)}"
    return "database tests: SKIPPED (set TEST_DATABASE_URL to a disposable database with 'test' in its name)"
