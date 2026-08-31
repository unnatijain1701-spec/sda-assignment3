"""
producer.py
Assignment 2 - Sample Data & Kafka Producer
Industry: Retail / E-commerce
"""

import json
import time
from kafka import KafkaProducer

TOPIC_NAME = "ecommerce-orders"
BOOTSTRAP_SERVERS = "localhost:9092"
SAMPLE_DATA_FILE = "sample_ecommerce_data.json"
DELAY_SECONDS = 1

def main():
    with open(SAMPLE_DATA_FILE, "r") as f:
        records = json.load(f)

    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    print(f"Streaming {len(records)} records to topic '{TOPIC_NAME}'...\n")

    for i, record in enumerate(records, start=1):
        producer.send(TOPIC_NAME, value=record)
        producer.flush()
        print(f"[{i}/{len(records)}] Sent order_id={record['order_id']} "
              f"| {record['product_name']} | ₹{record['total_amount']}")
        time.sleep(DELAY_SECONDS)

    producer.close()
    print("\nAll records sent.")


if __name__ == "__main__":
    main()