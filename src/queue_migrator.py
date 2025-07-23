#!/usr/bin/env python3
# ==============================================================================
# Copyright (c) 2025, Seventh State
# ==============================================================================
# Orchestrates the migration of a queue to a new type (quorum/stream).
# Ensures settings compatibility, recreates queues and bindings,
# and moves messages.

#===============================================================================
# Imports
#===============================================================================
from logger import log_info, log_error
from colorama import Fore, Style, init as colorama_init
from queue_utils import (get_queue_settings,
                         get_queue_bindings, check_mirroring_policy,
                         create_queue, create_binding, delete_queue)
from message_utils import move_messages
from utils import (UNSUPPORTED_FEATURES, remove_unsupported_keys,
                   get_policy_by_name)
import argparse
colorama_init(autoreset=True)

#===============================================================================
# Main Functions
#===============================================================================
def validate_migration(settings, queue_type):
    unsupported_keys = UNSUPPORTED_FEATURES.get(queue_type, [])
    conflicts = [k for k in settings["arguments"] if k in unsupported_keys]
    if conflicts:
        log_error(f"{queue_type.capitalize()} queues do not support: {conflicts}")
        print(f"{Fore.RED}[Migration halted] {queue_type.capitalize()} queues do not support: {conflicts}. Investigate manually.{Style.RESET_ALL}")
        return False, conflicts
    return True, []

# Algorithm:
# creates temporary queue, moves messages, deletes original queue,
# recreates queue with new type, moves messages back, and deletes
# temporary queue.
# Currently, rollback is not implemented.
# Manual intervention needed in case of failure.
def migrate_queue(vhost, name, target_type):
    log_info(f"===== Starting migration of '{name}' to '{target_type}' =====")

    try:
        settings = get_queue_settings(vhost, name)
        if not settings:
            log_error(f"Queue '{name}' not found in vhost '{vhost}'. Aborting.")
            return

        policy = get_policy_by_name(vhost, settings.get("policy"))
        if check_mirroring_policy(policy):
            log_info(f"Queue '{name}' has mirroring policy. Remove before migrating.")

        bindings = get_queue_bindings(vhost, name)
        if bindings is None:
            log_error(f"Failed to retrieve bindings for '{name}'. Aborting migration.")
            print(f"[Migration halted] Could not retrieve bindings for '{name}'.")
            return

        temp_name = f"{name}_temp_migrated"
        args, removed = remove_unsupported_keys(settings["arguments"], target_type)
        if removed:
            log_info(f"Removed unsupported arguments for {target_type} queue: {removed}")
        # Set the x-queue-type for the temp queue
        args["x-queue-type"] = target_type
        if not create_queue(vhost, temp_name, settings["durable"], args):
            log_error("Failed to create temporary queue. Aborting.")
            return

        messages_moved = move_messages(
            name, temp_name, target_type, settings.get("arguments"), vhost
        )

        if messages_moved == 0:
            log_info(f"No messages found in '{name}'. Continuing migration.")
            print(f"No messages found in '{name}'. Continuing migration.")

        if messages_moved == -1:
            log_error("Error during message transfer. Migration aborted.")
            print(f"[Migration halted] Error during message transfer. Investigate manually.")
            return

        if not delete_queue(vhost, name, if_empty=True):
            log_error(f"Failed to delete original queue '{name}'. Aborting migration.")
            print(f"[Migration halted] Could not delete original queue '{name}'. Investigate manually.")
            return

        final_args, removed_final = remove_unsupported_keys(settings["arguments"], target_type)
        if removed_final:
            log_info(f"Removed unsupported arguments for {target_type} queue: {removed_final}")
        # Set the x-queue-type for the recreated queue
        final_args["x-queue-type"] = target_type
        if not create_queue(vhost, name, settings["durable"], final_args):
            log_error(f"Failed to recreate queue '{name}' as '{target_type}'.")
            print(f"[Migration halted] Could not recreate queue '{name}'. Investigate manually.")
            return

        for binding in bindings:
            exchange = binding.get("source")
            routing_key = binding.get("routing_key", "")
            arguments = binding.get("arguments", {})
            if exchange and not create_binding(vhost, exchange, name, routing_key, arguments):
                log_error(f"Failed to recreate binding '{exchange}' -> '{name}'. Aborting migration.")
                print(f"[Migration halted] Could not recreate bindings. Investigate manually.")
                return

        moved_back = move_messages(
            temp_name, name, queue_type=target_type,
            original_args=settings.get("arguments"), vhost=vhost
        )

        if moved_back == 0 and messages_moved == 0:
            log_info(f"No messages moved back from '{temp_name}' to '{name}'. Continuing migration.")

        if messages_moved == -1:
            log_error("Error during message transfer. Migration aborted.")
            print(f"[Migration halted] Error during message transfer. Investigate manually.")
            return

        if moved_back != messages_moved:
            log_error(f"Mismatch: moved {messages_moved} to temp, but {moved_back} moved back to '{name}'. Investigate manually.")
            print(f"[Migration halted] Message count mismatch. Manual intervention required.")
            return

        if not delete_queue(vhost, temp_name):
            log_error(f"Failed to delete temporary queue '{temp_name}'. Investigate manually.")
            print(f"[Migration warning] Could not delete temporary queue '{temp_name}'.")
            return

        print(f"Migration complete! Queue '{name}' is now '{target_type}'.")
        log_info(f"Migration successful for queue '{name}' to '{target_type}'.")

    except KeyboardInterrupt:
        log_error("Migration interrupted by user (Ctrl+C).")
        print(f"\n{Fore.RED}[Migration interrupted] by user. Investigate manually for cleanup.{Style.RESET_ALL}")
        return

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RabbitMQ Queue Migration Tool")
    parser.add_argument("--vhost", required=True, help="vHost of the queue")
    parser.add_argument("--queue", required=True, help="Queue name")
    parser.add_argument("--type", required=True, choices=["quorum"], help="Target queue type")
    args = parser.parse_args()

    migrate_queue(args.vhost, args.queue, args.type)