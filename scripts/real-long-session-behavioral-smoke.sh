#!/usr/bin/env bash
set -Eeuo pipefail

stage="real-long-session-behavioral-smoke"
allow_bypass=0
dry_run=0
limit=200
timeout_seconds=5
prefix=""

usage() {
  cat <<'USAGE'
Usage:
  scripts/real-long-session-behavioral-smoke.sh --dry-run
  scripts/real-long-session-behavioral-smoke.sh --allow-bypass [--limit 200] [--timeout 5] [--prefix /tmp/name]

Purpose:
  Run a controlled real Codex long-session behavioral smoke test against the local thinking proxy.

Safety:
  The real smoke uses:
    codex exec --profile deepseek-thinking --dangerously-bypass-approvals-and-sandbox

  This bypass is required because Codex workspace-write sandbox cannot reliably access
  the host WSL listener at 127.0.0.1:8001. The smoke prompt restricts Codex to
  read-only repository commands and a controlled large-output command.

Outputs:
  All logs are written under /tmp by default. The terminal prints only compact paths.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --allow-bypass)
      allow_bypass=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --limit)
      limit="${2:?missing --limit value}"
      shift 2
      ;;
    --timeout)
      timeout_seconds="${2:?missing --timeout value}"
      shift 2
      ;;
    --prefix)
      prefix="${2:?missing --prefix value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error=unknown_argument:$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$repo_root" ]; then
  echo "error=not_inside_git_checkout" >&2
  exit 2
fi
cd "$repo_root"

if [ -z "$prefix" ]; then
  prefix="/tmp/v2.7a32-real-long-session-behavioral-smoke-$(date +%Y%m%d-%H%M%S)"
fi

out="${prefix}.txt"
prompt_file="${prefix}.prompt.txt"
codex_jsonl="${prefix}.codex.jsonl"
codex_stderr="${prefix}.codex.stderr.txt"
codex_final="${prefix}.codex-final.txt"
post_behavioral_json="${prefix}.post-behavioral.json"
post_behavioral_summary="${prefix}.post-behavioral-summary.json"
comparison_summary="${prefix}.comparison-summary.json"

if [ "$dry_run" -eq 1 ]; then
  {
    echo "===== stage ====="
    echo "stage=${stage}-dry-run"
    echo "prefix=${prefix}"
    echo
    echo "===== plan ====="
    echo "repo_root=${repo_root}"
    echo "limit=${limit}"
    echo "timeout=${timeout_seconds}"
    echo "uses_bypass=${allow_bypass}"
    echo "codex_profile=deepseek-thinking"
    echo "real_run_requires=--allow-bypass"
  } > "$out"
  printf 'stage=%s\nrun_ok=1\nout=%s\n' "${stage}-dry-run" "$out"
  exit 0
fi

if [ "$allow_bypass" -ne 1 ]; then
  {
    echo "===== stage ====="
    echo "stage=${stage}"
    echo "prefix=${prefix}"
    echo
    echo "===== refused ====="
    echo "run_ok=0"
    echo "reason=allow_bypass_required"
    echo "message=This smoke requires codex exec --dangerously-bypass-approvals-and-sandbox because workspace-write cannot access 127.0.0.1:8001."
  } > "$out"
  printf 'stage=%s\nrun_ok=0\nout=%s\n' "$stage" "$out"
  exit 3
fi

run_ok=1

{
  echo "===== stage ====="
  echo "stage=${stage}"
  echo "prefix=${prefix}"

  echo
  echo "===== repo preflight ====="
  echo "repo_root=${repo_root}"
  echo "branch_before=$(git branch --show-current)"
  echo "status_count_before=$(git status --short | wc -l)"
  echo "head_before=$(git log --oneline --decorate --max-count=1)"
  if [ "$(git status --short | wc -l)" -ne 0 ]; then
    echo "error=working_tree_not_clean"
    exit 20
  fi

  echo
  echo "===== proxy preflight ====="
  curl -sS --max-time "$timeout_seconds" http://127.0.0.1:8001/healthz
  echo
  .venv/bin/python -m deepseek_responses_proxy.cli debug behavioral --thinking --limit "$limit" --timeout "$timeout_seconds" > "${prefix}.pre-behavioral.json"

  echo
  echo "===== write codex prompt ====="
  cat > "$prompt_file" <<'PROMPT'
You are running a controlled real long-session behavioral validation for the deepseek-responses-proxy repository.

Hard constraints:
1. Do not modify repository files.
2. Do not commit anything.
3. Do not print secrets or environment variables.
4. Use only read-only repository commands, plus the explicitly requested controlled large-output command below.
5. After running the commands, reply with only compact JSON. Do not use Markdown fences.

Working directory is already the repository root.

Run these commands in order:
1. git branch --show-current && git status --short && git log --oneline --decorate --max-count=3
2. .venv/bin/python -m pytest tests/test_cli.py::test_cli_debug_behavioral_summarizes_long_session_readiness -q
3. .venv/bin/python - <<'PY_TRIM_TRIGGER'
print("REAL_LONG_SESSION_TRIM_TRIGGER_BEGIN")
for i in range(3000):
    print(f"REAL_LONG_SESSION_TRIM_TRIGGER line={i:04d} " + ("controlled-output-" * 8))
print("REAL_LONG_SESSION_TRIM_TRIGGER_END")
PY_TRIM_TRIGGER
4. .venv/bin/python -m deepseek_responses_proxy.cli debug behavioral --thinking --limit 200 --timeout 5
5. git status --short

Your final answer must be valid compact JSON only, with these keys:
{
  "branch": "...",
  "working_tree_clean": true or false,
  "current_head": "...",
  "current_version": "...",
  "pytest_result": "...",
  "behavioral_status": "...",
  "behavioral_recommendation": "...",
  "trimmed_categories": ["..."],
  "tool_output_trim_applied_count": number or null,
  "tool_output_trim_chars_removed": number or null,
  "next_safe_command": "...",
  "risks": ["..."]
}
PROMPT
  echo "prompt_file=${prompt_file}"

  echo
  echo "===== run codex real session with bypass ====="
  timeout 900s codex exec \
    --profile deepseek-thinking \
    --dangerously-bypass-approvals-and-sandbox \
    --cd "$repo_root" \
    --json \
    --output-last-message "$codex_final" \
    "$(cat "$prompt_file")" \
    > "$codex_jsonl" 2> "$codex_stderr"

  echo
  echo "===== post behavioral check ====="
  .venv/bin/python -m deepseek_responses_proxy.cli debug behavioral --thinking --limit "$limit" --timeout "$timeout_seconds" > "$post_behavioral_json"

  .venv/bin/python - "$post_behavioral_json" "$post_behavioral_summary" <<'PY_POST_SUMMARY'
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, "r", encoding="utf-8") as f:
    data = json.load(f)

behavioral = data.get("behavioral") or {}
metrics = behavioral.get("metrics") or {}
summary = {
    "cli_status": data.get("status"),
    "debug_command": data.get("debug_command"),
    "behavioral_status": behavioral.get("status"),
    "behavioral_recommendation": behavioral.get("recommendation"),
    "blockers": behavioral.get("blockers"),
    "assertions": behavioral.get("assertions"),
    "metrics": {
        "trace_event_count": metrics.get("trace_event_count"),
        "response_count": metrics.get("response_count"),
        "context_latest_chars": metrics.get("context_latest_chars"),
        "context_max_chars": metrics.get("context_max_chars"),
        "latest_prompt_tokens": metrics.get("latest_prompt_tokens"),
        "max_prompt_tokens": metrics.get("max_prompt_tokens"),
        "tool_output_trim_event_count": metrics.get("tool_output_trim_event_count"),
        "tool_output_trim_applied_count": metrics.get("tool_output_trim_applied_count"),
        "tool_output_trim_chars_removed": metrics.get("tool_output_trim_chars_removed"),
        "image_payload_trim_count": metrics.get("image_payload_trim_count"),
        "trimmed_categories": metrics.get("trimmed_categories"),
        "long_session_recommendation": metrics.get("long_session_recommendation"),
    },
}
with open(dst, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
PY_POST_SUMMARY

  echo
  echo "===== compare codex final with external postcheck ====="
  .venv/bin/python - "$codex_final" "$post_behavioral_summary" "$comparison_summary" <<'PY_COMPARE'
import json
import re
import sys

final_path, post_path, dst = sys.argv[1:4]
final_text = open(final_path, "r", encoding="utf-8", errors="replace").read().strip()
post = json.load(open(post_path, "r", encoding="utf-8"))

fence = re.search(r"```(?:json)?\s*(.*?)\s*```", final_text, flags=re.S)
candidate = fence.group(1).strip() if fence else final_text

try:
    final = json.loads(candidate)
    parse_ok = True
except Exception as exc:
    final = {"_parse_error": repr(exc), "_raw_prefix": final_text[:1000]}
    parse_ok = False

metrics = post.get("metrics") or {}
comparison = {
    "final_json_parse_ok": parse_ok,
    "final_used_markdown_fence": bool(fence),
    "final_branch": final.get("branch"),
    "final_working_tree_clean": final.get("working_tree_clean"),
    "final_current_version": final.get("current_version"),
    "final_pytest_result": final.get("pytest_result"),
    "final_behavioral_status": final.get("behavioral_status"),
    "post_behavioral_status": post.get("behavioral_status"),
    "behavioral_status_matches": final.get("behavioral_status") == post.get("behavioral_status"),
    "final_tool_output_trim_applied_count": final.get("tool_output_trim_applied_count"),
    "post_tool_output_trim_applied_count": metrics.get("tool_output_trim_applied_count"),
    "trim_applied_count_matches": final.get("tool_output_trim_applied_count") == metrics.get("tool_output_trim_applied_count"),
    "final_tool_output_trim_chars_removed": final.get("tool_output_trim_chars_removed"),
    "post_tool_output_trim_chars_removed": metrics.get("tool_output_trim_chars_removed"),
    "trim_chars_removed_matches": final.get("tool_output_trim_chars_removed") == metrics.get("tool_output_trim_chars_removed"),
    "final_trimmed_categories": final.get("trimmed_categories"),
    "post_trimmed_categories": metrics.get("trimmed_categories"),
    "final_risks": final.get("risks"),
}
with open(dst, "w", encoding="utf-8") as f:
    json.dump(comparison, f, ensure_ascii=False, indent=2, sort_keys=True)
print(json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True))
PY_COMPARE

  echo
  echo "===== codex stderr filtered ====="
  grep -Ei "error|failed|panic|timeout|rate|limit|unauthorized|forbidden|exception|approval|sandbox|connection|refused|operation not permitted" "$codex_stderr" | tail -n 120 || true

  echo
  echo "===== codex jsonl summary ====="
  .venv/bin/python - "$codex_jsonl" <<'PY_JSONL'
import json
import sys
from collections import Counter

path = sys.argv[1]
counts = Counter()
large_output_seen = False
behavioral_seen = False
with open(path, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            item = json.loads(line)
        except Exception:
            counts["json_parse_error"] += 1
            continue
        t = item.get("type") or item.get("event") or "<unknown>"
        counts[str(t)] += 1
        text = json.dumps(item, ensure_ascii=False)
        if "REAL_LONG_SESSION_TRIM_TRIGGER" in text:
            large_output_seen = True
        if "debug behavioral" in text or '"behavioral"' in text:
            behavioral_seen = True
print(json.dumps({
    "event_counts": dict(counts),
    "large_output_seen": large_output_seen,
    "behavioral_seen": behavioral_seen,
}, ensure_ascii=False, sort_keys=True))
PY_JSONL

  echo
  echo "===== repo postcheck ====="
  echo "branch_after=$(git branch --show-current)"
  echo "status_count_after=$(git status --short | wc -l)"
  git status --short

  echo
  echo "===== artifacts ====="
  echo "prompt_file=${prompt_file}"
  echo "codex_jsonl=${codex_jsonl}"
  echo "codex_stderr=${codex_stderr}"
  echo "codex_final=${codex_final}"
  echo "post_behavioral_json=${post_behavioral_json}"
  echo "post_behavioral_summary=${post_behavioral_summary}"
  echo "comparison_summary=${comparison_summary}"

  echo
  echo "===== final ====="
  echo "run_ok=1"
  echo "out=${out}"
} > "$out" 2>&1 || run_ok=0

if [ "$run_ok" -ne 1 ]; then
  {
    echo
    echo "===== final wrapper ====="
    echo "run_ok=0"
    echo "out=${out}"
    echo "codex_jsonl=${codex_jsonl}"
    echo "codex_stderr=${codex_stderr}"
    echo "codex_final=${codex_final}"
    echo "post_behavioral_summary=${post_behavioral_summary}"
    echo "comparison_summary=${comparison_summary}"
  } >> "$out"
fi

printf 'stage=%s\nrun_ok=%s\nout=%s\ncodex_final=%s\ncomparison_summary=%s\npost_behavioral_summary=%s\n' "$stage" "$run_ok" "$out" "$codex_final" "$comparison_summary" "$post_behavioral_summary"
