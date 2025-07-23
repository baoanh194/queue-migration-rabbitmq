# Q-Hop

The **Q-Hop** - Quick Hop from Classic to Quorum Queues
It provides functionality to:

1. **List Queues**
Detect and display all queues (with filtering, metrics, and JSON output support) via the RabbitMQ Management HTTP API.

2. **Migration Planning**
Analyze each queue’s properties (durability, exclusivity, auto-delete, and custom arguments) to determine its migration readiness. Identify any blockers or warnings, and output a detailed migration plan to user (the output also saved in a JSON file).

3. **Migration single or all queue**
Migrate a single classic queue or multiples queue in a vhost to quorum queue(s).

> **Note:**
> - The toolkit uses RabbitMQ credentials configured in `config/config.py`.
> - Ensure you set `RABBITMQ_HOST`, `RABBITMQ_USER`, and `RABBITMQ_PASS` before running any commands.

---

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [1. Listing Queues](#1-listing-queues)
  - [2. Migration Planner](#2-migration-planner)
  - [3. Queue Creation & Migration](#3-queue-creation--migration)
  - [4. Bulk Migration](#4-bulk-migration)
- [Error Handling](#error-handling)
- [Supported Features & Limitations](#supported-features--limitations)
- [Support](#support)

---

## Installation
### Clone the repository:
```
git@github.com:Seventh-State/queue-migration-tool.git
cd queue-migration-tool
```

### Install required dependencies:
pip install -r requirements.txt

### Configure RabbitMQ credentials:
Edit the config/config.py file as needed:
```
RABBITMQ_HOST = "http://localhost:15672"
RABBITMQ_USER = "guest"
RABBITMQ_PASS = "guest"
```

## Usage
All commands are invoked via the q-hop CLI entry point. You can get help for any command by appending --help.
```
$ q-hop --help
usage: q-hop [-h] {list_queues,planner,migrate_queue,migrate_all} ...

CLI for RabbitMQ migration tasks

positional arguments:
  {list_queues,planner,migrate_queue,migrate_all}
                        Available commands
    list_queues         List RabbitMQ queues
    planner             Analyze queue migration suitability
    migrate_queue       Migrate an existing queue to a new type (quorum/stream)
    migrate_all         Migrate all classic queues in a vhost to a new type

options:
  -h, --help            show this help message and exit
```

### Listing Queues

The `list-queues` command detects and lists all queues in the RabbitMQ cluster,
providing information about their state, policies, and arguments.

```bash
$ q-hop list_queues

09:55:03 /Users/baoadinh/dev/queue-migration-tool$ q-hop list_queues
VHost               Queue Name          Type      Messages  State          Policies  Publish/s      Deliver/s      Arguments
=======================================================================================================================================
/                   Test1               quorum    3         running        None      0.00           0.00            {"leader-locator": "client-local", "queue-initial-cluster-size": 3, "x-queue-type": "quorum"}
/                   Test2               quorum    3         running        None      0.00           0.00            {"leader-locator": "client-local", "queue-initial-cluster-size": 3, "x-queue-type": "quorum"}
/                   sfasfsdfd           quorum    0         running        None      0.00           0.00            {"leader-locator": "client-local", "queue-initial-cluster-size": 3, "x-queue-type": "quorum"}
/                   target              quorum    7         running        None      0.00           0.00            {"x-queue-type": "quorum"}
/                   testing-2           quorum    0         running        None      0.00           0.00            {"x-queue-type": "quorum"}
/                   testing-3           quorum    0         running        None      0.00           0.00            {"x-queue-type": "quorum"}
/                   testing_1           quorum    5         running        None      0.00           0.00            {"x-queue-type": "quorum"}
```

Options:

```--name <queue_name>```: Filter queues by name.

```--vhost <vhost_name>```: Filter queues by vhost. Use url encoding for vhost names (e.g., ```%2f``` for ```/```).

```--json```: Output queue details in JSON format.

Example Usage:

Filtering by Queue Name:
```bash
$ q-hop list_queues --name ttt_2
VHost               Queue Name          Type      Messages  State          Policies  Publish/s      Deliver/s      Arguments
=======================================================================================================================================
/                   ttt_2               quorum    0         running        None      0.00           0.00            {"x-queue-type": "quorum"}
```

JSON Output:
```bash
$ q-hop list_queues --name ttt_2 --vhost %2f --json
[
  {
    "arguments": {
      "x-queue-type": "quorum"
    },
    "auto_delete": false,
    "consumer_capacity": 0,
    "consumer_utilisation": 0,
    "consumers": 0,
    "durable": true,
    "effective_policy_definition": {},
    "exclusive": false,
    "leader": "rabbit@rmq1.example",
    "members": [
      "rabbit@rmq1.example"
    ],
    "memory": 42572,
    "message_bytes": 0,
    "message_bytes_dlx": 0,
    "message_bytes_persistent": 0,
    "message_bytes_ram": 0,
    "message_bytes_ready": 0,
    "message_bytes_unacknowledged": 0,
    "messages": 0,
    "messages_details": {
      "rate": 0.0
    },
    "messages_dlx": 0,
    "messages_persistent": 0,
    "messages_ram": 0,
    "messages_ready": 0,
    "messages_ready_details": {
      "rate": 0.0
    },
    "messages_unacknowledged": 0,
    "messages_unacknowledged_details": {
      "rate": 0.0
    },
    "name": "ttt_2",
    "node": "rabbit@rmq1.example",
    "online": [
      "rabbit@rmq1.example"
    ],
    "open_files": {
      "rabbit@rmq1.example": 0
    },
    "reductions": 46812,
    "reductions_details": {
      "rate": 58.8
    },
    "state": "running",
    "type": "quorum",
    "vhost": "/"
  }
]
```

Error Handling:
The tool provides improved error handling for invalid filters or missing data.
For example:
```bash
$ q-hop list_queues --vhost /  # Incorrect vhost
Error fetching queue details: 404 Client Error: Not Found for url: http://localhost:15672/api/queues//
```


### Migration Planner
The migration planner analyzes queue properties to determine migration readiness.
It checks for blockers (e.g., non-durable, exclusive, or auto-delete queues)
and warns about unsupported settings.


```
$ q-hop planner --help
usage: q-hop planner [-h] [--vhost VHOST] [--queue QUEUE] [--all] [--json] [--file FILE]

options:
  -h, --help     show this help message and exit
  --vhost VHOST  Virtual host (default: %2f)
  --queue QUEUE  Specify a queue name to analyze
  --all          Analyze all queues in the specified vHost
  --json         Output results in JSON format
  --file FILE    Path to exported RabbitMQ definitions JSON file
```

Example (Analyze a specific queue):
```
$ q-hop planner --queue test
[DEBUG] Received args: Namespace(vhost='%2f', queue='test', all=False, json=False, file=None)

**Migration Analysis Result**:
Queue Name: test
Current Type: classic

**Good for Migration**

**Warnings for Quorum Migration**:
   - Setting 'x-queue-version' will be removed during migration.
   - Setting 'x-queue-master-locator' will be removed during migration.
```

### Queue Migration
Create a new queue based on the migration plan.

```
$ q-hop migrate_queue --help
usage: q-hop migrate_queue [-h] --vhost VHOST --queue QUEUE --type {quorum,stream}

options:
  -h, --help            show this help message and exit
  --vhost VHOST         Virtual host for the queue
  --queue QUEUE         Name of the queue to migrate
  --type {quorum,stream} Target queue type
```

Example:

```bash
$ q-hop migrate_queue --vhost %2f --queue testing --type quorum
Message transfer complete. 0 message(s)                 moved from 'testing' to 'testing_temp_migrated'.
No messages found in 'testing'. Continuing migration.
Message transfer complete. 0 message(s)                 moved from 'testing_temp_migrated' to 'testing'.
Migration complete! Queue 'testing' is now 'quorum'.
```

### Migrate all the queues
Migrate all queue in a specific vhost and specific file
```
$ q-hop migrate_all --vhost %2f --type quorum
Initiating migration of 3 classic queues in vhost '%2f' to 'quorum'.
Migrating queue: readme_1
Message transfer complete. 5 message(s) moved from 'readme_1' to 'readme_1_temp_migrated'.
Message transfer complete. 5 message(s) moved from 'readme_1_temp_migrated' to 'readme_1'.
Migration complete! Queue 'readme_1' is now 'quorum'.
Migrating queue: readme_2
Message transfer complete. 5 message(s) moved from 'readme_2' to 'readme_2_temp_migrated'.
Message transfer complete. 5 message(s) moved from 'readme_2_temp_migrated' to 'readme_2'.
Migration complete! Queue 'readme_2' is now 'quorum'.
Migrating queue: readme_3
Message transfer complete. 0 message(s) moved from 'readme_3' to 'readme_3_temp_migrated'.
No messages found in 'readme_3'. Continuing migration.
Message transfer complete. 0 message(s) moved from 'readme_3_temp_migrated' to 'readme_3'.
Migration complete! Queue 'readme_3' is now 'quorum'.
Migration process initiated for all classic queues.
```

## Support
For any issues or questions, please open an issue on GitHub or contact the development team.

## Notes and Limitations

Queues with unsupported features (e.g., x-max-priority, lazy mode, ha-* policies) will be flagged and require manual intervention.

Only queues using supported arguments can be migrated automatically. Unsupported arguments must be handled manually.

Ensure your RabbitMQ Management plugin is enabled and accessible via the configured host URL.