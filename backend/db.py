"""
Database module for Data Center Digital Twin.
Stores simulations, telemetry logs, alerts, interventions, and research benchmarks
using SQLite with SQLAlchemy.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Text, DateTime, Boolean, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

DB_PATH = Path(__file__).parent / "datacenter_twin.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SimulationRecord(Base):
    __tablename__ = "simulations"

    id = Column(String(64), primary_key=True, index=True)
    mode = Column(String(32), default="live")
    status = Column(String(32), default="RUNNING")
    scenario_weather = Column(String(64), default="Normal")
    scenario_problem = Column(String(64), default="None")
    scenario_workload = Column(String(64), default="Baseline")
    duration_sec = Column(Integer, default=3600)
    elapsed_sec = Column(Integer, default=0)
    timestep_sec = Column(Float, default=1.0)
    ml_model = Column(String(32), default="xgboost")
    opt_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    summary_json = Column(Text, default="{}")

    telemetry = relationship("TelemetryRecord", back_populates="simulation", cascade="all, delete-orphan")
    alerts = relationship("AlertRecord", back_populates="simulation", cascade="all, delete-orphan")
    interventions = relationship("InterventionRecord", back_populates="simulation", cascade="all, delete-orphan")


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(String(64), ForeignKey("simulations.id"), index=True)
    sim_time_sec = Column(Integer, default=0)
    timestamp = Column(String(32))
    avg_temp = Column(Float)
    max_temp = Column(Float)
    min_temp = Column(Float)
    it_power_kw = Column(Float)
    cooling_power_kw = Column(Float)
    pue = Column(Float)
    hotspot_risk = Column(Float)
    racks_json = Column(Text)

    simulation = relationship("SimulationRecord", back_populates="telemetry")


class AlertRecord(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(String(64), ForeignKey("simulations.id"), index=True)
    timestamp = Column(String(32))
    sim_time = Column(String(32))
    rack_id = Column(String(32), nullable=True)
    severity = Column(String(16))  # CRITICAL, WARNING, INFO
    event_type = Column(String(64))
    description = Column(Text)
    action_taken = Column(String(128), default="Logged")

    simulation = relationship("SimulationRecord", back_populates="alerts")


class InterventionRecord(Base):
    __tablename__ = "interventions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(String(64), ForeignKey("simulations.id"), index=True)
    timestamp = Column(String(32))
    sim_time = Column(String(32))
    action_id = Column(String(64))
    title = Column(String(128))
    peak_temp = Column(Float)
    cooling_energy_kwh = Column(Float)
    safe = Column(Boolean, default=True)
    cost_score = Column(Float)
    was_applied = Column(Boolean, default=False)

    simulation = relationship("SimulationRecord", back_populates="interventions")


class ExperimentRecord(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paradigm = Column(String(64), index=True)
    mae = Column(Float)
    rmse = Column(Float)
    r2 = Column(Float)
    thermal_violations = Column(Integer)
    total_energy_kwh = Column(Float)
    peak_temp = Column(Float)
    intervention_count = Column(Integer)
    energy_savings_pct = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


init_db()
