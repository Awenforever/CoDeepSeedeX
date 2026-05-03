# Regression Checklist

Use this checklist after changes to the proxy.

## 1. Static sanity

```bash
cd ~/projects/deepseek-responses-proxy
git status --short
git diff --check
```

## 2. Unit tests

```bash
cd ~/projects/deepseek-responses-proxy
source .venv/bin/activate

TMPDIR=~/projects/deepseek-responses-proxy/.tmp \
PYTHONPATH=. \
python -m pytest -q -s
```

## 3. HTTP health check

Stable profile:

```bash
./health_check.sh
```

Thinking profile:

```bash
BASE_URL=http://127.0.0.1:8001/v1 ./health_check.sh
```

Optional official DeepSeek balance check:

```bash
CHECK_DEEPSEEK_BALANCE=1 ./health_check.sh
```

## 4. Stable Codex regression

```bash
cd /tmp
mkdir -p codex-regression-test
cd codex-regression-test
codex --profile deepseek
```

Run these prompts:

```text
Reply exactly: ok
```

Expected: Codex replies exactly or effectively `ok`.

```text
Run `pwd` and tell me the working directory.
```

Expected: Codex executes the shell command and reports the current directory.

```text
Create a file named test.txt containing exactly "ok", read it back, then delete it.
```

Expected: Codex creates, reads, and deletes the file through the tool-call loop.

## 5. Thinking Codex regression

```bash
cd /tmp
mkdir -p codex-thinking-regression-test
cd codex-thinking-regression-test
codex --profile deepseek-thinking
```

Run the same three prompts.

Expected: text, tool call, and tool continuation all work.

## 6. Resume regression

Stable:

```bash
codex --profile deepseek resume --last
```

Thinking:

```bash
codex --profile deepseek-thinking resume --last
```

If both profiles were used recently in the same directory, prefer explicit session IDs.

## 7. Usage ledger verification

After one successful request:

```bash
curl -sS http://127.0.0.1:8000/v1/proxy/usage/summary | python3 -m json.tool
curl -sS "http://127.0.0.1:8000/v1/proxy/usage?limit=5" | python3 -m json.tool
```

Expected:

* request count increases
* token fields are numeric
* `estimated_cost_usd` is present
* `thinking_enabled` matches the selected profile

For thinking mode, use port `8001`.

## 8. Do not release if any of these fail

Do not commit or tag a release if:

* pytest fails
* health check fails
* real Codex tool-call continuation fails
* response retrieval by `previous_response_id` is broken
* thinking mode rejects repaired history
* proxy exposes raw traceback to Codex for upstream errors
