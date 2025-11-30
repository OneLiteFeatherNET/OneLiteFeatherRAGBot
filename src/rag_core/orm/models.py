from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, Text, Integer, TIMESTAMP, func, JSON
from pgvector.sqlalchemy import Vector
from sqlalchemy import Table, MetaData, Column


class Base(DeclarativeBase):
    pass


class RagSetting(Base):
    __tablename__ = "rag_settings"

    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_id: Mapped[Optional[int]] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class RagChecksum(Base):
    __tablename__ = "rag_checksums"

    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


def make_chunk_table(metadata: Optional[MetaData], table_name: str, embed_dim: int) -> Table:
    """Return a SQLAlchemy Table for data_<table_name> with pgvector column.

    The llama-index PGVectorStore creates tables named data_<name>. This helper maps that table
    so you can run ORM-style queries for stats/maintenance.
    """
    md = metadata or MetaData()
    return Table(
        f"data_{table_name}",
        md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("text", Text),
        Column("metadata_", JSON),
        Column("node_id", Text),
        Column("embedding", Vector(dim=embed_dim)),
    )

