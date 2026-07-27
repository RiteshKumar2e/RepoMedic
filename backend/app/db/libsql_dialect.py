"""SQLAlchemy dialect for Turso over the HTTP transport.

Why this exists
---------------
``sqlalchemy-libsql`` 0.1.0 drives Turso through ``libsql-client``, whose DBAPI
layer registers connection handlers for ``libsql``/``ws``/``wss`` only — every
one of them a WebSocket. Current Turso databases serve the HTTP
``/v2/pipeline`` transport and reject the WebSocket handshake with ``400``, so
that stack cannot connect at all. Upgrading is not an option either:
``sqlalchemy-libsql`` 0.2.0 depends on ``libsql-experimental``, which ships no
wheel for CPython 3.10 on Windows and needs a Rust toolchain to build.

The ``libsql`` package does ship a prebuilt wheel and speaks HTTP, but it is not
quite a DBAPI module: it exposes ``connect``/``Connection``/``Cursor``/``Error``
and nothing else. This module fills in the names SQLAlchemy's SQLite dialect
expects and registers a dialect that uses it.

Registered as ``sqlite+libsql_http``. The stock ``sqlite+libsql`` name is left
alone so the two never race to own the same entry point.
"""

from __future__ import annotations

from typing import Any

import libsql
from sqlalchemy.dialects import registry
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite

DIALECT_NAME = "libsql_http"


class _Dbapi:
    """A :pep:`249`-shaped facade over ``libsql``.

    ``libsql`` raises a single ``Error`` type, so the granular exception classes
    are aliased to it. That keeps SQLAlchemy's ``except dialect.dbapi.X``
    handling working — it catches too broadly rather than missing errors, which
    is the safe direction.
    """

    apilevel = "2.0"
    threadsafety = 1
    paramstyle = libsql.paramstyle

    sqlite_version_info = libsql.sqlite_version_info
    sqlite_version = ".".join(str(part) for part in libsql.sqlite_version_info)

    Error = libsql.Error
    Warning = libsql.Error
    InterfaceError = libsql.Error
    DatabaseError = libsql.Error
    DataError = libsql.Error
    OperationalError = libsql.Error
    IntegrityError = libsql.Error
    InternalError = libsql.Error
    ProgrammingError = libsql.Error
    NotSupportedError = libsql.Error

    Connection = libsql.Connection
    Cursor = libsql.Cursor

    @staticmethod
    def connect(*args: Any, **kwargs: Any) -> Any:
        # SQLAlchemy passes check_same_thread; libsql spells it _check_same_thread.
        if "check_same_thread" in kwargs:
            kwargs["_check_same_thread"] = kwargs.pop("check_same_thread")
        # No equivalent in libsql — statement caching is handled internally.
        kwargs.pop("cached_statements", None)
        kwargs.pop("uri", None)
        kwargs.pop("detect_types", None)
        kwargs.pop("factory", None)
        return libsql.connect(*args, **kwargs)


# SQLAlchemy names dialects `<Database>Dialect_<driver>`; matching that beats PEP 8 here.
class SQLiteDialect_libsql_http(SQLiteDialect_pysqlite):  # noqa: N801
    name = "sqlite"
    driver = DIALECT_NAME
    supports_statement_cache = True

    # The remote database is shared; SQLAlchemy must not assume a local file.
    @classmethod
    def import_dbapi(cls) -> Any:
        return _Dbapi

    # SQLAlchemy 1.4 compatibility.
    dbapi = import_dbapi

    @classmethod
    def get_pool_class(cls, url: Any) -> Any:
        from sqlalchemy.pool import QueuePool

        return QueuePool

    def create_connect_args(self, url: Any) -> tuple[list[Any], dict[str, Any]]:
        """Turn ``sqlite+libsql_http://host?authToken=…`` into libsql arguments."""
        query = dict(url.query)
        auth_token = query.pop("authToken", "") or query.pop("auth_token", "")
        query.pop("secure", None)

        host = url.host or ""
        if url.port:
            host = f"{host}:{url.port}"
        database = f"libsql://{host}{'/' + url.database if url.database else ''}"

        options: dict[str, Any] = {}
        if auth_token:
            options["auth_token"] = auth_token
        # Sessions are per-request across a thread pool, same as the SQLite path.
        options["_check_same_thread"] = False
        return ([database], options)

    def on_connect(self):
        """No per-connection setup.

        pysqlite's ``on_connect`` installs regexp/JSON serializers against the
        stdlib module; none of that applies to the remote driver.
        """
        return None


registry.register(f"sqlite.{DIALECT_NAME}", __name__, "SQLiteDialect_libsql_http")

__all__ = ["DIALECT_NAME", "SQLiteDialect_libsql_http"]
