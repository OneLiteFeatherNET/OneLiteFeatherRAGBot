from __future__ import annotations

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Iterator

from ..types import Db


def make_dsn(db: Db) -> str:
    return f"postgresql+psycopg2://{db.user}:{db.password}@{db.host}:{db.port}/{db.database}"


def create_engine_from_db(db: Db):
    return create_engine(make_dsn(db), pool_pre_ping=True)


def session_factory(db: Db):
    eng = create_engine_from_db(db)
    return sessionmaker(bind=eng)


@contextmanager
def session_scope(db: Db):
    Session = session_factory(db)
    sess = Session()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

