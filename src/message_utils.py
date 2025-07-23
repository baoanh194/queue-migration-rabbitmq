
#!/usr/bin/env python3
# ==============================================================================
# Copyright (c) 2025, Seventh State
# ==============================================================================
# Message utilities for moving and publishing RabbitMQ messages.
# ==============================================================================

#===============================================================================
# Imports
#===============================================================================
from logger import log_error, log_info
from utils import build_amqp_url
import pika, json

def move_messages(
    source_queue, target_queue, queue_type="quorum", original_args=None,
    vhost="%2f", batch_size=1000
):
    source_url = build_amqp_url(vhost)
    target_url = build_amqp_url(vhost)
    source_conn = target_conn = None
    consumer_tag = None
    messages_moved = 0

    if original_args is None:
        original_args = {}
    queue_args = original_args.copy()
    queue_args["x-queue-type"] = queue_type

    try:
        source_conn = pika.BlockingConnection(pika.URLParameters(source_url))
        source_channel = source_conn.channel()
        target_conn = pika.BlockingConnection(pika.URLParameters(target_url))
        target_channel = target_conn.channel()

        target_channel.confirm_delivery()
        try:
            target_channel.queue_declare(queue=target_queue, passive=True)
        except pika.exceptions.ChannelClosedByBroker as e:
            log_error(f"Target queue '{target_queue}' does not exist: {e}")
            return -1

        for method, properties, body in source_channel.consume(
            source_queue, inactivity_timeout=3, auto_ack=False
        ):
            if method is None:
                break  # inactivity timeout, likely done

            try:
                target_channel.basic_publish(
                    exchange="",
                    routing_key=target_queue,
                    body=body,
                    properties=properties,
                )
                source_channel.basic_ack(delivery_tag=method.delivery_tag)
                messages_moved += 1

                if messages_moved % batch_size == 0:
                    print(f"...migrated {messages_moved} messages so far...")
            except Exception as e:
                source_channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                print(f"Failed to move message: {e}")
                # cancel consumer before returning on failure!
                try:
                    source_channel.cancel()
                except Exception:
                    pass
                return -1  # Indicate failure

        # Cancel the consumer at the end!
        try:
            source_channel.cancel()
        except Exception:
            pass

        print(
            f"Message transfer complete. {messages_moved} message(s) moved from '{source_queue}' to '{target_queue}'."
        )
        return messages_moved

    except Exception as e:
        print(f"Error during message transfer: {e}")
        return -1  # Indicate failure

    finally:
        for conn in [source_conn, target_conn]:
            try:
                if conn and conn.is_open:
                    conn.close()
            except Exception:
                pass