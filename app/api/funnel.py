"""Own visitor funnel for the static landing pages (no external analytics).

POST /api/ev      - anonymous step events from /lp pages (sendBeacon, text/plain). Never names or phone numbers.
GET  /api/ev/...  - aggregated funnel + session timelines, readable only with the key whose SHA-256 is FUNNEL_KEY_SHA256
                    (the repo is public, so the key itself is never committed).
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import text

from app.db import engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ev")

FUNNEL_KEY_SHA256 = "8cbf3a8be5f3ca4140fa7229a9dc421c6f0792829cc446697bb018a49a1fc046"
MAX_EVENTS = 60
_table_ready = False

DDL = """
CREATE TABLE IF NOT EXISTS lp_events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    sid VARCHAR(24) NOT NULL,
    page VARCHAR(40) NOT NULL,
    ev VARCHAR(24) NOT NULL,
    t_ms INTEGER,
    data VARCHAR(120)
);
CREATE INDEX IF NOT EXISTS lp_events_ts ON lp_events (ts);
CREATE INDEX IF NOT EXISTS lp_events_sid ON lp_events (sid);
"""


async def _ensure_table():
    global _table_ready
    if _table_ready:
        return
    async with engine.begin() as conn:
        for stmt in [s for s in DDL.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    _table_ready = True


def _clip(v, n):
    return str(v)[:n] if v is not None else None


@router.post("")
async def collect(request: Request):
    # Never fail the page: bad input is dropped silently.
    try:
        body = json.loads((await request.body())[:20000] or b"{}")
        sid, page, events = _clip(body.get("s"), 24), _clip(body.get("p"), 40), body.get("e") or []
        if not sid or not page or not isinstance(events, list):
            return Response(status_code=204)
        rows = []
        for e in events[:MAX_EVENTS]:
            if not isinstance(e, list) or not e:
                continue
            ms = e[1] if len(e) > 1 and isinstance(e[1], int) else None
            rows.append({"sid": sid, "page": page, "ev": _clip(e[0], 24), "t_ms": ms,
                         "data": _clip(e[2], 120) if len(e) > 2 and e[2] is not None else None})
        if rows:
            await _ensure_table()
            async with engine.begin() as conn:
                await conn.execute(text("INSERT INTO lp_events (sid, page, ev, t_ms, data) VALUES (:sid, :page, :ev, :t_ms, :data)"), rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lp_events collect failed: %s", exc)
    return Response(status_code=204)


def _check(key: str):
    if hashlib.sha256((key or "").encode()).hexdigest() != FUNNEL_KEY_SHA256:
        raise HTTPException(status_code=404)


STEPS = ["view", "s25", "s50", "s75", "s100", "cta", "offer", "nm_in", "ph_in", "submit", "ph_err", "send_err", "ok"]


@router.get("/funnel")
async def funnel(key: str = Query(""), hours: float = Query(24, ge=0.1, le=24 * 30)):
    """Distinct visitors reaching each step, per page, plus error breakdowns and time on page."""
    _check(key)
    await _ensure_table()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with engine.connect() as conn:
        steps = (await conn.execute(text(
            "SELECT page, ev, COUNT(DISTINCT sid) FROM lp_events WHERE ts >= :s GROUP BY page, ev"), {"s": since})).all()
        errs = (await conn.execute(text(
            "SELECT page, ev, data, COUNT(*) FROM lp_events WHERE ts >= :s AND ev IN ('ph_err','nm_err','send_err','offer','leave_step') "
            "GROUP BY page, ev, data ORDER BY 4 DESC"), {"s": since})).all()
        secs = (await conn.execute(text(
            "SELECT page, percentile_cont(0.5) WITHIN GROUP (ORDER BY t_ms) / 1000.0, COUNT(*) FROM lp_events "
            "WHERE ts >= :s AND ev = 'leave' GROUP BY page"), {"s": since})).all()
    out = {}
    for page, ev, n in steps:
        out.setdefault(page, {"steps": {}, "details": {}, "median_seconds_on_page": None})["steps"][ev] = n
    for page, ev, data, n in errs:
        out.setdefault(page, {"steps": {}, "details": {}, "median_seconds_on_page": None})["details"].setdefault(ev, {})[data or "-"] = n
    for page, med, _n in secs:
        out.setdefault(page, {"steps": {}, "details": {}, "median_seconds_on_page": None})["median_seconds_on_page"] = round(med or 0, 1)
    for p in out.values():
        p["steps"] = {k: p["steps"][k] for k in STEPS + sorted(set(p["steps"]) - set(STEPS)) if k in p["steps"]}
    return {"since": since.isoformat(), "pages": out}


@router.get("/sessions")
async def sessions(key: str = Query(""), page: str = Query(""), hours: float = Query(24, ge=0.1, le=24 * 30),
                   limit: int = Query(40, ge=1, le=300), only_form: bool = Query(False)):
    """Step-by-step timeline of recent visitors (what each one did, in order, with seconds)."""
    _check(key)
    await _ensure_table()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    cond = "ts >= :s" + (" AND page = :p" if page else "")
    sub = (f"SELECT sid FROM lp_events WHERE {cond}" + (" AND ev = 'cta'" if only_form else "")
           + " GROUP BY sid ORDER BY MAX(ts) DESC LIMIT :n")
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            f"SELECT sid, page, ev, t_ms, data FROM lp_events WHERE sid IN ({sub}) ORDER BY sid, id"),
            {"s": since, "p": page, "n": limit})).all()
    out = {}
    for sid, pg, ev, ms, data in rows:
        s = out.setdefault(sid, {"page": pg, "steps": []})
        s["steps"].append(f"{(ms or 0) / 1000:.0f}s {ev}" + (f" ({data})" if data else ""))
    return list(out.values())
