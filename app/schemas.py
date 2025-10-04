# app/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date

class ActivityIn(BaseModel):
    user: str = Field(..., example="ketan")
    date: date
    client: Optional[str] = None
    activity_type: Optional[str] = None
    duration_min: Optional[int] = 0
    outcome: Optional[str] = None
    deal_value: Optional[float] = 0.0
    stage: Optional[str] = None
    followup_date: Optional[date] = None
    notes: Optional[str] = None

class ActivityOut(ActivityIn):
    id: int
