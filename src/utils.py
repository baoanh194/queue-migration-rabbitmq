#!/usr/bin/env python3
# ==============================================================================
# Copyright (c) 2025, Seventh State
# ==============================================================================
# Utility module providing common constants and helpers for RabbitMQ queue
# migration, including API helpers and connection string construction.
# ===============================================================================

#===============================================================================
# Imports
#===============================================================================
import requests
from config.config import RABBITMQ_HOST, RABBITMQ_USER, RABBITMQ_PASS, HOST
from logger import log_error

#===============================================================================
# MACROS
#===============================================================================
API_HEADERS = {"Content-Type": "application/json"}
MESSAGE_BATCH_SIZE = 10000

UNSUPPORTED_FEATURES = {
    "quorum": [
        "exclusive",
        "auto-delete",
        "x-max-priority",
        "x-queue-master-locator",
        "x-queue-version",
        "x-queue-mode"
    ]
}

SUPPORTED_SETTINGS = {
    "quorum": {
        "durable": True,
        "supported": [
            "x-expires",
            "x-max-length",
            "x-message-ttl",
            "x-dead-letter-exchange",
            "x-dead-letter-routing-key",
            "x-max-length-bytes",
            "delivery-limit",
            "queue-initial-cluster-size",
            "dead-letter-strategy",
            "leader-locator"
        ],

        "unsupported": UNSUPPORTED_FEATURES["quorum"]
    }
}

UNSUPPORTED_ARGUMENT_VALUES = {
    "x-queue-mode": ["lazy"],
    "overflow": ["reject-publish-dlx"]
}
#=============================================================================
# API Request Helper
#=============================================================================
# Wrapper for making HTTP requests to the RabbitMQ management API.
def send_api_request(method, url, auth, headers=None, json=None):
    try:
        response = requests.request(method, url, auth=auth, headers=headers,
                                    json=json)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        log_error(f"API {method} {url} failed: {e}")
        if hasattr(e.response, 'text'):
            log_error(f"Response: {e.response.status_code} - {e.response.text}")
            return e.response
        return None

# This function builds the AMQP URL for connecting to RabbitMQ.
def build_amqp_url(vhost="%2f"):
    return f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{HOST}:5672/{vhost}"

def remove_unsupported_keys(arguments, queue_type):
    removed = []
    args_copy = arguments.copy()
    for key in UNSUPPORTED_FEATURES.get(queue_type, []):
        if key in args_copy:
            removed.append(key)
            args_copy.pop(key)
    return args_copy, removed

def get_policy_by_name(vhost, policy_name):
    if not policy_name:
        return None
    url = f"{RABBITMQ_HOST}/api/policies/{vhost}"
    response = send_api_request("GET", url, auth=(RABBITMQ_USER, RABBITMQ_PASS))
    if response and response.status_code == 200:
        policies = response.json()
        for policy in policies:
            if policy.get("name") == policy_name:
                return policy
    return None