"""Database access helpers (intentionally simplified for the fixture)."""

from app.config import DATABASE_URL


class _Cursor:
    def execute(self, query, params=None):
        raise NotImplementedError("fixture stub")

    def fetchone(self):
        raise NotImplementedError("fixture stub")

    def fetchall(self):
        raise NotImplementedError("fixture stub")


class _Session:
    def query(self, *args, **kwargs):
        raise NotImplementedError("fixture stub")

    def add(self, entity):
        raise NotImplementedError("fixture stub")

    def commit(self):
        raise NotImplementedError("fixture stub")


session = _Session()


def get_cursor() -> _Cursor:
    """Return a raw DBAPI cursor for the configured database."""
    assert DATABASE_URL
    return _Cursor()
