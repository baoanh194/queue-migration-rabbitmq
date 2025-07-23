PYTHON=python3

# Run all tests in the current directory
test:
	@echo "Running all tests..."
	$(PYTHON) -m unittest discover -v

# Run a specific test file
# Usage: make test-file FILE=test_queue_migrator.py
test-file:
	@echo "Running test file: $(FILE)"
	$(PYTHON) -m unittest $(FILE:.py=)

# Run a specific test case
# Usage: make test-case FILE=test_cli.py CASE=TestCLI.test_list_queues_json_output
test-case:
	@echo "Running specific test case: $(CASE) from file: $(FILE)"
	$(PYTHON) -m unittest $(FILE:.py=).$(CASE)

# Clean up generated files
clean:
	@echo "Cleaning up migration_log.txt and __pycache__ directories..."
	@find ../../ -type f -name "migration_log.txt" -delete
	@find ../../ -type d -name "__pycache__" -exec rm -rf {} +

.PHONY: test test-file test-case clean
