"""
producer_live.py
Assignment 3 - endless SIMULATED order generator with built-in business patterns.
Patterns: city effect, payment effect (COD risk), product effect, and a recurring
payment-gateway incident (all Net Banking orders fail for 90s in every 6-minute cycle).
Ctrl+C to stop.
"""

import json
import random
import time
import uuid
from datetime import datetime

from kafka import KafkaProducer

TOPIC_NAME = "ecommerce-orders"
BOOTSTRAP_SERVERS = "localhost:9092"

PRODUCTS = [  # (name, category, price, popularity weight)
    ("Yoga Mat", "Sports", 699, 6), ("Denim Jacket", "Fashion", 1799, 8),
    ("Running Shoes", "Sports", 2999, 7), ("Cotton T-Shirt", "Fashion", 499, 14),
    ("Basmati Rice 5kg", "Grocery", 549, 12), ("Non-stick Cookware Set", "Home & Kitchen", 2499, 5),
    ("Bluetooth Speaker", "Electronics", 1999, 9), ("Air Fryer", "Home & Kitchen", 3999, 4),
    ("Face Serum", "Beauty", 799, 8), ("Wireless Earbuds", "Electronics", 1499, 13),
]
PRODUCT_MULT = {"Air Fryer": 1.7, "Running Shoes": 1.4, "Non-stick Cookware Set": 1.3,
                "Wireless Earbuds": 1.2, "Bluetooth Speaker": 1.0, "Denim Jacket": 0.9,
                "Face Serum": 0.9, "Yoga Mat": 0.8, "Cotton T-Shirt": 0.7,
                "Basmati Rice 5kg": 0.6}
PAYMENTS = ["UPI", "COD", "Debit Card", "Credit Card", "Wallet", "Net Banking"]
PAY_WEIGHTS = [34, 22, 14, 10, 8, 12]
CITIES = ["Delhi", "Mumbai", "Bangalore", "Chennai", "Hyderabad", "Pune", "Kolkata", "Jaipur"]
CITY_WEIGHTS = [16, 18, 15, 10, 10, 9, 8, 14]
CITY_CANCEL = {"Jaipur": 0.24, "Kolkata": 0.20, "Delhi": 0.13, "Chennai": 0.13,
               "Hyderabad": 0.12, "Pune": 0.11, "Bangalore": 0.10, "Mumbai": 0.09}
PAY_MULT = {"COD": 1.6, "Net Banking": 1.0, "Wallet": 0.9, "Debit Card": 0.8,
            "UPI": 0.7, "Credit Card": 0.6}
DEVICES = ["Mobile", "Tablet", "Desktop"]
DEVICE_WEIGHTS = [65, 10, 25]


def incident_active():
    """Simulated payment-gateway outage: last 90s of every 6-minute cycle."""
    return time.time() % 360 >= 270


def gateway_down(pay):
    return incident_active() and pay == "Net Banking"


def cancel_probability(city, pay, product):
    if gateway_down(pay):
        return 0.75
    return min(CITY_CANCEL[city] * PAY_MULT[pay] * PRODUCT_MULT[product], 0.85)


def cancel_reason(pay):
    if gateway_down(pay):
        return "Payment failed"
    if pay == "COD":
        return random.choices(["Customer refused at delivery", "Changed mind", "Delivery delayed"],
                              [50, 25, 25])[0]
    if pay in ("Net Banking", "UPI"):
        return random.choices(["Payment failed", "Changed mind", "Delivery delayed"],
                              [45, 35, 20])[0]
    return random.choices(["Changed mind", "Delivery delayed", "Out of stock"], [45, 30, 25])[0]


def make_order():
    name, category, price, _ = random.choices(PRODUCTS, [p[3] for p in PRODUCTS])[0]
    city = random.choices(CITIES, CITY_WEIGHTS)[0]
    pay = random.choices(PAYMENTS, PAY_WEIGHTS)[0]
    qty = random.choices([1, 2, 3, 4], [45, 30, 15, 10])[0]
    disc = random.choices([0, 5, 10, 15, 20], [30, 20, 25, 15, 10])[0]
    cancelled = random.random() < cancel_probability(city, pay, name)
    status = "Cancelled" if cancelled else random.choices(
        ["Placed", "Shipped", "Delivered"], [30, 35, 35])[0]
    order = {
        "order_id": uuid.uuid4().hex[:8],
        "timestamp": datetime.now().isoformat(),
        "customer_id": f"CUST{random.randint(1000, 9999)}",
        "customer_type": random.choices(["New", "Returning"], [40, 60])[0],
        "product_name": name, "category": category, "unit_price": price,
        "quantity": qty, "discount_pct": disc,
        "total_amount": round(price * qty * (1 - disc / 100), 2),
        "payment_method": pay, "city": city,
        "device_type": random.choices(DEVICES, DEVICE_WEIGHTS)[0],
        "order_status": status,
    }
    if cancelled:
        order["cancel_reason"] = cancel_reason(pay)
    return order


producer = KafkaProducer(bootstrap_servers=BOOTSTRAP_SERVERS,
                         value_serializer=lambda v: json.dumps(v).encode("utf-8"))

print(f"Streaming simulated orders to '{TOPIC_NAME}'... press Ctrl+C to stop\n")
count = 0
was_incident = False
try:
    while True:
        now_incident = incident_active()
        if now_incident != was_incident:
            print("\n*** SIMULATED INCIDENT " + ("STARTED: Net Banking payments failing ***\n"
                  if now_incident else "ENDED ***\n"))
            was_incident = now_incident
        order = make_order()
        producer.send(TOPIC_NAME, value=order)
        producer.flush()
        count += 1
        print(f"[{count}] {order['order_id']} | {order['product_name']} | ₹{order['total_amount']} "
              f"| {order['city']} | {order['payment_method']} | {order['order_status']}")
        time.sleep(random.uniform(0.3, 1.0))
except KeyboardInterrupt:
    print(f"\nStopped. Sent {count} orders.")
finally:
    producer.close()