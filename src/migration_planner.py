#=============================================================================
# Copyright (c) 2025, Seventh State
#=============================================================================
# Fetches all queues from the RabbitMQ management API, checks each queue’s
# properties (such as durability, exclusivity, and auto-delete), and reports if
# a queue is fit for migration. It prints a summary table to the console and
# saves the analysis as a JSON report in migration_report.json.

#===============================================================================
# Imports
#===============================================================================
import requests
import re
import json
import argparse
import os
from rich.table import Table
from rich.console import Console
from rich import box

console = Console()

from src.utils import send_api_request
from src.logger import log_info, log_error
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from colorama import init, Fore, Style
from config.config import RABBITMQ_HOST, RABBITMQ_USER, RABBITMQ_PASS
from src.utils import SUPPORTED_SETTINGS, UNSUPPORTED_ARGUMENT_VALUES

init(autoreset=True)

session = requests.Session()
retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retry))

#===============================================================================
# Internal Functions
#===============================================================================
"""Fetch queue settings from RabbitMQ API with retries and timeout."""
def get_queue_settings(vhost, queue_name):
    url = f"{RABBITMQ_HOST}/api/queues/{vhost}/{queue_name}"

    try:
        response = session.get(url, auth=(RABBITMQ_USER, RABBITMQ_PASS), timeout=5)
        response.raise_for_status()
        queue_data = response.json()
        log_info(f"Fetched settings for queue '{queue_name}' in vhost '{vhost}'.")
        return {
            "queue_name": queue_name,
            "vhost": vhost,
            "type": queue_data.get("type", "classic"),
            "durable": queue_data.get("durable", True),
            "exclusive": queue_data.get("exclusive", False),
            "auto_delete": queue_data.get("auto_delete", False),
            "arguments": queue_data.get("arguments", {})
        }

    except requests.exceptions.RequestException as e:
        log_error(f"Error fetching settings for queue '{queue_name}' in vhost '{vhost}': {e}")
        print(f"Error fetching settings for queue '{queue_name}' in vhost '{vhost}': {e}")
        return None

def get_queue_policy(vhost, queue_name):
    url = f"{RABBITMQ_HOST}/api/policies/{vhost}"
    response = send_api_request("GET", url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
    if response and response.status_code == 200:
        policies = response.json()
        for policy in policies:
            if "pattern" in policy and policy.get("apply-to") in ["queues", "all"]:
                if queue_name and re.match(policy["pattern"], queue_name):
                    return policy
    return None

def check_mirroring_policy(policy):
    if not policy:
        return False
    definition = policy.get("definition", {})
    mirroring_keys = {"ha-mode", "ha-params", "ha-sync-mode", "ha-promote-on-shutdown", "ha-promote-on-failure"}
    return any(k in definition for k in mirroring_keys)

"""Identify migration blockers & warnings based on queue settings."""
def detect_migration_blockers(queue_info, target_type):
    blockers = []
    warnings = []
    settings = SUPPORTED_SETTINGS[target_type]

    if not queue_info["durable"] and settings["durable"]:
        blockers.append("Non-durable queues cannot be migrated.")

    if queue_info["exclusive"]:
        blockers.append("Exclusive queues are not supported.")
    if queue_info["auto_delete"]:
        blockers.append("Auto-delete queues cannot be migrated.")

    arguments = queue_info["arguments"]

    for arg in ["x-queue-version", "x-queue-master-locator", "x-max-priority"]:
        if arg in arguments:
            warnings.append(f"Setting '{arg}' will be removed during migration.")

    # Detect unsupported argument values
    for key, bad_values in UNSUPPORTED_ARGUMENT_VALUES.items():
        if key in arguments and arguments[key] in bad_values:
            warnings.append(f"Argument '{key}={arguments[key]}' is not compatible with Quorum Queues.")

    return blockers, warnings

# Generate a migration plan for a queue.
def generate_migration_plan(vhost, queue_name, queue_info=None):
    if not queue_info:
        queue_info = get_queue_settings(vhost, queue_name)
        if not queue_info:
            log_error(f"Failed to generate migration plan for queue '{queue_name}' in vhost '{vhost}'.")
            return None

    blockers_quorum, warnings_quorum = detect_migration_blockers(queue_info, "quorum")

    mirroring_policy = get_queue_policy(vhost, queue_name)
    has_mirroring = check_mirroring_policy(mirroring_policy)

    if has_mirroring:
        msg = "Queue has classic mirroring policy. This policy will be ignored when migrating to quorum. Migration will proceed."
        print(f"[WARNING] {msg}")
        log_info(f"[WARNING] {msg} Policy: {mirroring_policy}")
        warnings_quorum.append(msg)

    migration_plan = {
        "queue_name": queue_name,
        "vhost": vhost,
        "current_type": queue_info["type"],
        "blockers": {
            "quorum": blockers_quorum
        },
        "warnings": {
            "quorum": warnings_quorum
        },
        "mirroring_policy": mirroring_policy,
        "original_settings": queue_info
    }
    log_info(f"Generated migration plan for queue '{queue_name}': {json.dumps(migration_plan)}")
    return migration_plan

def get_all_queues(vhost):
    url = f"{RABBITMQ_HOST}/api/queues/{vhost}"

    try:
        response = requests.get(url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error fetching queues: {e}")
        return []

def analyze_all_queues(vhost):
    queues = get_all_queues(vhost)
    migration_results = []

    for queue in queues:
        queue_name = queue["name"]
        print(f"Analyzing queue: {queue_name}...")

        migration_plan = generate_migration_plan(vhost, queue_name)
        if migration_plan:
            migration_results.append(migration_plan)

    return migration_results

# Load queues from a RabbitMQ definition export file (JSON).
def load_queues_from_definition_file(filepath):
    if not os.path.exists(filepath):
        log_error(f"Definition file not found: {filepath}")
        return []

    try:
        with open(filepath, "r") as f:
            data = json.load(f)

        queues = data.get("queues", [])
        log_info(f"Loaded {len(queues)} queues from definition file: {filepath}")
        return queues

    except Exception as e:
        log_error(f"Failed to load queues from file '{filepath}': {e}")
        return []

def analyze_queues_from_file(filepath):
    queues = load_queues_from_definition_file(filepath)
    migration_results = []

    for queue in queues:
        queue_info = {
            "queue_name": queue.get("name"),
            "vhost": queue.get("vhost", "%2f"),
            "type": queue.get("type", "classic"),
            "durable": queue.get("durable", True),
            "exclusive": queue.get("exclusive", False),
            "auto_delete": queue.get("auto_delete", False),
            "arguments": queue.get("arguments", {})
        }
        print(f"Analyzing queue from file: {queue_info['queue_name']}...")
        migration_plan = generate_migration_plan(queue_info["vhost"], queue_info["queue_name"], queue_info)
        if migration_plan:
            migration_results.append(migration_plan)

    return migration_results

def print_summary_table(migration_plans):
    table = Table(title="Migration Summary Report", box=box.SIMPLE_HEAVY)
    table.add_column("Queue Name", style="bold cyan", overflow="fold")
    table.add_column("Status", justify="center", style="bold")
    table.add_column("Reason", overflow="fold")

    # Counters for summary
    counts = {"Good": 0, "Warning": 0, "Blocked": 0}

    # Iterate and populate table
    for plan in migration_plans:
        queue_name = plan.get("queue_name", "N/A")
        blockers = [b for bl in plan["blockers"].values() for b in bl]
        warnings = [w for wl in plan["warnings"].values() for w in wl]

        if blockers:
            status = "Blocked"
            reason = "; ".join(blockers)
            style = "red"
            counts[status] += 1
        elif warnings:
            status = "Warning"
            reason = "; ".join(warnings)
            style = "yellow"
            counts[status] += 1
        else:
            status = "Good"
            reason = "-"
            style = "green"
            counts[status] += 1

        table.add_row(
            queue_name,
            f"[{style}]{status}[/{style}]",
            reason
        )

    # Print table and summary
    console.print(table)
    summary = (
        f"Total queues: {len(migration_plans)}  "
        f"[green]Good: {counts['Good']}[/green]  "
        f"[yellow]Warning: {counts['Warning']}[/yellow]  "
        f"[red]Blocked: {counts['Blocked']}[/red]"
    )
    console.print(summary)
    console.print(f"\n[bold yellow]Migration report saved: migration_report.json[/bold yellow]")

def run_migration_planner(args):
    print(f"[DEBUG] Received args: {args}")
    vhost = args.vhost
    queue_name = getattr(args, "queue", None)
    process_all = getattr(args, "all", False)
    json_output = getattr(args, "json", False)
    filepath = getattr(args, "file", None)

    if filepath:
        results = analyze_queues_from_file(filepath)
        if json_output:
            print(json.dumps(results, indent=4))
        else:
            with open("migration_report.json", "w") as f:
                json.dump(results, f, indent=4)
            log_info(f"Saved migration report from definition file.")
            print_summary_table(results)
            print("\nMigration report saved: migration_report.json")
        return

    if process_all:
        results = analyze_all_queues(vhost)
        if json_output:
            print(json.dumps(results, indent=4))
        else:
            with open("migration_report.json", "w") as f:
                json.dump(results, f, indent=4)
            log_info(f"Saved migration report for all queues in vhost '{vhost}'.")
            print_summary_table(results)
            print("\nMigration report saved: migration_report.json")
        return

    if queue_name:
        migration_plan = generate_migration_plan(vhost, queue_name)
        if not migration_plan:
            print(f"{Fore.RED}Failed to generate migration plan for queue '{queue_name}'.")
            log_error(f"Failed to generate migration plan for queue '{queue_name}'.")
            return
        if json_output:
            print(json.dumps(migration_plan, indent=4))
        else:
            print(f"\n{Fore.CYAN + Style.BRIGHT}**Migration Analysis Result**:")
            print(f"{Fore.YELLOW}Queue Name: {migration_plan['queue_name']}")
            print(f"{Fore.YELLOW}Current Type: {migration_plan['current_type']}")

            has_blockers = any(migration_plan["blockers"][mt] for mt in migration_plan["blockers"])

            if not has_blockers:
                print(f"\n{Fore.GREEN + Style.BRIGHT}**Good for Migration**")

            if has_blockers:
                print(f"\n{Fore.RED + Style.BRIGHT}**Bad for Migration** (Blockers detected):")
                for migration_type, reasons in migration_plan["blockers"].items():
                    if reasons:
                        print(f"   {Fore.RED}- {migration_type.capitalize()}: {', '.join(reasons)}")

            for migration_type, warnings in migration_plan["warnings"].items():
                if warnings:
                    print(f"\n{Fore.MAGENTA + Style.BRIGHT}**Warnings for {migration_type.capitalize()} Migration**:")
                    for warning in warnings:
                        print(f"   {Fore.MAGENTA}- {warning}")
    else:
        print("Please provide --queue, --vhost or --all argument")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze RabbitMQ queues for migration.")
    parser.add_argument("--vhost", default="%2f", help="Virtual host (default: %(default)s)")
    parser.add_argument("--queue", help="Specific queue to analyze")
    parser.add_argument("--all", action="store_true", help="Analyze all queues in the vHost")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--file", help="Path to exported RabbitMQ definitions JSON file")

    args = parser.parse_args()
    run_migration_planner(args)
