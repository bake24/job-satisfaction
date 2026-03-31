from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def current_year() -> int:
    return datetime.utcnow().year


def current_quarter() -> int:
    return ((datetime.utcnow().month - 1) // 3) + 1


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Driver(Base, TimestampMixin):
    __tablename__ = "drivers"
    __table_args__ = (
        UniqueConstraint("unit_number", "first_name", "last_name", name="uq_driver_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_number: Mapped[str] = mapped_column(String(32), index=True)
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    language_default: Mapped[str | None] = mapped_column(String(8), nullable=True)

    survey_runs: Mapped[list["SurveyRun"]] = relationship(back_populates="driver")
    dispatcher_assignments: Mapped[list["DriverDispatcher"]] = relationship(
        back_populates="driver",
        cascade="all, delete-orphan",
    )


class Dispatcher(Base, TimestampMixin):
    __tablename__ = "dispatchers"
    __table_args__ = (
        UniqueConstraint("first_name", "last_name", name="uq_dispatcher_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    driver_assignments: Mapped[list["DriverDispatcher"]] = relationship(back_populates="dispatcher")
    responses: Mapped[list["Response"]] = relationship(back_populates="related_dispatcher")


class DriverDispatcher(Base, TimestampMixin):
    __tablename__ = "driver_dispatchers"
    __table_args__ = (
        UniqueConstraint("driver_id", "slot_number", name="uq_driver_dispatcher_slot"),
        UniqueConstraint("driver_id", "dispatcher_id", name="uq_driver_dispatcher_pair"),
        CheckConstraint("slot_number >= 1 AND slot_number <= 4", name="ck_driver_dispatchers_slot_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), index=True)
    dispatcher_id: Mapped[int] = mapped_column(ForeignKey("dispatchers.id", ondelete="CASCADE"), index=True)
    slot_number: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    driver: Mapped[Driver] = relationship(back_populates="dispatcher_assignments")
    dispatcher: Mapped[Dispatcher] = relationship(back_populates="driver_assignments")


class TelegramUser(Base, TimestampMixin):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="en")

    survey_runs: Mapped[list["SurveyRun"]] = relationship(back_populates="user")


class SurveyRun(Base, TimestampMixin):
    __tablename__ = "survey_runs"
    __table_args__ = (
        UniqueConstraint("driver_id", "survey_month", name="uq_driver_month"),
        UniqueConstraint("driver_id", "survey_year", "survey_quarter", name="uq_driver_quarter"),
        CheckConstraint("survey_quarter >= 1 AND survey_quarter <= 4", name="ck_survey_runs_quarter_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)

    # Backward-compatible field for the current application logic.
    survey_month: Mapped[str] = mapped_column(String(7), index=True)

    # Forward-compatible quarter-based fields for production PostgreSQL design.
    survey_year: Mapped[int] = mapped_column(Integer, index=True, default=current_year)
    survey_quarter: Mapped[int] = mapped_column(Integer, index=True, default=current_quarter)

    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Snapshot fields retained under existing names to avoid breaking current app logic.
    unit_number: Mapped[str] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64))

    feedback_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["TelegramUser"] = relationship(back_populates="survey_runs")
    driver: Mapped[Driver] = relationship(back_populates="survey_runs")
    responses: Mapped[list["Response"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    exports: Mapped[list["SurveyExport"]] = relationship(back_populates="survey_run", cascade="all, delete-orphan")


class Response(Base, TimestampMixin):
    __tablename__ = "survey_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id", ondelete="CASCADE"), index=True)
    department: Mapped[str] = mapped_column(String(64), index=True)
    question_code: Mapped[str] = mapped_column(String(64), index=True)

    # Keep answer_code for backward compatibility with the current repo/service layer.
    answer_code: Mapped[str] = mapped_column(String(64))
    answer_text: Mapped[str] = mapped_column(Text)

    related_dispatcher_id: Mapped[int | None] = mapped_column(
        ForeignKey("dispatchers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    related_dispatcher_name_snapshot: Mapped[str | None] = mapped_column(String(160), nullable=True)

    run: Mapped[SurveyRun] = relationship(back_populates="responses")
    related_dispatcher: Mapped[Dispatcher | None] = relationship(back_populates="responses")


class SurveyExport(Base, TimestampMixin):
    __tablename__ = "survey_exports"
    __table_args__ = (
        UniqueConstraint("survey_run_id", "target", name="uq_survey_export_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id", ondelete="CASCADE"), index=True)
    target: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    survey_run: Mapped[SurveyRun] = relationship(back_populates="exports")


