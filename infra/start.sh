#!/bin/sh
set -eu

case "${1:-api}" in
  demo)
    exec python -m services.assistant.supervisor
    ;;
  api)
    exec python -m uvicorn services.assistant.api:app --host 0.0.0.0 --port "${PORT:-10000}"
    ;;
  worker)
    exec python -m services.assistant.worker
    ;;
  migrate)
    exec python -m services.assistant.migrate
    ;;
  *)
    exec "$@"
    ;;
esac
