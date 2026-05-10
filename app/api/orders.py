import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models import Order, ConversionEvent
from app.schemas import OrderIn, OrderOut
from app.services.phone import normalize_moroccan_phone
from app.services.pricing import recalculate_order
from app.services.sheets import send_to_sheets
from app.services import tracking as tracking_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def generate_public_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"AP-{today}-{str(uuid.uuid4())[:8].upper()}"


@router.post("/orders", response_model=OrderOut)
async def create_order(
    order_in: OrderIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # 1. Validate and normalize phone
    try:
        phone_e164 = normalize_moroccan_phone(order_in.customer.phone)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 2. Recalculate pricing server-side
    try:
        subtotal, shipping, total, validated_items = recalculate_order(
            order_in.items, order_in.upsell
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 3. Build tracking data with real client IP
    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else ""
    )
    tracking_data = order_in.tracking.model_dump()
    tracking_data["ip"] = client_ip

    # 4. Extract UTM separately
    utm_data = tracking_data.pop("utm", {}) or {}

    # 5. Upsell summary
    upsell_data = order_in.upsell.model_dump()

    # 6. Generate IDs
    order_id = uuid.uuid4()
    public_id = generate_public_id()

    # 7. Persist order
    order = Order(
        id=order_id,
        public_id=public_id,
        full_name=order_in.customer.full_name.strip(),
        phone_e164=phone_e164,
        phone_raw=order_in.customer.phone,
        status="new",
        subtotal=subtotal,
        shipping=shipping,
        total=total,
        currency="MAD",
        items_json={"items": validated_items},
        upsell_json=upsell_data,
        tracking_json=tracking_data,
        utm_json=utm_data,
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    logger.info(
        "Order created: %s (total=%s MAD, phone=%s***)",
        public_id, total, phone_e164[:8],
    )

    # 8. Forward to Google Sheets
    PRODUCT_MAPPING = {
        "breath_drops": {"name": "قطرات القرنفل والنعناع", "sku": "BD-001"},
        "foot_spray": {"name": "بخاخ الشبة وزيت شجرة الشاي", "sku": "FS-002"},
        "nail_serum": {"name": "سيروم الثوم والخل", "sku": "NS-003"}
    }
    
    product_names_list = []
    sku_list = []
    quantity_list = []
    
    for item in validated_items:
        p_info = PRODUCT_MAPPING.get(item["product_id"], {"name": item["product_id"], "sku": "UNKNOWN"})
        product_names_list.append(p_info["name"])
        sku_list.append(p_info["sku"])
        quantity_list.append(str(item["quantity"]))
        
    product_names_str = "/".join(product_names_list)
    sku_str = "/".join(sku_list)
    quantity_str = "/".join(quantity_list)
    
    phone_clean = phone_e164.replace("+", "")
    
    sheet_payload = {
        "date": order.created_at.strftime("%d/%m/%Y"),
        "orderid": public_id,
        "country": "maroc",
        "name": order.full_name,
        "phone": phone_clean,
        "product": product_names_str,
        "sku": sku_str,
        "quantity": quantity_str,
        "totale price": total,
        "curency": "MAD",
        "status": "",
        
        # Keep detailed info for debugging in the raw JSON payload if needed
        "detailed_items": validated_items,
        "upsell": upsell_data,
        "tracking": {**tracking_data, "utm": utm_data},
    }

    sheet_ok = await send_to_sheets(sheet_payload)

    if sheet_ok:
        order.status = "sent_to_sheet"
        order.sheet_sent_at = datetime.now(timezone.utc)
    else:
        order.status = "sheet_failed"
        order.sheet_error = "Webhook failed or not configured"

    await db.commit()

    # 9. Fire CAPI (non-blocking on failure)
    event_id = order_in.tracking.event_id
    try:
        capi_results = await tracking_service.fire_purchase_capi(
            order_id=str(order_id),
            event_id=event_id,
            phone_e164=phone_e164,
            total=total,
            items=validated_items,
            tracking={**tracking_data, "utm": utm_data},
        )

        for platform, result in capi_results.items():
            if result.get("skipped"):
                continue
            ce = ConversionEvent(
                order_id=order_id,
                event_name="Purchase",
                event_id=event_id,
                platform=platform,
                payload_json=result,
                response_json=result,
                status_code=result.get("status_code"),
                success=result.get("status_code") in (200, 201),
            )
            db.add(ce)
        await db.commit()
    except Exception as e:
        logger.error("CAPI error for order %s: %s", public_id, str(e))

    return OrderOut(
        order_id=str(order_id),
        public_id=public_id,
        status=order.status,
        total=total,
        currency="MAD",
    )


@router.get("/orders/{public_id}", response_model=OrderOut)
async def get_order_summary(public_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.public_id == public_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderOut(
        order_id=str(order.id),
        public_id=order.public_id,
        status=order.status,
        total=order.total,
        currency=order.currency,
    )
