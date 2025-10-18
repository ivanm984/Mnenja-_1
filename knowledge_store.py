"""Persistent storage layer for the planning knowledge base backed by PostgreSQL."""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import DATABASE_URL, PROJECT_ROOT
from .municipalities import list_municipality_profiles

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarative class for the knowledge base models."""


class KnowledgeMunicipality(Base):
    """Represents a municipality that owns a set of knowledge documents."""

    __tablename__ = "knowledge_municipalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    documents: Mapped[List["KnowledgeDocument"]] = relationship(
        back_populates="municipality", cascade="all, delete-orphan"
    )


class KnowledgeDocument(Base):
    """Represents a structured knowledge document (OPN, priloge, uredba ...)."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    municipality_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_municipalities.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    content_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    content_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # IMPORTANT: attribute name must NOT be 'metadata' (reserved by SQLAlchemy)
    meta: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    embedding: Mapped[Optional[Sequence[float]]] = mapped_column(ARRAY(Float))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64))
    embedding_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    municipality: Mapped[KnowledgeMunicipality] = relationship(back_populates="documents")
    chunks: Mapped[List["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "municipality_id", "document_type", "slug", name="uq_knowledge_documents_slug"
        ),
        Index(
            "ix_knowledge_documents_municipality_type",
            "municipality_id",
            "document_type",
        ),
        Index(
            "ix_knowledge_documents_search",
            text("to_tsvector('simple', coalesce(content_text, ''))"),
            postgresql_using="gin",
        ),
    )


class KnowledgeChunk(Base):
    """Optional chunked representation of documents for vector search."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # IMPORTANT: attribute name must NOT be 'metadata'
    meta: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    embedding: Mapped[Optional[Sequence[float]]] = mapped_column(ARRAY(Float))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64))
    embedding_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunks_index"),
        Index("ix_knowledge_chunks_document", "document_id"),
        Index(
            "ix_knowledge_chunks_search",
            text("to_tsvector('simple', coalesce(content, ''))"),
            postgresql_using="gin",
        ),
    )


@dataclass
class KnowledgeSearchResult:
    """Structured response for full-text search queries."""

    document_id: int
    municipality_slug: str
    document_type: str
    slug: str
    title: Optional[str]
    snippet: str
    score: float


class KnowledgeBaseRepository:
    """Repository handling persistence of the knowledge base in PostgreSQL."""

    def __init__(self, database_url: str):
        if not database_url:
            raise RuntimeError("❌ DATABASE_URL manjka v .env datoteki!")

        self.database_url = database_url
        self.engine = create_engine(self.database_url, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        try:
            Base.metadata.create_all(self.engine)
        except SQLAlchemyError as exc:
            raise RuntimeError(
                "❌ Povezava s PostgreSQL bazo znanja ni uspela. Preverite DATABASE_URL."
            ) from exc

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Napaka pri delu z bazo znanja.")
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Municipality helpers
    # ------------------------------------------------------------------
    def get_or_create_municipality(self, slug: str, name: str) -> KnowledgeMunicipality:
        with self.session_scope() as session:
            stmt = select(KnowledgeMunicipality).where(KnowledgeMunicipality.slug == slug)
            municipality = session.execute(stmt).scalar_one_or_none()
            if municipality:
                return municipality

            municipality = KnowledgeMunicipality(slug=slug, name=name)
            session.add(municipality)
            session.commit()
            session.refresh(municipality)
            return municipality

    def ensure_default_municipality(self) -> KnowledgeMunicipality:
        return self.get_or_create_municipality(DEFAULT_MUNICIPALITY_SLUG, DEFAULT_MUNICIPALITY_NAME)

    # ------------------------------------------------------------------
    # Document helpers
    # ------------------------------------------------------------------
    def upsert_document(
        self,
        municipality: KnowledgeMunicipality,
        document_type: str,
        slug: str,
        title: Optional[str],
        content_json: Dict[str, Any],
        content_text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeDocument:
        # keep parameter name 'metadata' for callers; map to attribute 'meta'
        metadata = metadata or {}
        with self.session_scope() as session:
            stmt = select(KnowledgeDocument).where(
                KnowledgeDocument.municipality_id == municipality.id,
                KnowledgeDocument.document_type == document_type,
                KnowledgeDocument.slug == slug,
            )
            document = session.execute(stmt).scalar_one_or_none()
            if document:
                document.title = title
                document.content_json = content_json
                document.content_text = content_text
                document.meta = metadata  # <— attribute is 'meta'
                document.updated_at = datetime.utcnow()
            else:
                document = KnowledgeDocument(
                    municipality_id=municipality.id,
                    document_type=document_type,
                    slug=slug,
                    title=title,
                    content_json=content_json,
                    content_text=content_text,
                    meta=metadata,  # <— attribute is 'meta'
                )
                session.add(document)
            session.commit()
            session.refresh(document)
            return document

    def load_document_json(
        self, municipality_slug: str, document_type: str, slug: str
    ) -> Dict[str, Any]:
        with self.session_scope() as session:
            stmt = (
                select(KnowledgeDocument.content_json)
                .join(KnowledgeMunicipality)
                .where(
                    KnowledgeMunicipality.slug == municipality_slug,
                    KnowledgeDocument.document_type == document_type,
                    KnowledgeDocument.slug == slug,
                )
            )
            result = session.execute(stmt).scalar_one_or_none()
            return result or {}

    def load_document_text(
        self, municipality_slug: str, document_type: str, slug: str
    ) -> str:
        with self.session_scope() as session:
            stmt = (
                select(KnowledgeDocument.content_text)
                .join(KnowledgeMunicipality)
                .where(
                    KnowledgeMunicipality.slug == municipality_slug,
                    KnowledgeDocument.document_type == document_type,
                    KnowledgeDocument.slug == slug,
                )
            )
            result = session.execute(stmt).scalar_one_or_none()
            return result or ""

    def list_documents(self, municipality_slug: str, document_type: Optional[str] = None) -> List[KnowledgeDocument]:
        with self.session_scope() as session:
            stmt = select(KnowledgeDocument).join(KnowledgeMunicipality).where(
                KnowledgeMunicipality.slug == municipality_slug
            )
            if document_type:
                stmt = stmt.where(KnowledgeDocument.document_type == document_type)
            stmt = stmt.order_by(KnowledgeDocument.slug.asc())
            return list(session.execute(stmt).scalars())

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------
    def search_documents(
        self, query: str, municipality_slug: str, limit: int = 10
    ) -> List[KnowledgeSearchResult]:
        if not query.strip():
            return []

        search_stmt = text(
            """
            SELECT d.id, m.slug AS municipality_slug, d.document_type, d.slug, d.title,
                   ts_headline('simple', d.content_text, plainto_tsquery('simple', :query)) AS snippet,
                   ts_rank_cd(to_tsvector('simple', d.content_text), plainto_tsquery('simple', :query)) AS score
            FROM knowledge_documents AS d
            JOIN knowledge_municipalities AS m ON d.municipality_id = m.id
            WHERE m.slug = :municipality AND to_tsvector('simple', d.content_text) @@ plainto_tsquery('simple', :query)
            ORDER BY score DESC
            LIMIT :limit
            """
        )

        with self.engine.connect() as connection:
            rows = connection.execute(
                search_stmt, {"query": query, "municipality": municipality_slug, "limit": limit}
            )
            return [
                KnowledgeSearchResult(
                    document_id=row["id"],
                    municipality_slug=row["municipality_slug"],
                    document_type=row["document_type"],
                    slug=row["slug"],
                    title=row["title"],
                    snippet=row["snippet"],
                    score=float(row["score"] or 0.0),
                )
                for row in rows
            ]

    # ------------------------------------------------------------------
    # Bootstrapping helpers
    # ------------------------------------------------------------------
    def _json_to_text(self, payload: Any) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload
        if isinstance(payload, (int, float, bool)):
            return str(payload)
        if isinstance(payload, dict):
            parts = []
            for key, value in payload.items():
                parts.append(f"{key}: {self._json_to_text(value)}")
            return "\n".join(parts)
        if isinstance(payload, Iterable):
            return "\n".join(self._json_to_text(item) for item in payload)
        return str(payload)

    def bootstrap_from_files(
        self,
        municipality_slug: str,
        municipality_name: str,
        base_dir: Path | None = None,
    ) -> None:
        base_dir = base_dir or PROJECT_ROOT
        municipality = self.get_or_create_municipality(municipality_slug, municipality_name)

        file_map = [
            ("core", "opn", base_dir / "OPN.json", "OPN katalog"),
            ("priloge", "priloga1", base_dir / "priloga1.json", "Priloga 1"),
            ("priloge", "priloga2", base_dir / "priloga2.json", "Priloga 2"),
            ("priloge", "priloga3-4", base_dir / "priloga3-4.json", "Priloga 3-4"),
            ("priloge", "izrazi", base_dir / "Izrazi.json", "Slovar izrazov"),
            ("priloge", "uredba-objekti", base_dir / "UredbaObjekti.json", "Uredba objekti"),
        ]

        for doc_type, slug, path, title in file_map:
            if not path.exists():
                logger.warning("Datoteka %s ne obstaja, preskakujem.", path)
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    content_json = json.load(handle)
            except (OSError, json.JSONDecodeError):
                logger.exception("Napaka pri nalaganju %s", path)
                continue

            content_text = self._json_to_text(content_json)
            metadata = {"source_path": str(path), "imported_at": datetime.utcnow().isoformat()}
            self.upsert_document(municipality, doc_type, slug, title, content_json, content_text, metadata)

    def ensure_bootstrap(self, municipality_slug: str, municipality_name: str) -> None:
        with self.session_scope() as session:
            stmt = (
                select(func.count(KnowledgeDocument.id))
                .join(KnowledgeMunicipality)
                .where(KnowledgeMunicipality.slug == municipality_slug)
            )
            count = session.execute(stmt).scalar_one() or 0
        if count == 0:
            logger.info(
                "Baza znanja za občino '%s' je prazna. Uvažam podatke iz JSON datotek...",
                municipality_slug,
            )
            self.bootstrap_from_files(municipality_slug, municipality_name)


knowledge_repository = KnowledgeBaseRepository(DATABASE_URL)
for municipality_profile in list_municipality_profiles():
    knowledge_repository.ensure_bootstrap(
        municipality_profile.knowledge_slug, municipality_profile.name
    )

__all__ = [
    "KnowledgeMunicipality",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "KnowledgeSearchResult",
    "KnowledgeBaseRepository",
    "knowledge_repository",
]
