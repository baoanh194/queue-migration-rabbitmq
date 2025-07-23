#===============================================================================
# Parametrized “perf” test for RabbitMQ migration tool
#
# Merges:
#  - 10000_queues.py → “small queues” case (100 queues, 10 msgs each)
#  - 10000_queues_many_msgs.py → “large queues” case (100 queues, 10000 msgs each))
#  - one_queue_1M_messages.py → “single queue” case (1 queue, 1000000 msgs, order‐verify)
#
# (We leave out many_queues_many_bindings.py, which is topology‐specific.)
#
# Usage:
#   python3 test/tests/perf/test_migration_parametrized.py
#
# Please make sure RabbitMQ is running on localhost:5672, guest/guest.
#===============================================================================
import os
import subprocess
import time
import pytest
import pika

#───────────────────────────────────────────────────────────────────────────────
# Configuration (adjust paths / credentials as needed)
#───────────────────────────────────────────────────────────────────────────────
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = os.environ.get("RABBITMQ_PORT", 5672)
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.environ.get("RABBITMQ_PASS", "guest")
VHOST = "/"

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../..")
)
#───────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
# Returns a pika channel connected to RabbitMQ, and cleans up after all scenarios.
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

    # Delete any queues that may have been created by our test scenarios.
    # We know the prefixes used below, so delete them all.
    prefixes = ["bulk_q_", "super_bulk_q_", "big_msg_q"]
    # For “small” and “large” cases: up to 100 queues each.
    for prefix in prefixes:
        # In the single‐queue case, the prefix is exactly "big_msg_q"
        # In the multi‐queue cases, prefix + index 0..99
        for i in range(100):
            qname = f"{prefix}{i}"
            try:
                channel.queue_delete(queue=qname)
            except Exception:
                pass
        # Also delete the one‐queue “big_msg_q” without index
        if prefix == "big_msg_q":
            try:
                channel.queue_delete(queue="big_msg_q")
            except Exception:
                pass
    connection.close()

    # Run tool
def run_migration_tool(args):
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=7200,
    )


@pytest.mark.parametrize("scenario", [
    {
        # Small queues: fixed small number of messages for quick verification
        "name": "small_queues",
        "num_queues": 100,
        "queue_prefix": "bulk_q_",
        "msg_spec": {"type": "fixed", "count": 10},
        "verify_mode": "all",
    },
    {
        # Large queues: fixed large number of messages for thorough verification
        "name": "large_queues",
        "num_queues": 100,
        "queue_prefix": "super_bulk_q_",
        "msg_spec": {"type": "fixed", "count": 10000},
        "verify_mode": "all",
    },
    {
        # Single queue, large scale, verify ordered messages
        "name": "single_queue",
        "num_queues": 1,
        "queue_prefix": "big_msg_q",
        "msg_spec": {"type": "fixed", "count": 10},
        "verify_mode": "ordered",
        "batch_size": 1000,
    },
])
def test_migration_various_scenarios(rabbitmq_connection, scenario):
    ch = rabbitmq_connection
    ch.confirm_delivery()

    num_queues = scenario["num_queues"]
    prefix = scenario["queue_prefix"]
    msg_spec = scenario["msg_spec"]
    verify_mode = scenario["verify_mode"]

    # Storage for “expected” messages per queue
    # For “all” mode: a list of messages per queue.
    # For “ordered” mode: nothing special, we know the expected is [0..N-1].
    expected_data = {}

    # CREATE QUEUES AND PUBLISH MESSAGES
    if verify_mode == "ordered":
        # Single‐queue case: queue name is exactly “big_msg_q”
        queue_name = prefix  # no index appended
        # delete old queue if it exists
        ch.queue_delete(queue=queue_name)
        ch.queue_declare(
            queue=queue_name,
            durable=True,
            arguments={"x-queue-type": "classic"},
        )

        total = msg_spec["count"]
        batch_size = scenario.get("batch_size", 1000)
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            for i in range(batch_start, batch_end):
                ch.basic_publish(
                    exchange="",
                    routing_key=queue_name,
                    body=str(i).encode(),
                    properties=pika.BasicProperties(delivery_mode=2),
                )
            # Optional here: print progress every 100k
            if batch_end % 100_000 == 0:
                print(f"[{scenario['name']}] Published messages {batch_start}–{batch_end - 1}")

        # delay to flush to disk
        time.sleep(2)

        expected_data[queue_name] = total

    else:
        for i in range(num_queues):
            queue_name = f"{prefix}{i}"
            ch.queue_declare(
                queue=queue_name,
                durable=True,
                arguments={"x-queue-type": "classic"},
            )

            count = msg_spec["count"]

            # Generate all messages (strings) to verify later
            msgs = [f"msg_{queue_name}_{j}" for j in range(count)]

            expected_data[queue_name] = list(msgs)

            # publish everything
            for msg in msgs:
                ch.basic_publish(
                    exchange="",
                    routing_key=queue_name,
                    body=msg.encode(),
                    properties=pika.BasicProperties(delivery_mode=2),
                )

            if (i + 1) % 20 == 0:  # print every 20 so we don't spam logs
                print(f"[{scenario['name']}] Published to {i+1}/{num_queues} queues")

    # RUN MIGRATION TOOL
    print(f"[{scenario['name']}] Running migration tool on all queues...")

    if verify_mode == "ordered":
        args = [
            "q-hop", "migrate_queue",
            "--vhost", "%2f",
            "--queue", prefix,
            "--type", "quorum",
        ]
    else:
        args = [
            "q-hop", "migrate_all",
            "--vhost", "%2f",
            "--type", "quorum",
        ]

    result = run_migration_tool(args)
    # write logs for debugging
    with open(f"migration_stdout_{scenario['name']}.log", "w") as f:
        f.write(result.stdout)
    with open(f"migration_stderr_{scenario['name']}.log", "w") as f:
        f.write(result.stderr)
    assert result.returncode == 0, (
        f"Migration failed for scenario {scenario['name']}!\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    # VERIFY POST‐MIGRATION

    if verify_mode == "all":
        # For each queue, redeclare as quorum and consume *all* messages in order
        for i in range(num_queues):
            queue_name = f"{prefix}{i}"
            expected_msgs = expected_data[queue_name]

            # declare as quorum
            ch.queue_declare(
                queue=queue_name,
                passive=True,
            )

            actual = []
            for method_frame, props, body in ch.consume(queue=queue_name, inactivity_timeout=1):
                if method_frame:
                    actual.append(body.decode())
                    ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                else:
                    break
            ch.cancel()

            assert actual == expected_msgs, (
                f"[{scenario['name']}] FULL‐VERIFY failed for queue {queue_name}: "
                f"expected {len(expected_msgs)} messages, got {len(actual)}"
            )

            if (i + 1) % 20 == 0:
                print(f"[{scenario['name']}] Verified ALL messages in {i+1}/{num_queues} queues")

    else:  # verify_mode == "ordered"
        # Single‐queue: consume in batches until we have total_messages, check order
        queue_name = prefix  # “big_msg_q”
        total = expected_data[queue_name]

        # redeclare as quorum
        ch.queue_declare(
            queue=queue_name,
            passive=True,
        )

        # consume sequentially
        messages = []
        for _ in range(0, total, scenario.get("batch_size", 1000)):
            batch = ch.consume(queue=queue_name, inactivity_timeout=5)
            for method_frame, props, body in batch:
                if method_frame:
                    messages.append(int(body.decode()))
                    ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                else:
                    break
            if len(messages) >= total:
                break
            print(f"[{scenario['name']}] Consumed {len(messages)}/{total} messages so far...")

        assert len(messages) == total, (
            f"[{scenario['name']}] LENGTH mismatch: expected {total} messages, got {len(messages)}"
        )
        # check ordering
        assert messages == list(range(total)), (
            f"[{scenario['name']}] ORDER mismatch: messages are not in 0..{total - 1}"
        )

    print(f"[{scenario['name']}] Test passed.")

if __name__ == "__main__":
    pytest.main([__file__])