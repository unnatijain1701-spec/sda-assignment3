"""
generate_sample.py
Assignment 2 - Sample Data & Kafka Producer
Industry: Retail / E-commerce
"""

import json
import random
import uuid
from datetime import datetime, timedelta

NUM_RECORDS = 500

PRODUCTS = [
    ("Wireless Earbuds", "Electronics", 1499),
    ("Cotton T-Shirt", "Fashion", 499),
    ("Air Fryer", "Home & Kitchen", 3999),
    ("Running Shoes", "Sports", 2999),
    ("Face Serum", "Beauty", 799),
    ("Basmati Rice 5kg", "Grocery", 549),
    ("Bluetooth Speaker", "Electronics", 1999),
    ("Denim Jacket", "Fashion", 1799),
    ("Non-stick Cookware Set", "Home & Kitchen", 2499),
    ("Yoga Mat", "Sports", 699),
]

CITIES = ["Delhi", "Mumbai", "Bangalore", "Hyderabad", "Pune", "Chennai", "Kolkata", "Jaipur"]
PAYMENT_METHODS = ["UPI", "Credit Card", "Debit Card", "Net Banking", "COD", "Wallet"]
DEVICE_TYPES = ["Mobile", "Desktop", "Tablet"]
ORDER_STATUS = ["Placed", "Shipped", "Delivered", "Cancelled"]


def generate_record(base_time):
    product_name, category, price = random.choice(PRODUCTS)
    quantity = random.randint(1, 4)
    discount_pct = random.choice([0, 0, 5, 10, 15, 20])
    timestamp = base_time + timedelta(seconds=random.randint(0, 3600 * 24 * 7))

    return {
        "order_id": str(uuid.uuid4())[:8],
        "timestamp": timestamp.isoformat(),
        "customer_id": f"CUST{random.randint(1000, 9999)}",
        "product_name": product_name,
        "category": category,
        "unit_price": price,
        "quantity": quantity,
        "discount_pct": discount_pct,
        "total_amount": round(price * quantity * (1 - discount_pct / 100), 2),
        "payment_method": random.choice(PAYMENT_METHODS),
        "city": random.choice(CITIES),
        "device_type": random.choice(DEVICE_TYPES),
        "order_status": random.choice(ORDER_STATUS),
    }


def main():
    base_time = datetime.now() - timedelta(days=7)
    records = [generate_record(base_time) for _ in range(NUM_RECORDS)]
    records.sort(key=lambda r: r["timestamp"])

    with open("sample_ecommerce_data.json", "w") as f:
        json.dump(records, f, indent=2)

    print(f"Generated {len(records)} sample e-commerce order records.")
    print("Saved to sample_ecommerce_data.json")


if __name__ == "__main__":
    main()