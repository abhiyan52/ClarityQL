"""Seed script for local development data."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from random import choice, randint

from faker import Faker

from packages.db.base import Base, get_engine
from packages.db.models import (
    Conversation,
    ConversationState,
    Customer,
    Order,
    Product,
    User,
)
from packages.db.session import SessionLocal

fake = Faker()

PRODUCT_LINES = ["Core", "Pro", "Enterprise"]
PRODUCT_CATEGORIES = ["Analytics", "Data Ops", "Security", "Finance", "Growth"]
SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]
REGIONS = ["North America", "Europe", "APAC", "LATAM"]


def seed_customers(session) -> list[Customer]:
    customers = []
    for _ in range(50):
        customer = Customer(
            name=fake.company(),
            segment=choice(SEGMENTS),
            country=fake.country(),
        )
        customers.append(customer)
    session.add_all(customers)
    session.flush()
    return customers


def seed_products(session) -> list[Product]:
    products = []
    for _ in range(20):
        product = Product(
            product_line=choice(PRODUCT_LINES),
            category=choice(PRODUCT_CATEGORIES),
        )
        products.append(product)
    session.add_all(products)
    session.flush()
    return products


def seed_orders(session, customers: list[Customer], products: list[Product]) -> None:
    orders = []
    start_date = date.today() - timedelta(days=365)
    for _ in range(500):
        order = Order(
            customer_id=choice(customers).customer_id,
            product_id=choice(products).product_id,
            order_date=start_date + timedelta(days=randint(0, 364)),
            quantity=randint(1, 25),
            unit_price=Decimal(str(round(randint(50, 500) + randint(0, 99) / 100, 2))),
            region=choice(REGIONS),
        )
        orders.append(order)
    session.add_all(orders)


def seed_users(session) -> list[User]:
    users = []
    for idx in range(2):
        user = User(
            email=f"analyst{idx + 1}@clarityql.local",
            hashed_password=fake.sha256(raw_output=False),
        )
        users.append(user)
    session.add_all(users)
    session.flush()
    return users


def seed_conversations(session, users: list[User]) -> None:
    for user in users:
        conversation = Conversation(user_id=user.user_id)
        session.add(conversation)
        session.flush()
        state = ConversationState(
            conversation_id=conversation.conversation_id,
            ast_json={"status": "seeded"},
            last_sql="SELECT 1;",
        )
        session.add(state)


def main() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)

    session = SessionLocal()
    try:
        customers = seed_customers(session)
        products = seed_products(session)
        seed_orders(session, customers, products)
        users = seed_users(session)
        seed_conversations(session, users)
        session.commit()
        print("Seeded database with fake data.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
