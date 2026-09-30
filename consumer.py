"""
consumer.py
Assignment 3 - reads orders from Kafka topic 'ecommerce-orders', processes them,
and stores them in MongoDB Atlas.

Processing per order:
  1. Adds ingested_at (arrival time) for live time-based charts
  2. Tags high_value (order total above Rs 8,000)
  3. Tags at_risk (order was cancelled)
  4. Skips duplicate order_ids (unique index)
"""

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from kafka import KafkaConsumer
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv(override=True)

TOPIC_NAME = "ecommerce-orders"
BOOTSTRAP_SERVERS = "localhost:9092"
HIGH_VALUE_LIMIT = 8000

collection = MongoClient(os.environ["MONGO_URI"])["ecommerce"]["orders"]
collection.create_index("order_id", unique=True)

consumer = KafkaConsumer(
    TOPIC_NAME,
    bootstrap_servers=BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    auto_offset_reset="earliest",
    group_id="a3-dashboard",
)

print(f"Listening on '{TOPIC_NAME}'... (Ctrl+C to stop)")

stored = duplicates = 0
for message in consumer:
    order = message.value
    order["ingested_at"] = datetime.now(timezone.utc)
    order["high_value"] = order["total_amount"] > HIGH_VALUE_LIMIT
    order["at_risk"] = order["order_status"] == "Cancelled"
    try:
        collection.insert_one(order)
        stored += 1
    except DuplicateKeyError:
        duplicates += 1
        print(f"skipped duplicate order_id={order['order_id']}")
        continue
    flags = ("HIGH-VALUE " if order["high_value"] else "") + ("AT-RISK" if order["at_risk"] else "")
    print(f"[{stored}] {order['order_id']} | {order['product_name']} | "
          f"₹{order['total_amount']} | {order['order_status']} {flags}")