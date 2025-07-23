# config.py
import os

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "http://localhost:15672")
HOST = os.getenv("HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")

RABBITMQ_BROKER = os.getenv("RABBITMQ_BROKER", "localhost")
