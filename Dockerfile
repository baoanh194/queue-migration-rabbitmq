FROM python:3.12-slim as builder

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirement.txt pytest

# Run unit tests only, ignoring integration tests
RUN pytest test/tests/ -q --disable-warnings --maxfail=1 --ignore=test/tests/perf

# Build wheel and sdist
RUN python setup.py sdist bdist_wheel

# --- Release image ---
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/dist /app/dist
COPY wait-for-it.sh /usr/local/bin/wait-for-it
RUN chmod +x /usr/local/bin/wait-for-it
COPY requirement.txt /app/requirement.txt
COPY src/ /app/src/
COPY config/ /app/config/
COPY test/ /app/test/

# Install the plugin package
RUN pip install /app/dist/*.whl

RUN pip install -r /app/requirement.txt pytest

ENV PYTHONPATH=/app

CMD ["echo", "Plugin package ready."]
