"""Database schema for CourseMind's structured source-of-truth data.

SQLite is the local default; the same SQLAlchemy models accept a PostgreSQL
database URL in deployment. Vector documents and chat traces are deliberately
not placed here yet: this module stores transactional academic and community
data only.
"""
from typing import Any, Dict, Generator, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class StudentProfileRow(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    programme: Mapped[str] = mapped_column(String(16), nullable=False)
    major_track: Mapped[str] = mapped_column(String(16), nullable=False, default="DSC")
    catalogue_year: Mapped[str] = mapped_column(String(32), nullable=False)
    max_credits: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    unavailable_slots: Mapped[list] = mapped_column(JSON, default=list)
    interests: Mapped[list] = mapped_column(JSON, default=list)
    workload_preference: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    course_records: Mapped[list["StudentCourseRow"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class StudentCourseRow(Base):
    __tablename__ = "student_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.user_id"), nullable=False, index=True)
    course_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    term_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    profile: Mapped[StudentProfileRow] = relationship(back_populates="course_records")


class CourseRow(Base):
    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(16), nullable=False)
    offering_academic_unit: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    duration_terms: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    catalogue_year: Mapped[str] = mapped_column(String(32), nullable=False)
    official_url: Mapped[str] = mapped_column(String(1024), default="")
    prerequisite_json: Mapped[dict] = mapped_column(JSON, default=dict)
    minimum_major_credits: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class SourceDocumentRow(Base):
    """Versioned source material used as official retrieval evidence.

    Text is stored separately from transactional course/profile data so that a
    future vector index can be rebuilt from these records without changing the
    academic source of truth.
    """

    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    catalogue_year: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    term_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    source_status: Mapped[str] = mapped_column(String(16), nullable=False, default="published", index=True)
    verified_at: Mapped[str] = mapped_column(String(40), nullable=False)
    course_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)


class CourseOfferingRow(Base):
    """A point-in-time official course section for one academic term."""

    __tablename__ = "course_offerings"
    __table_args__ = (UniqueConstraint("course_code", "term_id", "section", name="uq_offering_section"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"), nullable=False, index=True)
    term_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    slots: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unavailable", index=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    verified_at: Mapped[str] = mapped_column(String(40), nullable=False)
    credit_units: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allowed_majors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    allowed_programmes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    access_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    crn: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    component_type: Mapped[str] = mapped_column(String(16), nullable=False, default="class")
    campus: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    web_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    available_seats: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    waitlist_available: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    date_start: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    date_end: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    building: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    room: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    instructor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    medium: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ProgrammeCourseScopeRow(Base):
    """Courses explicitly permitted by a programme version."""

    __tablename__ = "programme_course_scopes"
    __table_args__ = (UniqueConstraint("programme", "catalogue_year", "course_code", name="uq_programme_course_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    programme: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    catalogue_year: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)


class CourseReviewRow(Base):
    __tablename__ = "course_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("student_profiles.user_id"), nullable=False, index=True)
    term_id: Mapped[str] = mapped_column(String(32), nullable=False)
    overall_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    workload: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    assessment_pressure: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    instructor_or_section: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=True)


def build_engine(database_url: str):
    options: Dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    return create_engine(database_url, **options)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    _ensure_legacy_schema(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _ensure_legacy_schema(engine) -> None:
    """Apply tiny additive migrations needed by the local starter database."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(courses)")}
        if "offering_academic_unit" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE courses ADD COLUMN offering_academic_unit VARCHAR(128) NOT NULL DEFAULT ''"
            )
        if "duration_terms" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE courses ADD COLUMN duration_terms INTEGER NOT NULL DEFAULT 1"
            )
        if "minimum_major_credits" not in columns:
            connection.exec_driver_sql("ALTER TABLE courses ADD COLUMN minimum_major_credits INTEGER")
        offering_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(course_offerings)")}
        if offering_columns and "credit_units" not in offering_columns:
            connection.exec_driver_sql("ALTER TABLE course_offerings ADD COLUMN credit_units INTEGER")
        if offering_columns and "allowed_majors" not in offering_columns:
            connection.exec_driver_sql("ALTER TABLE course_offerings ADD COLUMN allowed_majors JSON NOT NULL DEFAULT '[]'")
        if offering_columns and "allowed_programmes" not in offering_columns:
            connection.exec_driver_sql("ALTER TABLE course_offerings ADD COLUMN allowed_programmes JSON NOT NULL DEFAULT '[]'")
        if offering_columns and "access_note" not in offering_columns:
            connection.exec_driver_sql("ALTER TABLE course_offerings ADD COLUMN access_note TEXT NOT NULL DEFAULT ''")
        additive = {
            "crn": "VARCHAR(32)", "component_type": "VARCHAR(16) NOT NULL DEFAULT 'class'",
            "campus": "VARCHAR(64) NOT NULL DEFAULT ''", "web_enabled": "BOOLEAN",
            "level": "VARCHAR(8) NOT NULL DEFAULT ''", "available_seats": "INTEGER",
            "capacity": "INTEGER", "waitlist_available": "INTEGER",
            "date_start": "VARCHAR(16)", "date_end": "VARCHAR(16)",
            "building": "VARCHAR(64) NOT NULL DEFAULT ''", "room": "VARCHAR(64) NOT NULL DEFAULT ''",
            "instructor": "VARCHAR(128) NOT NULL DEFAULT ''", "medium": "VARCHAR(64) NOT NULL DEFAULT ''",
            "is_snapshot": "BOOLEAN NOT NULL DEFAULT 0",
        }
        for name, definition in additive.items():
            if offering_columns and name not in offering_columns:
                connection.exec_driver_sql(f"ALTER TABLE course_offerings ADD COLUMN {name} {definition}")
        profile_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(student_profiles)")}
        if profile_columns and "major_track" not in profile_columns:
            connection.exec_driver_sql("ALTER TABLE student_profiles ADD COLUMN major_track VARCHAR(16) NOT NULL DEFAULT 'DSC'")


def session_dependency(factory) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
