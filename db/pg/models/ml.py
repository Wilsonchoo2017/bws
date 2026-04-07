"""ML models: MlFeatureStore, MlModelRun, MlPredictionSnapshot."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.pg.base import Base


class MlFeatureStore(Base):
    __tablename__ = "ml_feature_store"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_number: Mapped[str] = mapped_column(String(20), nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_return: Mapped[float | None] = mapped_column(Float)
    target_profitable: Mapped[bool | None] = mapped_column(Boolean)
    features_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("set_number", "horizon_months", name="uq_ml_feature_store"),
    )


class MlModelRun(Base):
    __tablename__ = "ml_model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    task: Mapped[str] = mapped_column(String(50), nullable=False)
    r_squared: Mapped[float | None] = mapped_column(Float)
    roc_auc: Mapped[float | None] = mapped_column(Float)
    hit_rate: Mapped[float | None] = mapped_column(Float)
    quintile_spread: Mapped[float | None] = mapped_column(Float)
    n_train: Mapped[int | None] = mapped_column(Integer)
    n_test: Mapped[int | None] = mapped_column(Integer)
    feature_count: Mapped[int | None] = mapped_column(Integer)
    artifact_path: Mapped[str | None] = mapped_column(Text)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MlPredictionSnapshot(Base):
    __tablename__ = "ml_prediction_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    set_number: Mapped[str] = mapped_column(String(20), nullable=False)
    predicted_growth_pct: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(20))
    tier: Mapped[int | None] = mapped_column(Integer)
    model_version: Mapped[str | None] = mapped_column(String(50))
    actual_growth_pct: Mapped[float | None] = mapped_column(Float)
    actual_measured_at: Mapped[date | None] = mapped_column(Date)
    avoid_probability: Mapped[float | None] = mapped_column(Float)
    buy_signal: Mapped[bool | None] = mapped_column(Boolean)
    kelly_fraction: Mapped[float | None] = mapped_column(Float)
    win_probability: Mapped[float | None] = mapped_column(Float)
    interval_lower: Mapped[float | None] = mapped_column(Float)
    interval_upper: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("snapshot_date", "set_number", name="uq_ml_prediction_snapshot"),
    )
