import re
import uuid
from pydantic import BaseModel, field_validator
from typing import Any


class CustomerIn(BaseModel):
    full_name: str
    phone: str

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2 or len(v) > 80:
            raise ValueError("الاسم يجب أن يكون بين 2 و 80 حرفا")
        return v


class OrderItemIn(BaseModel):
    product_id: str
    offer_id: str
    quantity: int
    unit_count: int
    price: int
    source: str


class OrderTotalsIn(BaseModel):
    subtotal: int
    shipping: int
    total: int
    currency: str = "MAD"


class TrackingIn(BaseModel):
    event_id: str
    fbp: str | None = None
    fbc: str | None = None
    ttp: str | None = None
    ttclid: str | None = None
    sc_click_id: str | None = None
    page_url: str = ""
    referrer: str | None = None
    user_agent: str = ""
    utm: dict[str, str] | None = None


class UpsellIn(BaseModel):
    shown: bool
    accepted: bool
    product_id: str | None = None
    price: int = 99


class OrderIn(BaseModel):
    customer: CustomerIn
    items: list[OrderItemIn]
    totals: OrderTotalsIn
    tracking: TrackingIn
    upsell: UpsellIn


class OrderOut(BaseModel):
    order_id: str
    public_id: str
    status: str
    total: int
    currency: str


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class RedirectBase(BaseModel):
    slug: str
    target_url: str

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Slug is required")
        if not SLUG_RE.match(v):
            raise ValueError(
                "Slug must be URL-safe: lowercase letters, numbers and single "
                "dashes only (e.g. breath-drops, argan-oil)"
            )
        return v

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Target URL is required")
        return v


class RedirectCreate(RedirectBase):
    pass

class RedirectOut(RedirectBase):
    id: uuid.UUID

    class Config:
        from_attributes = True

