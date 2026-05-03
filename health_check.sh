#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/v1}"

echo "== models =="
curl -fsS "$BASE_URL/models" | python3 -m json.tool >/dev/null
echo "models ok"


echo "== proxy status =="
curl -fsS "$BASE_URL/proxy/status" | python3 -m json.tool >/dev/null
echo "proxy status ok"

echo "== text response =="
curl -fsS "$BASE_URL/responses" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "input": "Reply exactly: ok"
  }' | tee /tmp/ds_proxy_health_text.json | python3 -m json.tool >/dev/null

grep -q "ok" /tmp/ds_proxy_health_text.json
echo "text ok"

echo "== stream response =="
curl -fsS -N "$BASE_URL/responses" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "input": "Reply exactly: ok",
    "stream": true
  }' | tee /tmp/ds_proxy_health_stream.txt >/dev/null

grep -q "response.completed" /tmp/ds_proxy_health_stream.txt
echo "stream ok"

echo "All proxy HTTP health checks passed."

if [ "${CHECK_DEEPSEEK_BALANCE:-0}" = "1" ]; then
  echo "== DeepSeek balance =="
  curl -fsS "$BASE_URL/proxy/balance" | python3 -m json.tool
  echo "balance ok"
fi

