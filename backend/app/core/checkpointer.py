from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings

_checkpointer_cm = None
_checkpointer = None


def _to_psycopg_conn_string(database_url: str) -> str:
    """Convert SQLAlchemy's asyncpg URL into a URL psycopg accepts."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


async def init_checkpointer():
    """Create the singleton PostgresSaver and its tables during app startup."""
    global _checkpointer_cm, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    conn_string = _to_psycopg_conn_string(settings.database_url)
    checkpointer_cm = AsyncPostgresSaver.from_conn_string(conn_string)
    try:
        checkpointer = await checkpointer_cm.__aenter__()
        await checkpointer.setup()
    except BaseException as exc:
        await checkpointer_cm.__aexit__(type(exc), exc, exc.__traceback__)
        raise

    _checkpointer_cm = checkpointer_cm
    _checkpointer = checkpointer
    return _checkpointer


async def close_checkpointer():
    """Close the connection and clear singleton state for shutdown/restart."""
    global _checkpointer_cm, _checkpointer
    checkpointer_cm = _checkpointer_cm
    _checkpointer_cm = None
    _checkpointer = None
    if checkpointer_cm:
        await checkpointer_cm.__aexit__(None, None, None)


def get_checkpointer():
    if _checkpointer is None:
        raise RuntimeError("Postgres checkpointer has not been initialized")
    return _checkpointer
