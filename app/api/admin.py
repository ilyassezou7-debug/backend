import hmac as _hmac
import hashlib
import time
import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.db import get_db
from app.models import Order
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

PRODUCT_NAMES: dict[str, str] = {
    "breath_drops": "Breath Drops",
    "foot_spray": "Foot Spray",
    "nail_serum": "Nail Serum",
}

VALID_STATUSES = {
    "new", "confirmed", "processing", "shipped",
    "delivered", "cancelled", "returned",
    "sent_to_sheet", "sheet_failed",
}

# ── Auth helpers ──────────────────────────────────────────────────────


def _make_token(username: str, secret: str) -> str:
    ts = str(int(time.time()))
    msg = f"{username}:{ts}"
    sig = _hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    raw = f"{msg}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _check_token(token: str, secret: str, max_age_hours: int = 72) -> str | None:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        parts = raw.split(":")
        if len(parts) != 3:
            return None
        username, ts, sig = parts
        msg = f"{username}:{ts}"
        expected = _hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(sig, expected):
            return None
        if time.time() - int(ts) > max_age_hours * 3600:
            return None
        return username
    except Exception:
        return None


async def require_admin(authorization: Optional[str] = Header(None)) -> str:
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    username = _check_token(authorization[7:], settings.admin_secret_key)
    if not username:
        raise HTTPException(status_code=401, detail="Token invalid or expired")
    return username


# ── Request / response schemas ────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class StatusUpdate(BaseModel):
    status: str


class NoteUpdate(BaseModel):
    notes: str


# ── Helper ────────────────────────────────────────────────────────────


def _parse_date(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid date: {value!r}. Use ISO 8601.")


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/login")
async def admin_login(body: LoginRequest):
    settings = get_settings()
    if body.username != settings.admin_username or body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _make_token(body.username, settings.admin_secret_key)
    logger.info("Admin login: %s", body.username)
    return {"token": token, "username": body.username}


@router.get("/me")
async def admin_me(admin: str = Depends(require_admin)):
    return {"username": admin}


@router.get("/metrics")
async def get_metrics(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    now = datetime.now(timezone.utc)
    start_dt = _parse_date(start, now - timedelta(days=30))
    end_dt = _parse_date(end, now)

    result = await db.execute(
        select(Order).where(Order.created_at >= start_dt, Order.created_at <= end_dt)
    )
    orders = result.scalars().all()

    total_orders = len(orders)
    total_revenue = sum(o.total for o in orders)
    avg_order_value = total_revenue / total_orders if total_orders else 0

    upsell_shown = sum(1 for o in orders if (o.upsell_json or {}).get("shown"))
    upsell_accepted = sum(1 for o in orders if (o.upsell_json or {}).get("accepted"))
    upsell_rate = (upsell_accepted / upsell_shown * 100) if upsell_shown else 0.0

    sheet_ok = sum(1 for o in orders if o.status == "sent_to_sheet")
    sheet_rate = (sheet_ok / total_orders * 100) if total_orders else 0.0

    # Orders by status
    status_counts: dict[str, int] = {}
    for o in orders:
        status_counts[o.status] = status_counts.get(o.status, 0) + 1

    # Daily breakdown (fill every day in range)
    daily: dict[str, dict] = {}
    for o in orders:
        day = o.created_at.strftime("%Y-%m-%d")
        if day not in daily:
            daily[day] = {"date": day, "orders": 0, "revenue": 0}
        daily[day]["orders"] += 1
        daily[day]["revenue"] += o.total

    filled_days = []
    cursor = start_dt.date()
    end_date = end_dt.date()
    while cursor <= end_date:
        ds = cursor.strftime("%Y-%m-%d")
        filled_days.append(daily.get(ds, {"date": ds, "orders": 0, "revenue": 0}))
        cursor += timedelta(days=1)

    # Product breakdown
    product_data: dict[str, dict] = {}
    for o in orders:
        for item in (o.items_json or {}).get("items", []):
            pid = item.get("product_id", "unknown")
            if pid not in product_data:
                product_data[pid] = {
                    "product_id": pid,
                    "name": PRODUCT_NAMES.get(pid, pid),
                    "orders": 0,
                    "revenue": 0,
                    "units": 0,
                }
            product_data[pid]["orders"] += 1
            product_data[pid]["revenue"] += item.get("price", 0) * item.get("quantity", 1)
            product_data[pid]["units"] += item.get("quantity", 1)
    top_products = sorted(product_data.values(), key=lambda x: x["orders"], reverse=True)

    # UTM source breakdown
    utm_counts: dict[str, int] = {}
    for o in orders:
        src = (o.utm_json or {}).get("utm_source") or "Direct"
        utm_counts[src] = utm_counts.get(src, 0) + 1
    top_sources = sorted(
        [{"source": k, "count": v} for k, v in utm_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:8]

    return {
        "period": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "avg_order_value": round(avg_order_value, 0),
        "upsell_shown": upsell_shown,
        "upsell_accepted": upsell_accepted,
        "upsell_rate": round(upsell_rate, 1),
        "sheet_success_rate": round(sheet_rate, 1),
        "orders_by_status": status_counts,
        "orders_by_day": filled_days,
        "top_products": top_products,
        "top_sources": top_sources,
    }


@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    query = select(Order).order_by(Order.created_at.desc())

    if status and status != "all":
        query = query.where(Order.status == status)
    if search:
        s = f"%{search}%"
        query = query.where(
            Order.full_name.ilike(s)
            | Order.phone_e164.contains(search)
            | Order.public_id.ilike(s)
        )
    if start:
        query = query.where(Order.created_at >= _parse_date(start, datetime.min.replace(tzinfo=timezone.utc)))
    if end:
        query = query.where(Order.created_at <= _parse_date(end, datetime.now(timezone.utc)))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
    orders = result.scalars().all()

    return {
        "orders": [
            {
                "id": str(o.id),
                "public_id": o.public_id,
                "full_name": o.full_name,
                "phone": o.phone_e164,
                "status": o.status,
                "total": o.total,
                "currency": o.currency,
                "items_count": len((o.items_json or {}).get("items", [])),
                "items_summary": " / ".join(
                    PRODUCT_NAMES.get(i.get("product_id", ""), i.get("product_id", ""))
                    for i in (o.items_json or {}).get("items", [])
                ),
                "upsell_accepted": bool((o.upsell_json or {}).get("accepted")),
                "utm_source": (o.utm_json or {}).get("utm_source"),
                "notes": getattr(o, "notes", None),
                "created_at": o.created_at.isoformat(),
            }
            for o in orders
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/orders/{public_id}")
async def get_order(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    result = await db.execute(select(Order).where(Order.public_id == public_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    items = [
        {**item, "name": PRODUCT_NAMES.get(item.get("product_id", ""), item.get("product_id", ""))}
        for item in (order.items_json or {}).get("items", [])
    ]

    return {
        "id": str(order.id),
        "public_id": order.public_id,
        "full_name": order.full_name,
        "phone_e164": order.phone_e164,
        "phone_raw": order.phone_raw,
        "status": order.status,
        "subtotal": order.subtotal,
        "shipping": order.shipping,
        "total": order.total,
        "currency": order.currency,
        "items": items,
        "upsell": order.upsell_json,
        "tracking": order.tracking_json,
        "utm": order.utm_json,
        "notes": getattr(order, "notes", None),
        "sheet_sent_at": order.sheet_sent_at.isoformat() if order.sheet_sent_at else None,
        "sheet_error": order.sheet_error,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


@router.patch("/orders/{public_id}/status")
async def update_order_status(
    public_id: str,
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status. Options: {sorted(VALID_STATUSES)}")

    result = await db.execute(select(Order).where(Order.public_id == public_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = body.status
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("Admin updated %s → %s", public_id, body.status)
    return {"ok": True, "public_id": public_id, "status": body.status}


@router.patch("/orders/{public_id}/notes")
async def update_order_notes(
    public_id: str,
    body: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    result = await db.execute(select(Order).where(Order.public_id == public_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if hasattr(order, "notes"):
        order.notes = body.notes  # type: ignore[attr-defined]
        order.updated_at = datetime.now(timezone.utc)
        await db.commit()

    return {"ok": True, "public_id": public_id}
