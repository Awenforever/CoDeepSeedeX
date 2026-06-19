#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/v1}"
BASE_URL="${BASE_URL%/}"
HEALTH_MODEL="${HEALTH_MODEL:-${MODEL:-deepseek-v4-flash}}"
CHECK_PROVIDER_BALANCE="${CHECK_PROVIDER_BALANCE:-${CHECK_DEEPSEEK_BALANCE:-0}}"

if [[ "$BASE_URL" == */v1 ]]; then
  DEFAULT_ROOT_URL="${BASE_URL%/v1}"
else
  DEFAULT_ROOT_URL="$BASE_URL"
fi

ROOT_URL="${ROOT_URL:-$DEFAULT_ROOT_URL}"
ROOT_URL="${ROOT_URL%/}"

TEXT_OUT="$(mktemp -t cox_health_text.XXXXXX.json)"
STREAM_OUT="$(mktemp -t cox_health_stream.XXXXXX.txt)"
trap 'rm -f "$TEXT_OUT" "$STREAM_OUT"' EXIT

echo "== healthz =="
curl --noproxy '*' -fsS "$ROOT_URL/healthz" | python3 -m json.tool >/dev/null
echo "healthz ok"

echo "== models =="
curl --noproxy '*' -fsS "$BASE_URL/models" | python3 -m json.tool >/dev/null
echo "models ok"

echo "== proxy status =="
curl --noproxy '*' -fsS "$BASE_URL/proxy/status" | python3 -m json.tool >/dev/null
echo "proxy status ok"

echo "== usage summary =="
curl --noproxy '*' -fsS "$BASE_URL/proxy/usage/summary" | python3 -m json.tool >/dev/null
echo "usage summary ok"

TEXT_PAYLOAD="$(
  HEALTH_MODEL="$HEALTH_MODEL" python3 - <<'__CODEXCHANGE_HEALTH_TEXT_PAYLOAD_JSON__'
import json
import os

print(json.dumps({"model": os.environ["HEALTH_MODEL"], "input": "Reply exactly: ok"}))
__CODEXCHANGE_HEALTH_TEXT_PAYLOAD_JSON__
)"

echo "== text response =="
curl --noproxy '*' -fsS "$BASE_URL/responses" \
  -H "Content-Type: application/json" \
  -d "$TEXT_PAYLOAD" | tee "$TEXT_OUT" | python3 -m json.tool >/dev/null

grep -q "ok" "$TEXT_OUT"
echo "text ok"

STREAM_PAYLOAD="$(
  HEALTH_MODEL="$HEALTH_MODEL" python3 - <<'__CODEXCHANGE_HEALTH_STREAM_PAYLOAD_JSON__'
import json
import os

print(json.dumps({"model": os.environ["HEALTH_MODEL"], "input": "Reply exactly: ok", "stream": True}))
__CODEXCHANGE_HEALTH_STREAM_PAYLOAD_JSON__
)"

echo "== stream response =="
curl --noproxy '*' -fsS -N "$BASE_URL/responses" \
  -H "Content-Type: application/json" \
  -d "$STREAM_PAYLOAD" | tee "$STREAM_OUT" >/dev/null

grep -q "response.completed" "$STREAM_OUT"
echo "stream ok"

echo "All CodeXchange HTTP health checks passed."

if [ "$CHECK_PROVIDER_BALANCE" = "1" ]; then
  echo "== provider balance =="
  curl --noproxy '*' -fsS "$BASE_URL/proxy/balance" | python3 -m json.tool
  echo "balance ok"
fi
