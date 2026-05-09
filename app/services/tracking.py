import hashlib
import logging
import time
from typing import Any
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)


def sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def phone_digits_country(phone_e164: str) -> str:
    """Strip + and leading zeros, return digits starting from country code."""
    return "".join(ch for ch in phone_e164 if ch.isdigit()).lstrip("0")


async def send_meta_purchase(
    order_id: str,
    event_id: str,
    phone_e164: str,
    total: int,
    items: list[dict],
    tracking: dict,
) -> dict:
    settings = get_settings()
    if not settings.meta_pixel_id or not settings.meta_access_token:
        return {"skipped": True, "reason": "not_configured"}

    ph_hash = sha256(phone_digits_country(phone_e164))

    payload: dict[str, Any] = {
        "data": [{
            "event_name": "Purchase",
            "event_time": int(time.time()),
            "event_id": event_id,
            "action_source": "website",
            "event_source_url": tracking.get("page_url", "https://atlaspure.shop"),
            "user_data": {
                "ph": [ph_hash],
                "client_ip_address": tracking.get("ip", ""),
                "client_user_agent": tracking.get("user_agent", ""),
                "fbp": tracking.get("fbp") or None,
                "fbc": tracking.get("fbc") or None,
            },
            "custom_data": {
                "currency": "MAD",
                "value": total,
                "content_type": "product",
                "contents": [
                    {
                        "id": item["product_id"],
                        "quantity": item.get("unit_count", 1),
                        "item_price": item["price"],
                    }
                    for item in items
                ],
            },
        }],
    }

    if settings.meta_test_event_code:
        payload["test_event_code"] = settings.meta_test_event_code

    url = (
        f"https://graph.facebook.com/v19.0/{settings.meta_pixel_id}/events"
        f"?access_token={settings.meta_access_token}"
    )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            return {"status_code": resp.status_code, "body": resp.json()}
    except Exception as e:
        logger.error("Meta CAPI error: %s", str(e))
        return {"error": str(e)}


async def send_tiktok_purchase(
    order_id: str,
    event_id: str,
    phone_e164: str,
    total: int,
    items: list[dict],
    tracking: dict,
) -> dict:
    settings = get_settings()
    if not settings.tiktok_pixel_id or not settings.tiktok_access_token:
        return {"skipped": True, "reason": "not_configured"}

    ph_hash = sha256(phone_e164)

    event_data: dict[str, Any] = {
        "event": "PlaceAnOrder",
        "event_time": int(time.time()),
        "event_id": event_id,
        "user": {
            "phone": ph_hash,
            "ttp": tracking.get("ttp") or "",
            "ttclid": tracking.get("ttclid") or "",
        },
        "properties": {
            "currency": "MAD",
            "value": total,
            "contents": [
                {
                    "content_id": item["product_id"],
                    "content_type": "product",
                    "quantity": item.get("unit_count", 1),
                    "price": item["price"],
                }
                for item in items
            ],
        },
        "page": {
            "url": tracking.get("page_url", "https://atlaspure.shop"),
            "referrer": tracking.get("referrer") or "",
        },
    }

    payload: dict[str, Any] = {
        "event_source": "web",
        "event_source_id": settings.tiktok_pixel_id,
        "data": [event_data],
    }

    if settings.tiktok_test_event_code:
        payload["test_event_code"] = settings.tiktok_test_event_code

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://business-api.tiktok.com/open_api/v1.3/event/track/",
                json=payload,
                headers={
                    "Access-Token": settings.tiktok_access_token,
                    "Content-Type": "application/json",
                },
            )
            return {"status_code": resp.status_code, "body": resp.json()}
    except Exception as e:
        logger.error("TikTok Events API error: %s", str(e))
        return {"error": str(e)}


async def send_snapchat_purchase(
    order_id: str,
    event_id: str,
    phone_e164: str,
    total: int,
    items: list[dict],
    tracking: dict,
) -> dict:
    settings = get_settings()
    if not settings.snap_pixel_id or not settings.snapchat_access_token:
        return {"skipped": True, "reason": "not_configured"}

    ph_hash = sha256(phone_digits_country(phone_e164))

    payload: dict[str, Any] = {
        "pixel_id": settings.snap_pixel_id,
        "events": [{
            "event_name": "PURCHASE",
            "event_time": int(time.time()),
            "event_id": event_id,
            "action_source": "WEB",
            "user_data": {
                "ph": [ph_hash],
                "client_user_agent": tracking.get("user_agent", ""),
                "client_ip_address": tracking.get("ip", ""),
            },
            "custom_data": {
                "currency": "MAD",
                "value": total,
                "contents": [
                    {
                        "id": item["product_id"],
                        "quantity": item.get("unit_count", 1),
                        "item_price": item["price"],
                    }
                    for item in items
                ],
            },
        }],
    }

    if settings.snap_test_event_code:
        payload["events"][0]["test_event_code"] = settings.snap_test_event_code

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://tr.snapchat.com/v2/conversion",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.snapchat_access_token}",
                    "Content-Type": "application/json",
                },
            )
            return {"status_code": resp.status_code, "body": resp.json()}
    except Exception as e:
        logger.error("Snapchat CAPI error: %s", str(e))
        return {"error": str(e)}


async def fire_purchase_capi(
    order_id: str,
    event_id: str,
    phone_e164: str,
    total: int,
    items: list[dict],
    tracking: dict,
) -> dict[str, Any]:
    """Fire all three CAPI purchase events concurrently. Returns results dict."""
    results: dict[str, Any] = {}
    results["meta"] = await send_meta_purchase(order_id, event_id, phone_e164, total, items, tracking)
    results["tiktok"] = await send_tiktok_purchase(order_id, event_id, phone_e164, total, items, tracking)
    results["snapchat"] = await send_snapchat_purchase(order_id, event_id, phone_e164, total, items, tracking)
    return results
