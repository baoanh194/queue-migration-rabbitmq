#===============================================================================
# Test for migrating many queues and bindings.
#===============================================================================
# Purpose:
# Ensures the migration tool can handle complex RabbitMQ topologies
# by migrating 1,000 classic queues, each with 50+ unique bindings to different
# exchanges and routing keys, and verifying all bindings and messages are
# preserved after migration to quorum queues.
#
# Scenario:
# - Creates 1,000 classic queues (manybind_q_0 to manybind_q_999)
# - For each queue: Creates 50 unique direct exchanges and binds
# the queue to each using a unique routing key.
# Publishes messages to the queues via these exchanges.
# - Run tool
# - Verifiy on each queue that:
# The quorum queue exists.
# All expected bindings exist.
# All messages are still present.
#
# Note:
# - At least 512MB of free RAM.

#===============================================================================
# macros and imports
#===============================================================================
import pytest
import pika
import subprocess
import os
import random
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src')))

from src.queue_utils import get_queue_bindings

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__) + "/../../..")

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = os.environ.get("RABBITMQ_PORT", 5672)
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.environ.get("RABBITMQ_PASS", "guest")
VHOST = "/"
TOTAL_QUEUES = 1000
BINDINGS_PER_QUEUE = 50
QUEUE_PREFIX = "manybind_q_"
EXCHANGE_PREFIX = "exchg_"
MSG_PER_QUEUE = 1000

#===============================================================================
# Test setup
#===============================================================================
@pytest.fixture(scope="module")
def rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=VHOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    yield channel
    # Cleanup
    for i in range(TOTAL_QUEUES):
        queue_name = f"{QUEUE_PREFIX}{i}"
        try:
            channel.queue_delete(queue=queue_name)
        except Exception:
            pass
    for j in range(BINDINGS_PER_QUEUE):
        exchange_name = f"{EXCHANGE_PREFIX}{j}"
        try:
            channel.exchange_delete(exchange=exchange_name)
        except Exception:
            pass
    connection.close()

def test_migrate_many_queues_many_bindings_api(rabbitmq_connection):
    ch = rabbitmq_connection
    queue_binding_info = {}

    # Create exchanges and queues with many bindings each
    for j in range(BINDINGS_PER_QUEUE):
        exchange_name = f"{EXCHANGE_PREFIX}{j}"
        ch.exchange_declare(exchange=exchange_name, exchange_type="direct", durable=True)

    for i in range(TOTAL_QUEUES):
        queue_name = f"{QUEUE_PREFIX}{i}"
        ch.queue_declare(queue=queue_name, durable=True, arguments={"x-queue-type": "classic"})
        bindings = []
        for j in range(BINDINGS_PER_QUEUE):
            exchange_name = f"{EXCHANGE_PREFIX}{j}"
            routing_key = f"rk_{i}_{j}"
            ch.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=routing_key)
            bindings.append((exchange_name, routing_key))
        queue_binding_info[queue_name] = bindings
        for msgidx in range(MSG_PER_QUEUE):
            ex, rk = random.choice(bindings)
            msg = f"{queue_name}_msg{msgidx}"
            ch.basic_publish(
                exchange=ex,
                routing_key=rk,
                body=msg.encode(),
                properties=pika.BasicProperties(delivery_mode=2)
            )
        if (i + 1) % 200 == 0:
            print(f"Created/bound {i+1} queues")

    # Run tool
    print("Running migration tool for all queues...")
    result = subprocess.run(
        [
            "q-hop", "migrate_all",
            "--vhost", "%2f",
            "--type", "quorum"
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=3600
    )
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, (
        f"Migration failed!\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    # For each queue, verify quorum type, all bindings via API, and messages
    for i in range(TOTAL_QUEUES):
        queue_name = f"{QUEUE_PREFIX}{i}"
        ch.queue_declare(queue=queue_name, durable=True, arguments={"x-queue-type": "quorum"})

        bindings_api = get_queue_bindings("%2f", queue_name)
        expected_bindings = set(queue_binding_info[queue_name])
        found_bindings = set()
        for b in bindings_api:
            if b.get("destination_type") == "queue" and b.get("destination") == queue_name:
                source = b.get("source")
                rk = b.get("routing_key")
                if (source, rk) in expected_bindings:
                    found_bindings.add((source, rk))
        assert found_bindings == expected_bindings, f"Bindings mismatch in queue {queue_name} (missing: {expected_bindings - found_bindings})"

        # Verification
        msgs = []
        for method_frame, properties, body in ch.consume(queue=queue_name, inactivity_timeout=1):
            if method_frame:
                msgs.append(body.decode())
                ch.basic_ack(delivery_tag=method_frame.delivery_tag)
            else:
                break
        ch.cancel()
        assert len(msgs) >= MSG_PER_QUEUE, f"Queue {queue_name} missing messages after migration"
        if (i + 1) % 200 == 0:
            print(f"Verified {i+1} queues (bindings & messages)")

    print("Test passed: All queues, bindings, and messages preserved after migration.")

if __name__ == "__main__":
    pytest.main([__file__])