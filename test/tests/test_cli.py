import unittest
import requests
from unittest.mock import patch, MagicMock
from subprocess import CalledProcessError
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from src.cli import (
    list_queues, _run_subprocess, run_migration_planner, run_queue_migrator)

class TestCLI(unittest.TestCase):

    @patch("src.cli.requests.get")
    def test_list_queues_json_output(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                "name": "test_queue",
                "vhost": "/",
                "messages": 0,
                "state": "running",
                "arguments": {"x-queue-type": "classic"}
            }
        ]
        mock_get.return_value = mock_response

        args = MagicMock(name="Args")
        args.name = None
        args.vhost = "%2f"
        args.json = True

        with patch("builtins.print") as mock_print:
            list_queues(args)
            mock_print.assert_called()  # Ensure some output

        mock_get.assert_called_once()

    @patch("src.cli.requests.get")
    def test_list_queues_filtered_by_name(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {"name": "test1", "vhost": "/", "messages": 0, "state": "running", "arguments": {}},
            {"name": "another_queue", "vhost": "/", "messages": 1, "state": "idle", "arguments": {}}
        ]
        mock_get.return_value = mock_response

        args = MagicMock()
        args.name = "test"
        args.vhost = "%2f"
        args.json = False

        with patch("builtins.print") as mock_print:
            list_queues(args)
            mock_print.assert_called()

        mock_get.assert_called_once()

    @patch("src.cli.requests.get", side_effect=requests.exceptions.RequestException("Something went wrong"))
    def test_list_queues_http_error(self, mock_get):
        args = MagicMock()
        args.name = None
        args.vhost = "%2f"
        args.json = False

        with patch("builtins.print") as mock_print:
            list_queues(args)
            mock_print.assert_called_with("Error fetching queue details: Something went wrong")



    @patch("src.cli.subprocess.run")
    def test_run_subprocess_success(self, mock_run):
        _run_subprocess(["echo", "hello"])
        mock_run.assert_called_with(["echo", "hello"], check=True)

    @patch("src.cli.subprocess.run", side_effect=CalledProcessError(returncode=1, cmd="fake cmd"))
    def test_run_subprocess_failure(self, mock_run):
        with patch("builtins.print") as mock_print:
            _run_subprocess(["fake", "cmd"])
            mock_print.assert_called_with("Error running command: fake cmd\nCommand 'fake cmd' returned non-zero exit status 1.")



    @patch("src.cli._run_subprocess")
    def test_run_migration_planner_args(self, mock_subprocess):
        args = MagicMock()
        args.vhost = "%2f"
        args.queue = "q1"
        args.all = False
        args.json = True

        run_migration_planner(args)
        mock_subprocess.assert_called()
        called_args = mock_subprocess.call_args[0][0]
        self.assertIn("--queue", called_args)
        self.assertIn("q1", called_args)

    @patch("src.cli._run_subprocess")
    def test_run_queue_migrator_args(self, mock_subprocess):
        args = MagicMock()
        args.vhost = "test_vhost"
        args.queue = "my_queue"
        args.type = "quorum"

        run_queue_migrator(args)
        mock_subprocess.assert_called_with([
            "python3", "src/queue_migrator.py",
            "--vhost", "test_vhost",
            "--queue", "my_queue",
            "--type", "quorum"
        ])

if __name__ == '__main__':
    unittest.main()
