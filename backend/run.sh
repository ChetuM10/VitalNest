#!/bin/bash
# Lambda Web Adapter starts this script and proxies invocations to the port below.
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
