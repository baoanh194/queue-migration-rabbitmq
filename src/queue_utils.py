#!/usr/bin/env python3
# ==============================================================================
# Copyright (c) 2025, Seventh State
# ==============================================================================
# ==============================================================================
# Queue utilities: queue settings, creation/deletion, bindings,
# and policy checks.
# ==============================================================================

#===============================================================================
# Imports
#===============================================================================
from config.config import RABBITMQ_HOST, RABBITMQ_USER, RABBITMQ_PASS
from logger import log_error, log_info
from utils import send_api_request, remove_unsupported_keys, API_HEADERS
import re

#===============================================================================
# Queue functions
#===============================================================================
# Retrieves the settings of a specific queue from the RabbitMQ management API.
def get_queue_settings(vhost, queue_name):
    url = f"{RABBITMQ_HOST}/api/queues/{vhost}/{queue_name}"
    response = send_api_request("GET", url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
    if response and response.status_code == 200:
        data = response.json()
        return {
            "durable": data.get("durable", True),
            "arguments": data.get("arguments", {}),
            "policy": data.get("policy")  # This is the policy name
        }
    log_error(f"Unable to retrieve settings for {vhost}/{queue_name}.")
    return None

# Creates a new queue in RabbitMQ.
def create_queue(vhost, name, durable, arguments):
    url = f"{RABBITMQ_HOST}/api/queues/{vhost}/{name}"
    payload = {"durable": durable, "arguments": arguments}
    response = send_api_request("PUT", url, auth=(RABBITMQ_USER, RABBITMQ_PASS),
                                headers=API_HEADERS, json=payload)
    if response and response.status_code in [201, 204]:
        log_info(f"Queue '{name}' created.")
        return True
    log_error(f"Failed to create queue '{name}': {response.text if response else 'Unknown error'}")
    return False

def delete_queue(vhost, name, if_empty=False):
    url = f"{RABBITMQ_HOST}/api/queues/{vhost}/{name}"
    if if_empty:
        url += "?if-empty=true"
    response = send_api_request("DELETE", url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
    if response and response.status_code in [200, 204, 404]:
        log_info(f"Queue '{name}' deleted (or did not exist).")
        return True
    log_error(f"Failed to delete queue '{name}' (status: {getattr(response, 'status_code', None)}): {getattr(response, 'text', None)}")
    return False

#===============================================================================
# Binding functions
#===============================================================================
# Retrieves the bindings for a specific queue.
def get_queue_bindings(vhost, queue_name):
    url = f"{RABBITMQ_HOST}/api/queues/{vhost}/{queue_name}/bindings"
    response = send_api_request("GET", url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
    if response and response.status_code == 200:
        return response.json()
    log_error(f"Unable to retrieve bindings for {vhost}/{queue_name}.")
    return None

# Creates a binding between an exchange and a queue.
def create_binding(vhost, exchange_name, queue_name, routing_key,
                   arguments=None):
    url=f"{RABBITMQ_HOST}/api/bindings/{vhost}/e/{exchange_name}/q/{queue_name}"
    payload = {"routing_key": routing_key, "arguments": arguments or {}}
    response = send_api_request("POST", url,
                                auth=(RABBITMQ_USER, RABBITMQ_PASS),
                                headers=API_HEADERS, json=payload)
    if response and response.status_code in [201, 204]:
        log_info(f"Binding created: Exchange '{exchange_name}' \
                 to Queue '{queue_name}' with routing key '{routing_key}'")
        return True
    log_error(f"Failed to create binding: Exchange '{exchange_name}' to Queue '{queue_name}' with routing key '{routing_key}'. Error: {response.text if response else 'Unknown'}")
    return False

#===============================================================================
# Policy/Mirroring Functions
#===============================================================================
#Retrieves the policies defined for a specific vhost in RabbitMQ.
def get_queue_policy(vhost, queue_name):
    url = f"{RABBITMQ_HOST}/api/policies/{vhost}"
    response = send_api_request("GET", url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
    if response and response.status_code == 200:
        policies = response.json()
        for policy in policies:
            if "pattern" in policy and policy.get("apply-to") in ["queues", "all"]:
                # If pattern matches the queue name
                if queue_name and re.match(policy["pattern"], queue_name):
                    return policy
    return None

# Returns True if policy has mirroring settings.
def check_mirroring_policy(policy):
    if not policy:
        return False
    definition = policy.get("definition", {})
    mirroring_keys = {"ha-mode", "ha-params", "ha-sync-mode",
                      "ha-promote-on-shutdown", "ha-promote-on-failure"}
    return any(k in definition for k in mirroring_keys)