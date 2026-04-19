"""SQLAlchemy models for Voiceprint Search."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text, Float, Integer, Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Speaker(Base):
    __tablename__ = "speakers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    embeddings: Mapped[list["Embedding"]] = relationship(back_populates="speaker", cascade="all, delete-orphan")


class AudioAsset(Base):
    __tablename__ = "audio_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    speaker_id: Mapped[int | None] = mapped_column(ForeignKey("speakers.id", ondelete="SET NULL"), default=None)
    original_filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(512))
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    sample_rate: Mapped[int | None] = mapped_column(Integer, default=None)
    processing_status: Mapped[str] = mapped_column(String(32), default="pending")
    processing_error: Mapped[str | None] = mapped_column(Text, default=None)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    processing_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    has_speech: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    speaker_id: Mapped[int] = mapped_column(ForeignKey("speakers.id", ondelete="CASCADE"))
    audio_asset_id: Mapped[int] = mapped_column(ForeignKey("audio_assets.id", ondelete="CASCADE"))
    vector = mapped_column(Vector())
    model_version: Mapped[str] = mapped_column(String(100), default="ecapa-tdnn-v1")
    embedding_dim: Mapped[int] = mapped_column(Integer, default=192)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    speaker: Mapped["Speaker"] = relationship(back_populates="embeddings")
