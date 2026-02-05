"""Order model representing transactional line items."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, column_property

from packages.db.base import Base


class Order(Base):
    """Represents a purchase of a product by a customer."""

    __tablename__ = "orders"

    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.product_id"), nullable=False
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)

    revenue = column_property(quantity * unit_price)

    customer = relationship("Customer", back_populates="orders")
    product = relationship("Product", back_populates="orders")
