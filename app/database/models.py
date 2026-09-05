"""Database schema — all six tables, defined together in Phase 1.

Why the whole schema now instead of one table per feature phase: Post has
three foreign keys (job, destination, template) and ApplicationMetric has
three more (job, destination, post). Defining them incrementally across
Phases 2-6 would mean forward-referencing tables that don't exist yet, or
circling back to add foreign keys after the fact. Phases 2-6 still build
their CRUD/service/API/UI layers on top of this incrementally, exactly as
specified — only the table definitions are frontloaded.

Tags are a proper many-to-many relationship (Tag + destination_tags join
table), not a comma-separated string column, so "recommend destinations by
matching job tags" (a later-phase feature) can be a plain SQL join instead
of string parsing.
"""

from datetime import date as date_type
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Date, ForeignKey, Integer, Table
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.database import Base
from app.database.enums import JobStatus, Platform, PostingMethod, PostStatus

# ---------------------------------------------------------------------------
# Association table: many-to-many Destination <-> Tag
# ---------------------------------------------------------------------------
destination_tags = Table(
    "destination_tags",
    Base.metadata,
    Column("destination_id", Integer, ForeignKey("destinations.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True, index=True)

    destinations: Mapped[list["Destination"]] = relationship(
        secondary=destination_tags, back_populates="tags"
    )

    def __repr__(self) -> str:
        return f"<Tag {self.name!r}>"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(index=True)
    company: Mapped[Optional[str]]
    location: Mapped[Optional[str]] = mapped_column(index=True)
    salary_min: Mapped[Optional[int]]
    salary_max: Mapped[Optional[int]]
    salary_text: Mapped[Optional[str]]
    employment_type: Mapped[Optional[str]]
    experience: Mapped[Optional[str]]
    education: Mapped[Optional[str]]
    language_requirements: Mapped[Optional[str]]
    requirements: Mapped[Optional[str]]
    responsibilities: Mapped[Optional[str]]
    benefits: Mapped[Optional[str]]
    working_hours: Mapped[Optional[str]]
    application_method: Mapped[Optional[str]]
    application_url: Mapped[Optional[str]]
    contact_phone: Mapped[Optional[str]]
    contact_whatsapp: Mapped[Optional[str]]
    contact_email: Mapped[Optional[str]]
    description: Mapped[Optional[str]]
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus), default=JobStatus.DRAFT, index=True
    )
    # Independent of status: "archived" means hidden from the default view,
    # not "closed". You can archive a Draft you dropped, or a Closed job
    # you're done looking at — the two are orthogonal on purpose.
    archived: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    posts: Mapped[list["Post"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    metrics: Mapped[list["ApplicationMetric"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job {self.id} {self.title!r}>"


class Destination(Base):
    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[Platform] = mapped_column(SAEnum(Platform), index=True)
    name: Mapped[str] = mapped_column(index=True)
    url: Mapped[Optional[str]]
    external_id: Mapped[Optional[str]]  # e.g. Telegram chat_id
    category: Mapped[Optional[str]] = mapped_column(index=True)
    location: Mapped[Optional[str]] = mapped_column(index=True)
    audience: Mapped[Optional[str]]
    language: Mapped[Optional[str]]
    active: Mapped[bool] = mapped_column(default=True, index=True)
    posting_method: Mapped[PostingMethod] = mapped_column(SAEnum(PostingMethod))
    notes: Mapped[Optional[str]]

    # Internal workflow safeguards (Section 19) — not platform-restriction
    # bypasses, just self-imposed rate limits per destination.
    min_posting_interval_minutes: Mapped[Optional[int]]
    daily_posting_limit: Mapped[Optional[int]]
    last_posted_at: Mapped[Optional[datetime]]

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    tags: Mapped[list["Tag"]] = relationship(secondary=destination_tags, back_populates="destinations")
    posts: Mapped[list["Post"]] = relationship(back_populates="destination", cascade="all, delete-orphan")
    metrics: Mapped[list["ApplicationMetric"]] = relationship(
        back_populates="destination", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Destination {self.id} {self.name!r} ({self.platform})>"


class PostTemplate(Base):
    __tablename__ = "post_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    platform: Mapped[Platform] = mapped_column(SAEnum(Platform), index=True)
    language: Mapped[Optional[str]]
    template_text: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    posts: Mapped[list["Post"]] = relationship(back_populates="template")

    def __repr__(self) -> str:
        return f"<PostTemplate {self.id} {self.name!r}>"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    destination_id: Mapped[int] = mapped_column(
        ForeignKey("destinations.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("post_templates.id", ondelete="SET NULL")
    )
    content: Mapped[str]
    media_path: Mapped[Optional[str]]
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(index=True)
    posted_at: Mapped[Optional[datetime]]
    status: Mapped[PostStatus] = mapped_column(SAEnum(PostStatus), default=PostStatus.DRAFT, index=True)
    # Independent of status, same pattern as Job.archived (Phase 2): Section
    # 17 wants "Pause" as a queue action, but Section 6's status list has no
    # Paused value. A paused post stays wherever it is in `status` (usually
    # Queued) — pausing just tells a future scheduler (Phase 10) to leave it
    # alone even once scheduled_at is due, without losing its place in the
    # queue or its scheduled time the way clearing scheduled_at would.
    paused: Mapped[bool] = mapped_column(default=False, index=True)
    error_message: Mapped[Optional[str]]
    external_post_id: Mapped[Optional[str]]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    job: Mapped["Job"] = relationship(back_populates="posts")
    destination: Mapped["Destination"] = relationship(back_populates="posts")
    template: Mapped[Optional["PostTemplate"]] = relationship(back_populates="posts")
    metrics: Mapped[list["ApplicationMetric"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Post {self.id} job={self.job_id} dest={self.destination_id} status={self.status}>"


class ApplicationMetric(Base):
    __tablename__ = "application_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    destination_id: Mapped[int] = mapped_column(
        ForeignKey("destinations.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[Optional[int]] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"), index=True)
    date: Mapped[date_type] = mapped_column(Date, default=date_type.today, index=True)
    views: Mapped[int] = mapped_column(default=0)
    clicks: Mapped[int] = mapped_column(default=0)
    messages: Mapped[int] = mapped_column(default=0)
    applications: Mapped[int] = mapped_column(default=0)
    interviews: Mapped[int] = mapped_column(default=0)
    hires: Mapped[int] = mapped_column(default=0)
    notes: Mapped[Optional[str]]

    job: Mapped["Job"] = relationship(back_populates="metrics")
    destination: Mapped["Destination"] = relationship(back_populates="metrics")
    post: Mapped[Optional["Post"]] = relationship(back_populates="metrics")

    def __repr__(self) -> str:
        return f"<ApplicationMetric job={self.job_id} dest={self.destination_id} date={self.date}>"
