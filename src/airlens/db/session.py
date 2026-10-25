from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from airlens.config import database_url


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    return create_engine(
        url or database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 3},
    )


def ping(engine: Engine) -> None:
    """Lempar SQLAlchemyError bila database tidak bisa dijangkau."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
