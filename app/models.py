# app/models.py
from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Date, DateTime, Float, Text
)
from sqlalchemy.sql import func
import datetime

metadata = MetaData()

activities = Table(
    "activities",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user", String(100), nullable=False, index=True),
    Column("date", Date, nullable=False),
    Column("client", String(200)),
    Column("activity_type", String(50)),
    Column("duration_min", Integer, default=0),
    Column("outcome", String(200)),
    Column("deal_value", Float, default=0.0),
    Column("stage", String(50)),
    Column("followup_date", Date, nullable=True),
    Column("notes", Text, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)
