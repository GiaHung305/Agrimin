import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    province: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=True)
    guardrail_status: Mapped[str] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class FarmProfile(Base):
    __tablename__ = "farm_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="Nông trại của tôi")
    province: Mapped[str] = mapped_column(String(100), nullable=True)
    crop: Mapped[str] = mapped_column(String(100), nullable=True)
    area_ha: Mapped[float] = mapped_column(Float, nullable=True)
    farming_style: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FarmTask(Base):
    __tablename__ = "farm_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class FarmLog(Base):
    __tablename__ = "farm_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class FarmPlot(Base):
    __tablename__ = "farm_plots"
    __table_args__ = (
        Index("ix_farm_plot_owner_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    farm_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    area_ha: Mapped[float] = mapped_column(Float, nullable=True)
    location_note: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CropSeason(Base):
    __tablename__ = "crop_seasons"
    __table_args__ = (
        Index("ix_crop_season_owner_status", "user_id", "status"),
        Index(
            "uq_crop_season_active_plot",
            "plot_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    plot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_plots.id"), index=True)
    crop: Mapped[str] = mapped_column(String(100))
    variety: Mapped[str] = mapped_column(String(100), nullable=True)
    growth_stage: Mapped[str] = mapped_column(String(100), nullable=True)
    planted_on: Mapped[date] = mapped_column(Date, nullable=True)
    expected_harvest_on: Mapped[date] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    ended_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FarmMonitoringSchedule(Base):
    __tablename__ = "farm_monitoring_schedules"
    __table_args__ = (
        Index("ix_farm_monitoring_due", "status", "next_run_at"),
        Index("ix_farm_monitoring_owner", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    farm_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_profiles.id"), index=True)
    plot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_plots.id"), nullable=True, index=True)
    crop_season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop_seasons.id"), nullable=True, index=True)
    crop: Mapped[str] = mapped_column(String(100))
    province: Mapped[str] = mapped_column(String(100))
    reminder_type: Mapped[str] = mapped_column(String(50), default="tomato_disease_risk")
    frequency_hours: Mapped[int] = mapped_column(Integer, default=24)
    notification_scope: Mapped[str] = mapped_column(String(30), default="in_app")
    status: Mapped[str] = mapped_column(String(20), default="active")
    consent_granted_at: Mapped[datetime] = mapped_column(DateTime)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FarmWeatherObservation(Base):
    __tablename__ = "farm_weather_observations"
    __table_args__ = (
        Index("ix_farm_weather_observation_owner", "user_id", "observed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_monitoring_schedules.id"), index=True)
    run_key: Mapped[str] = mapped_column(String(255), unique=True)
    source: Mapped[str] = mapped_column(String(100))
    forecast_date: Mapped[date] = mapped_column(Date)
    inputs: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class FarmRiskPrediction(Base):
    __tablename__ = "farm_risk_predictions"
    __table_args__ = (
        Index("ix_farm_risk_prediction_owner", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_monitoring_schedules.id"), index=True)
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_weather_observations.id"), unique=True)
    risk_type: Mapped[str] = mapped_column(String(80))
    risk_level: Mapped[str] = mapped_column(String(20), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    policy_version: Mapped[str] = mapped_column(String(50))
    inputs: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FarmRecommendation(Base):
    __tablename__ = "farm_recommendations"
    __table_args__ = (
        Index("ix_farm_recommendation_owner", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_monitoring_schedules.id"), index=True)
    prediction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_risk_predictions.id"), unique=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notifications.id"), nullable=True, unique=True)
    pending_action_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pending_actions.id"), nullable=True, unique=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_tasks.id"), nullable=True, unique=True)
    kind: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(512), unique=True)
    platform: Mapped[str] = mapped_column(String(30))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index("ix_notification_delivery_due", "status", "next_attempt_at"),
        Index("ix_notification_delivery_owner", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notifications.id"), index=True)
    device_token_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("device_tokens.id"), index=True)
    delivery_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    author: Mapped[str] = mapped_column(String(255), nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=True)
    published_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(default=True)
    file_key: Mapped[str] = mapped_column(String(500), nullable=True)
class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    qdrant_point_id: Mapped[str] = mapped_column(String(255))
    chunk_index: Mapped[int] = mapped_column()
    content_preview: Mapped[str] = mapped_column(Text)

class MemoryFact(Base):
    __tablename__ = "memory_facts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    fact_text: Mapped[str] = mapped_column(Text)
    source_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class GoldenDataset(Base):
    __tablename__ = "golden_dataset"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str] = mapped_column(Text)
    expected_citation: Mapped[str] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=True)
    dataset_version: Mapped[str] = mapped_column(String(50), default="v1", index=True)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    model_version: Mapped[str] = mapped_column(String(100), nullable=True)
    accuracy: Mapped[float] = mapped_column(Float, nullable=True)
    citation_score: Mapped[float] = mapped_column(Float, nullable=True)
    hallucination_rate: Mapped[float] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(default=False)
    dataset_version: Mapped[str] = mapped_column(String(50), default="v1", index=True)
