#!/bin/sh
# wait-for.sh <host> <port> [timeout_seconds]
HOST="$1"; PORT="$2"; TIMEOUT="${3:-30}"
echo ">> Waiting up to ${TIMEOUT}s for $HOST:$PORT ..."
for i in $(seq $TIMEOUT); do
  (echo >/dev/tcp/$HOST/$PORT) >/dev/null 2>&1 && echo ">> $HOST:$PORT is up" && exit 0
  sleep 1
done
echo "!! Timeout waiting for $HOST:$PORT"; exit 1
