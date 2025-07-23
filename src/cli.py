#!/usr/bin/env python3
#=============================================================================
# Copyright (c) 2025, Seventh State
#=============================================================================
# CLI tool for managing RabbitMQ queues.

import requests
import json
import argparse
import subprocess
import sys
from config.config import RABBITMQ_HOST, RABBITMQ_USER, RABBITMQ_PASS

#=============================================================================
# Internal Functions
#=============================================================================
"""Constructs the RabbitMQ API URL for queues."""
def _get_queue_url(vhost=None):
    return f"{RABBITMQ_HOST}/api/queues/{vhost}" if vhost else f"{RABBITMQ_HOST}/api/queues"

"""Fetch and display the list of RabbitMQ queues."""
def list_queues(args):
    queue_name = args.name
    vhost = args.vhost
    json_output = args.json
    url = _get_queue_url(vhost)
    try:
        response = requests.get(url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
        response.raise_for_status()
        queues = response.json() or []

        if queue_name:
            queues = [q for q in queues if queue_name in q.get("name", "")]

        if json_output:
            print(json.dumps(queues, indent=2))
            return

        print(f"{'VHost':<20}{'Queue Name':<20}{'Type':<10}{'Messages':<10}{'State':<15}{'Policies':<10}{'Publish/s':<15}{'Deliver/s':<15}{'Arguments':<10}")
        print("=" * 135)
        for queue in queues:
            message_stats = queue.get('message_stats', {})
            publish_details = message_stats.get('publish_details', {})
            deliver_details = message_stats.get('deliver_details', {})
            publish_rate = publish_details.get('rate', 0.0)
            deliver_rate = deliver_details.get('rate', 0.0)
            print(f"{queue.get('vhost', 'N/A'):<20}{queue.get('name', 'N/A'):<20}{queue.get('type', 'N/A'):<10}{queue.get('messages', 0):<10}{queue.get('state', 'unknown'):<15}{queue.get('policy', 'None'):<10}{publish_rate:<15.2f}{deliver_rate:<15.2f} {json.dumps(queue.get('arguments', {}))}")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching queue details: {e}")

def _run_subprocess(command):
    try:
        subprocess.run(command, check=True)
    except KeyboardInterrupt:
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e.cmd}\n{e}")
        return

def run_migration_planner(args):
    command = ["python3", "src/migration_planner.py"]
    if args.vhost:
        command.extend(["--vhost", args.vhost])
    if args.queue:
        command.extend(["--queue", args.queue])
    if args.all:
        command.append("--all")
    if args.json:
        command.append("--json")
    if args.file:
        command.extend(["--file", args.file])
    _run_subprocess(command)

def run_queue_migrator(args):
    command = ["python3", "src/queue_migrator.py", "--vhost", args.vhost, "--queue", args.queue, "--type", args.type]
    _run_subprocess(command)

def run_all_queue_migrator(args):
    vhost = args.vhost
    target_type = args.type
    url = _get_queue_url(vhost)
    try:
        response = requests.get(url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
        response.raise_for_status()
        queues = response.json() or []
        classic_queues = [q for q in queues if q.get("type") == "classic"]
        if not classic_queues:
            print(f"No classic queues found in vhost '{vhost}'.")
            return

        print(f"Initiating migration of {len(classic_queues)} classic queues in vhost '{vhost}' to '{target_type}'.")
        for queue in classic_queues:
            queue_name = queue.get("name")
            print(f"Migrating queue: {queue_name}")
            command = ["python3", "src/queue_migrator.py", "--vhost", vhost, "--queue", queue_name, "--type", target_type]
            _run_subprocess(command)
        print("Migration process initiated for all classic queues.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching queue details: {e}")

def main():
    parser = argparse.ArgumentParser(description="CLI for RabbitMQ migration tasks")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    list_parser = subparsers.add_parser("list_queues", help="List RabbitMQ queues")
    list_parser.add_argument("--name", help="Filter queues by name")
    list_parser.add_argument("--vhost", help="Filter queues by vhost")
    list_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    list_parser.set_defaults(func=list_queues)

    planner_parser = subparsers.add_parser("planner", help="Analyze queue migration suitability")
    planner_parser.add_argument("--vhost", default="%2f", help="Virtual host (default: %(default)s)")
    planner_parser.add_argument("--queue", help="Specify a queue name to analyze")
    planner_parser.add_argument("--all", action="store_true", help="Analyze all queues in the specified vHost")
    planner_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    planner_parser.add_argument("--file", help="Path to exported RabbitMQ definitions JSON file")
    planner_parser.set_defaults(func=run_migration_planner)

    creator_parser = subparsers.add_parser("migrate_queue", help="Migrate an existing queue to a quorum queue")
    creator_parser.add_argument("--vhost", required=True, help="Virtual host for the queue")
    creator_parser.add_argument("--queue", required=True, help="Name of the queue to migrate")
    creator_parser.add_argument("--type", required=True, choices=["quorum"], help="Target queue type")
    creator_parser.set_defaults(func=run_queue_migrator)

    migrate_all_parser = subparsers.add_parser("migrate_all", help="Migrate all classic queues in a vhost to a new type")
    migrate_all_parser.add_argument("--vhost", required=True, help="Virtual host containing the queues")
    migrate_all_parser.add_argument("--type", required=True, choices=["quorum"], help="Target queue type for migration")
    migrate_all_parser.set_defaults(func=run_all_queue_migrator)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
