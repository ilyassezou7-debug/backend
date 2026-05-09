"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("phone_raw", sa.String(50), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="new"),
        sa.Column("subtotal", sa.Integer(), nullable=False),
        sa.Column("shipping", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False, server_default="MAD"),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("upsell_json", sa.JSON(), nullable=True),
        sa.Column("tracking_json", sa.JSON(), nullable=True),
        sa.Column("utm_json", sa.JSON(), nullable=True),
        sa.Column("sheet_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sheet_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_orders_public_id", "orders", ["public_id"])
    op.create_index("ix_orders_phone_e164", "orders", ["phone_e164"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])

    op.create_table(
        "conversion_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("event_name", sa.String(100), nullable=False),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column(
            "success",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversion_events_event_id", "conversion_events", ["event_id"])
    op.create_index("ix_conversion_events_order_id", "conversion_events", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_conversion_events_order_id", table_name="conversion_events")
    op.drop_index("ix_conversion_events_event_id", table_name="conversion_events")
    op.drop_table("conversion_events")
    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_index("ix_orders_phone_e164", table_name="orders")
    op.drop_index("ix_orders_public_id", table_name="orders")
    op.drop_table("orders")
