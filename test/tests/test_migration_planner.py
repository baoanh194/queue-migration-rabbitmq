import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))


import unittest
from unittest.mock import patch
import requests

# Import the functions from your migration_planner module.
from src.migration_planner import (
    get_queue_settings,
    detect_migration_blockers,
    generate_migration_plan
)

# A simple fake response to simulate requests responses
class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.exceptions.HTTPError(f"HTTP error code: {self.status_code}")

class MigrationPlannerTests(unittest.TestCase):

    @patch('src.migration_planner.session.get')
    @patch('src.migration_planner.RABBITMQ_PASS', new='guest')
    @patch('src.migration_planner.RABBITMQ_USER', new='guest')
    @patch('src.migration_planner.RABBITMQ_HOST', new='http://localhost:15672')
    def test_get_queue_settings_success(self, mock_get):
        # Set up a fake API response for a queue
        fake_queue_data = {
            "type": "classic",
            "durable": True,
            "exclusive": False,
            "auto_delete": False,
            "arguments": {
                "x-max-priority": 10,
                "x-queue-mode": "lazy"
            },
            "queue_name": "test_queue",
            "vhost": "test_vhost"
        }
        mock_response = FakeResponse(fake_queue_data)
        mock_get.return_value = mock_response

        # Call the function under test
        result = get_queue_settings("test_vhost", "test_queue")

        # Verify the correct URL and auth were used
        mock_get.assert_called_once_with(
            "http://localhost:15672/api/queues/test_vhost/test_queue",
            auth=('guest', 'guest'),
            timeout=5
        )

        # Verify response content
        self.assertEqual(result, fake_queue_data)

    @patch('src.migration_planner.session.get')
    def test_get_queue_settings_failure(self, mock_get):
        # Simulate a network error or HTTP error
        mock_get.side_effect = requests.exceptions.RequestException("Network error")
        result = get_queue_settings("test_vhost", "bad_queue")
        self.assertIsNone(result)

    def test_detect_migration_blockers_and_warnings(self):
        # Create a dummy queue_info with various fields set, including unsupported arguments.
        queue_info = {
            "queue_name": "dummy",
            "vhost": "dummy_vhost",
            "type": "classic",
            "durable": True,
            "exclusive": True,
            "auto_delete": False,
            "arguments": {
                "x-max-priority": 10,
                "x-queue-mode": "lazy",    # unsupported value for quorum
                "overflow": "reject-publish-dlx",
                "x-queue-version": 1       # triggers warning in our logic
            }
        }
        # Evaluate for quorum migration
        blockers, warnings = detect_migration_blockers(queue_info, "quorum")

        # Expect warnings for each unsupported argument value.
        self.assertIn("Argument 'x-queue-mode=lazy' is not compatible with Quorum Queues.", warnings)
        self.assertIn("Argument 'overflow=reject-publish-dlx' is not compatible with Quorum Queues.", warnings)
        self.assertIn("Setting 'x-queue-version' will be removed during migration.", warnings)
        self.assertIn("Setting 'x-max-priority' will be removed during migration.", warnings)
        self.assertIn("Exclusive queues are not supported.", blockers)

    @patch('src.migration_planner.get_queue_settings')
    def test_generate_migration_plan_success(self, mock_get_queue_settings):
        # Prepare a fake queue info response.
        fake_queue_info = {
            "queue_name": "test_queue",
            "vhost": "test_vhost",
            "type": "classic",
            "durable": True,
            "exclusive": False,
            "auto_delete": False,
            "arguments": {"x-max-priority": 10}
        }
        mock_get_queue_settings.return_value = fake_queue_info

        # Generate the migration plan
        migration_plan = generate_migration_plan("test_vhost", "test_queue")
        self.assertEqual(migration_plan["queue_name"], "test_queue")
        self.assertEqual(migration_plan["vhost"], "test_vhost")

    @patch('src.migration_planner.get_queue_settings')
    def test_generate_migration_plan_failure(self, mock_get_queue_settings):
        # Simulate a failure in fetching the queue settings.
        mock_get_queue_settings.return_value = None
        migration_plan = generate_migration_plan("test_vhost", "nonexistent_queue")
        self.assertIsNone(migration_plan)

if __name__ == '__main__':
    unittest.main()