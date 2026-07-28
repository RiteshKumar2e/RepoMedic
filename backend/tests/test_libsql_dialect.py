"""The Turso HTTP dialect.

The failure this guards against is subtle and only appears under load: Turso's
HTTP transport keeps server-side streams that expire after a few seconds idle,
so a *reused* connection dies silently between queries. The analysis pipeline
clones a repository for several seconds mid-transaction, which is exactly long
enough to hit it — the symptom is ``stream not found`` far from the cause.
"""

from __future__ import annotations

import pytest
from sqlalchemy.pool import NullPool

from app.db.libsql_dialect import SQLiteDialect_libsql_http


def test_connections_are_never_pooled():
    """A reused connection is a rotted connection against Turso over HTTP."""
    assert SQLiteDialect_libsql_http.get_pool_class(None) is NullPool


@pytest.mark.parametrize(
    "message",
    [
        'Hrana: `api error: `status=404 Not Found, body={"error":"stream not found: 5a84eb81:cc75b"}``',
        "stream expired",
        "invalid baton",
        "HRANA protocol failure",
    ],
)
def test_stream_errors_are_reported_as_disconnects(message):
    """So pool pre-ping discards the connection instead of failing the request."""
    dialect = SQLiteDialect_libsql_http()

    assert dialect.is_disconnect(ValueError(message), None, None) is True


@pytest.mark.parametrize(
    "message",
    [
        "UNIQUE constraint failed: users.email",
        "no such table: widgets",
        "syntax error near SELECT",
    ],
)
def test_genuine_sql_errors_are_not_disconnects(message):
    """Misreporting these would hide real bugs behind a silent retry."""
    dialect = SQLiteDialect_libsql_http()

    assert dialect.is_disconnect(ValueError(message), None, None) is False


def test_connect_args_extract_the_auth_token():
    from sqlalchemy.engine.url import make_url

    dialect = SQLiteDialect_libsql_http()
    url = make_url("sqlite+libsql_http://db-org.turso.io?authToken=secret-token")

    args, options = dialect.create_connect_args(url)

    assert args == ["libsql://db-org.turso.io"]
    assert options["auth_token"] == "secret-token"
    # Sessions are per-request across a thread pool.
    assert options["_check_same_thread"] is False
