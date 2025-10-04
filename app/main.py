# app/main.py
import os, json, asyncio, math
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from datetime import date, datetime, timedelta
from pydantic import BaseModel
from databases import Database
from sqlalchemy import create_engine
from app import models, schemas

# Config
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kam_assistant.db")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # change if you want

# Init
database = Database(DATABASE_URL)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
models.metadata.create_all(engine)

app = FastAPI(title="KAM Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper DB wrappers
async def fetch_recent(user: str, limit: int = 500):
    query = models.activities.select().where(models.activities.c.user == user).order_by(models.activities.c.date.desc()).limit(limit)
    return await database.fetch_all(query)

# Basic ingest endpoint
@app.post("/ingest", summary="Ingest activity rows")
async def ingest(rows: List[schemas.ActivityIn]):
    if not rows:
        raise HTTPException(status_code=400, detail="No rows provided")
    query = models.activities.insert()
    values = []
    for r in rows:
        values.append({
            "user": r.user,
            "date": r.date,
            "client": r.client,
            "activity_type": r.activity_type,
            "duration_min": r.duration_min,
            "outcome": r.outcome,
            "deal_value": r.deal_value or 0.0,
            "stage": r.stage,
            "followup_date": r.followup_date,
            "notes": r.notes
        })
    await database.connect()
    async with database.transaction():
        await database.execute_many(query=query, values=values)
    await database.disconnect()
    return {"status":"ok", "inserted": len(values)}

# Dashboard endpoint (quick KPIs)
@app.get("/dashboard/{user}", summary="Quick KPIs")
async def dashboard(user: str):
    await database.connect()
    rows = await fetch_recent(user, limit=1000)
    await database.disconnect()
    if not rows:
        return {"mtd_revenue":0, "deals_closed":0, "avg_deal":0, "pipeline_value":0, "last_rows": []}

    mtd_start = date.today().replace(day=1)
    mtd_revenue = sum(r["deal_value"] or 0 for r in rows if r["date"] >= mtd_start)
    deals_closed = sum(1 for r in rows if (r["stage"] or "").lower() == "closed won")
    avg_deal = (mtd_revenue / deals_closed) if deals_closed else 0
    pipeline_value = sum(r["deal_value"] or 0 for r in rows if (r["stage"] or "").lower() not in ("closed won","closed lost","lost"))
    last_rows = [dict(r) for r in rows[:20]]
    return {"mtd_revenue": mtd_revenue, "deals_closed": deals_closed, "avg_deal": avg_deal, "pipeline_value": pipeline_value, "last_rows": last_rows}

# Analysis: small local pre-check + OpenAI call
def build_prompt_for_openai(user_rows, rules=None):
    # Keep prompt compact: send last 60 rows + small summary
    sample = user_rows[:60]
    totals = {
        "rows": len(user_rows),
        "mtd_revenue": sum(r["deal_value"] or 0 for r in user_rows if r["date"] >= date.today().replace(day=1))
    }
    system = "You are an expert sales analyst. Output JSON only with keys: morning_priorities (list), kpis (dict), warnings (list), recommended_actions (list). Use short plain sentences."
    user = f"Data snapshot summary: {json.dumps(totals)}.\nLatest activities sample (JSON): {json.dumps([dict(r) for r in sample], default=str)}\nRules: stage names Prospect,Demo,Proposal,Negotiation,Closed Won,Closed Lost. Flag deals stuck if followup_date older than 14 days. Output JSON only."
    return system, user

import requests
def call_openai(system_prompt, user_prompt, max_tokens=700):
    if not OPENAI_API_KEY:
        return {"error":"OPENAI_API_KEY not set in env"}
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"}
    body = {
        "model": MODEL_NAME,
        "messages": [
            {"role":"system","content": system_prompt},
            {"role":"user","content": user_prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2
    }
    resp = requests.post(OPENAI_API_URL, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()

@app.get("/analyze/{user}", summary="Run AI analysis (may call OpenAI)")
async def analyze(user: str):
    await database.connect()
    rows = await fetch_recent(user, limit=500)
    await database.disconnect()
    if not rows:
        return {"message":"no data for user"}
    system, user_prompt = build_prompt_for_openai(rows)
    try:
        ai = call_openai(system, user_prompt)
    except Exception as e:
        return {"error":"OpenAI call failed", "details": str(e)}
    return {"openai_response": ai}

# Startup / Shutdown events
@app.on_event("startup")
async def startup():
    if not database.is_connected:
        await database.connect()

@app.on_event("shutdown")
async def shutdown():
    if database.is_connected:
        await database.disconnect()
