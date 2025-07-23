import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

import unittest
from unittest.mock import patch, MagicMock, ANY

from src.queue_utils import (
    get_queue_settings,
    create_queue,
    delete_queue
)
from src.message_utils import move_messages
from src.queue_migrator import migrate_queue, validate_migration

class QueueMigratorTests(unittest.TestCase):
    @patch('src.queue_utils.send_api_request')
    def test_get_queue_settings_success(self, mock_request):
        mock_request.return_value = MagicMock(status_code=200, json=lambda: {
            "durable": True,
            "arguments": {"x-max-priority": 5}
        })
        settings = get_queue_settings("vhost1", "queue1")
        self.assertEqual(settings["durable"], True)
        self.assertIn("x-max-priority", settings["arguments"])

    @patch('src.queue_utils.send_api_request')
    def test_get_queue_settings_failure(self, mock_request):
        mock_request.return_value = MagicMock(status_code=404, text="Not Found")
        result = get_queue_settings("vhost1", "unknown_queue")
        self.assertIsNone(result)

    def test_validate_migration_with_unsupported_features(self):
        settings = {
            "arguments": {
                "x-max-priority": 10,
                "some-other-arg": "value"
            }
        }
        result = validate_migration(settings, "quorum")
        self.assertFalse(result[0])
        self.assertEqual(result[1], ['x-max-priority'])

    def test_validate_migration_no_issues(self):
        settings = {"arguments": {"x-some-ok-arg": 123}}
        result, conflicts = validate_migration(settings, "quorum")
        self.assertTrue(result)
        self.assertEqual(conflicts, [])

    @patch('src.queue_utils.send_api_request')
    def test_create_queue_success(self, mock_request):
        mock_request.return_value = MagicMock(status_code=201)
        original = {"durable": True, "arguments": {"x-max-priority": 5}}
        self.assertTrue(create_queue("vhost", "queue_new", "quorum", original))

    @patch('src.queue_utils.send_api_request')
    def test_create_queue_failure(self, mock_request):
        mock_request.return_value = MagicMock(status_code=400, text="Bad Request")
        original = {"durable": True, "arguments": {"x-max-priority": 5}}
        self.assertFalse(create_queue("vhost", "queue_fail", "quorum", original))

    @patch('src.queue_utils.send_api_request')
    def test_delete_queue_success(self, mock_request):
        mock_request.return_value = MagicMock(status_code=204)
        self.assertTrue(delete_queue("vhost", "q1"))

    @patch('src.queue_utils.send_api_request')
    def test_delete_queue_failure(self, mock_request):
        mock_request.return_value = MagicMock(status_code=500, text="Server Error")
        self.assertFalse(delete_queue("vhost", "q1"))

    @patch('pika.BlockingConnection')
    def test_move_messages_success(self, mock_connection):
        # Set up mock channels and connections
        mock_channel = MagicMock()
        mock_connection.return_value.channel.return_value = mock_channel

        # Simulate 2 messages and then a None (timeout)
        def fake_consume(*args, **kwargs):
            Message = MagicMock()
            yield (Message, MagicMock(), b"msg1")
            yield (Message, MagicMock(), b"msg2")
            yield (None, None, None)  # Simulate inactivity timeout

        mock_channel.consume.side_effect = fake_consume

        result = move_messages("src", "target")
        self.assertEqual(result, 2)
        self.assertEqual(mock_channel.basic_publish.call_count, 2)
        mock_channel.basic_publish.assert_any_call(
            exchange="", routing_key="target", body=b"msg1", properties=ANY
        )
        mock_channel.basic_publish.assert_any_call(
            exchange="", routing_key="target", body=b"msg2", properties=ANY
        )

    @patch('pika.BlockingConnection')
    def test_move_messages_empty_queue(self, mock_connection):
        mock_channel = MagicMock()
        mock_connection.return_value.channel.return_value = mock_channel

        # Simulate no messages (just inactivity timeout)
        def fake_consume(*args, **kwargs):
            yield (None, None, None)

        mock_channel.consume.side_effect = fake_consume

        result = move_messages("src", "target")
        self.assertEqual(result, 0)

    @patch('src.queue_migrator.get_queue_settings')
    @patch('src.queue_migrator.validate_migration')
    @patch('src.queue_migrator.create_queue')
    @patch('src.queue_migrator.move_messages')
    @patch('src.queue_migrator.delete_queue')
    @patch('src.queue_migrator.get_queue_policy')
    @patch('src.queue_migrator.get_queue_bindings')
    @patch('src.queue_migrator.create_binding')
    def test_migrate_queue_success_path(
        self, mock_create_binding, mock_get_bindings, mock_get_policy, mock_delete, mock_move, mock_create, mock_validate, mock_get
    ):
        mock_get.return_value = {"durable": True, "arguments": {}}
        mock_validate.return_value = (True, [])
        mock_create.return_value = True
        mock_move.side_effect = [2, 2]
        mock_delete.return_value = True
        mock_get_policy.return_value = None
        mock_get_bindings.return_value = [
            {"source": "ex", "routing_key": "rk", "arguments": {}}
        ]
        mock_create_binding.return_value = True

        migrate_queue("vhost", "queue1", "quorum")
        self.assertTrue(mock_create.called)
        self.assertTrue(mock_move.called)
        self.assertTrue(mock_delete.called)
        self.assertTrue(mock_create_binding.called)

    @patch('pika.BlockingConnection')
    def test_move_messages_preserves_order(self, mock_connection):
        mock_channel = MagicMock()
        mock_connection.return_value.channel.return_value = mock_channel

        sent_messages = []

        def fake_consume(*args, **kwargs):
            yield (MagicMock(), MagicMock(), b"first")
            yield (MagicMock(), MagicMock(), b"second")
            yield (MagicMock(), MagicMock(), b"third")
            yield (None, None, None)

        def fake_basic_publish(exchange, routing_key, body, properties):
            sent_messages.append(body)
            return True

        mock_channel.consume.side_effect = fake_consume
        mock_channel.basic_publish.side_effect = fake_basic_publish

        result = move_messages("queue1", "queue1_temp_migrated")
        self.assertEqual(result, 3)
        self.assertEqual(sent_messages, [b"first", b"second", b"third"])

if __name__ == '__main__':
    unittest.main()
