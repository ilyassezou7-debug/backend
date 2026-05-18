from app.schemas import OrderItemIn, UpsellIn

VALID_PRODUCTS = {"breath_drops", "foot_spray", "nail_serum"}
OFFER_PRICES: dict[str, dict] = {
    "one": {"unit_count": 1, "price": 292},
    "two": {"unit_count": 2, "price": 359},
    "three": {"unit_count": 3, "price": 426},
    "cross_sell": {"unit_count": 1, "price": 149},
    "upsell_99": {"unit_count": 1, "price": 99},
}


def recalculate_order(
    items: list[OrderItemIn], upsell: UpsellIn
) -> tuple[int, int, int, list[dict]]:
    """Returns (subtotal, shipping, total, validated_items). Raises ValueError on invalid input."""
    if not items:
        raise ValueError("الطلب يجب أن يحتوي على منتج واحد على الأقل")

    validated_items = []
    subtotal = 0
    upsell_count = 0

    for item in items:
        if item.product_id not in VALID_PRODUCTS:
            raise ValueError(f"منتج غير معروف: {item.product_id}")

        if item.offer_id not in OFFER_PRICES:
            raise ValueError(f"عرض غير معروف: {item.offer_id}")

        if item.offer_id == "upsell_99":
            upsell_count += 1
            if upsell_count > 1:
                raise ValueError("لا يمكن إضافة أكثر من عرض إضافي واحد")
            if item.source != "post_checkout_upsell":
                raise ValueError("العرض الإضافي غير صالح")

        offer = OFFER_PRICES[item.offer_id]
        server_price = offer["price"] * item.quantity
        subtotal += server_price

        validated_items.append({
            "product_id": item.product_id,
            "offer_id": item.offer_id,
            "quantity": item.quantity,
            "unit_count": offer["unit_count"],
            "price": offer["price"],
            "source": item.source,
        })

    shipping = 0
    total = subtotal + shipping
    return subtotal, shipping, total, validated_items
