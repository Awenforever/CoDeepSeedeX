#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${DEEPSEEK_PROXY_INSTALL_DIR:-$HOME/.local/share/deepseek-responses-proxy}"
REPO_URL="${DEEPSEEK_PROXY_REPO_URL:-https://github.com/Awenforever/CoDeepSeedeX.git}"
LATEST_RELEASE_API_URL="${DEEPSEEK_PROXY_LATEST_RELEASE_API_URL:-https://api.github.com/repos/Awenforever/CoDeepSeedeX/releases/latest}"
INSTALL_REF="${DEEPSEEK_PROXY_INSTALL_REF:-}"
BIN_DIR="${DEEPSEEK_PROXY_BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${DEEPSEEK_PROXY_CONFIG_DIR:-$HOME/.config/deepseek-responses-proxy}"
ENV_FILE="${DEEPSEEK_PROXY_ENV_FILE:-$CONFIG_DIR/env}"
MANIFEST_FILE="${DEEPSEEK_PROXY_MANIFEST_FILE:-$CONFIG_DIR/install-manifest.env}"
INSTALL_LOG="${DEEPSEEK_PROXY_INSTALL_LOG:-/tmp/codeepseedex-install-$(date +%Y%m%d_%H%M%S).log}"
LOCAL_BACKUP_DIR="${DEEPSEEK_PROXY_BACKUP_DIR:-/tmp/codeepseedex-install-backups-$(date +%Y%m%d_%H%M%S)}"
PYTHON_BIN="${DEEPSEEK_PROXY_PYTHON_BIN:-python3}"

DRY_RUN=0
NON_INTERACTIVE=0
FORCE_CODEX_WRAPPER="${DEEPSEEK_PROXY_FORCE_CODEX_WRAPPER:-0}"
FORCE_DSPROXY_WRAPPER="${DEEPSEEK_PROXY_FORCE_DSPROXY_WRAPPER:-0}"
INSTALL_CODEX_PROFILE=1
INSTALL_CODEX_WRAPPER=1
INSTALL_SHELL_PROFILE=1
SHELL_PROFILE_FILE=""
UNINSTALL=0
REMOVE_FILES=0
PROMPTED_MODEL_PROVIDER=""
PROMPTED_MODEL_BASE_URL=""
PROMPTED_MODEL_NAME=""

logo() {
  cat <<'LOGO'
   ____      ____                 ____              _      __  __
  / ___|___ |  _ \  ___  ___ _ __/ ___|  ___  ___  __| | ___ \ \/ /
 | |   / _ \| | | |/ _ \/ _ \ '_ \___ \ / _ \/ _ \/ _` |/ _ \ \  /
 | |__| (_) | |_| |  __/  __/ |_) |__) |  __/  __/ (_| |  __/ /  \
  \____\___/|____/ \___|\___| .__/____/ \___|\___|\__,_|\___|/_/\_\
                             |_|

  CoDeepSeedeX
  Codex × DeepSeek local Responses proxy
LOGO
}

usage() {
  cat <<'USAGE'
Usage: scripts/install.sh [options]

Options:
  --dry-run              Print actions without applying changes
  --non-interactive      Do not prompt; use environment/default values
  --install-dir DIR      Installation directory
  --repo-url URL         Git repository URL
  --install-ref REF      Target release tag or explicit git ref; defaults to GitHub Latest Release
  --bin-dir DIR          Directory for dsproxy and optional codex wrapper
  --config-dir DIR       Config directory
  --env-file FILE        Env file path
  --python-bin PATH     Python interpreter for venv, default: $DEEPSEEK_PROXY_PYTHON_BIN or python3
  --no-codex-profile     Skip Codex profile installation
  --no-codex-wrapper     Skip safe codex wrapper installation
  --no-shell-profile    Do not update shell startup files for PATH/env loading
  --uninstall            Remove profiles and wrappers installed by CoDeepSeedeX
  --remove-files         With --uninstall, also remove install dir and env files
  -h, -H, --help         Show help

The API key is entered with hidden input and written to a chmod 600 env file.
This is not cryptographic encryption.
USAGE
}

step() {
  printf '\n\033[1;36m%s\033[0m\n' "$1"
}

ok() {
  printf '  \033[1;32m✓\033[0m %s\n' "$1"
}

warn() {
  printf '  \033[1;33m!\033[0m %s\n' "$1"
}

divider() {
  printf '\n\033[1;36m%s\033[0m\n' '────────────────────────────────────────────────────────────'
}

section_title() {
  printf '\n\033[1;36m%s\033[0m\n' "$1"
}

sub_title() {
  printf '\n\033[1;35m%s\033[0m\n' "$1"
}

run_quiet() {
  local label="$1"
  shift
  printf '  ... %s\n' "$label"

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ %s\n' "$*" >> "$INSTALL_LOG"
    ok "$label"
    return 0
  fi

  if "$@" >> "$INSTALL_LOG" 2>&1; then
    ok "$label"
  else
    warn "$label failed. See log: $INSTALL_LOG"
    return 1
  fi
}

run_git_quiet() {
  local label="$1"
  local operation="$2"
  shift 2
  printf '  ... %s\n' "$label"

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ %s\n' "$*" >> "$INSTALL_LOG"
    ok "$label"
    return 0
  fi

  if "$@" >> "$INSTALL_LOG" 2>&1; then
    ok "$label"
    return 0
  fi

  warn "$label failed. See log: $INSTALL_LOG"
  warn "Git repository setup failed during: $operation"
  warn "Possible causes: network/TLS/proxy interruption, GitHub access failure, invalid --repo-url, repository permission issue, or a conflicting install directory."
  warn "Next step: retry after checking network/proxy/CA certificates, or use --repo-url /path/to/local-or-mirrored-repo."

  {
    printf '\n===== CoDeepSeedeX git setup diagnosis =====\n'
    printf 'operation=%s\n' "$operation"
    printf 'repo_url=%s\n' "$REPO_URL"
    printf 'install_dir=%s\n' "$INSTALL_DIR"
    printf 'hint=%s\n' "If this is a GitHub TLS/network failure, retry later or rerun with --repo-url pointing to a local or mirrored repository."
    printf 'hint=%s\n' "If the install directory exists but is not a valid clone, move it aside or choose another --install-dir."
  } >> "$INSTALL_LOG"

  return 1
}


resolve_install_ref() {
  if [ -n "$INSTALL_REF" ]; then
    printf '%s\n' "$INSTALL_REF"
    return 0
  fi

  local tag
  tag="$(curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 --connect-timeout 15 --max-time 60 "$LATEST_RELEASE_API_URL" |
    sed -nE 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' |
    head -n 1)"
  if [ -z "$tag" ]; then
    echo "ERROR: could not resolve GitHub Latest Release tag; set DEEPSEEK_PROXY_INSTALL_REF or pass --install-ref" >&2
    return 1
  fi
  printf '%s\n' "$tag"
}

read_from_tty() {
  local prompt="$1"
  local default_value="${2:-}"
  local value=""

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  if [ -n "$default_value" ]; then
    printf "%s [%s]: " "$prompt" "$default_value" > /dev/tty
  else
    printf "%s: " "$prompt" > /dev/tty
  fi

  IFS= read -r value < /dev/tty || true
  if [ -z "$value" ]; then
    value="$default_value"
  fi
  printf '%s\n' "$value"
}

read_yes_no() {
  local prompt="$1"
  local default_value="${2:-Y}"
  local value=""

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  printf "%s " "$prompt" > /dev/tty
  IFS= read -r value < /dev/tty || true
  if [ -z "$value" ]; then
    value="$default_value"
  fi
  printf '%s\n' "$value"
}

read_secret_from_tty() {
  local prompt="$1"
  local default_value="${2:-}"
  local value=""

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  if [ -n "$default_value" ]; then
    printf "%s [hidden, press Enter to keep existing]: " "$prompt" > /dev/tty
  else
    printf "%s [hidden]: " "$prompt" > /dev/tty
  fi

  stty -echo < /dev/tty 2>/dev/null || true
  IFS= read -r value < /dev/tty || true
  stty echo < /dev/tty 2>/dev/null || true
  printf "\n" > /dev/tty

  if [ -z "$value" ]; then
    value="$default_value"
  fi
  printf '%s\n' "$value"
}

find_real_codex() {
  local wrapper_path="$1"
  local candidate=""

  if [ -n "${CODEEPSEEDEX_REAL_CODEX:-}" ] && [ -x "$CODEEPSEEDEX_REAL_CODEX" ]; then
    printf '%s\n' "$CODEEPSEEDEX_REAL_CODEX"
    return 0
  fi

  while IFS= read -r candidate; do
    if [ "$candidate" != "$wrapper_path" ] && [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(type -P -a codex 2>/dev/null || true)

  return 1
}


json_string() {
  "$PYTHON_BIN" - "$1" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1]))
PY
}

test_deepseek_api_key() {
  local api_key="$1"
  if [ -z "$api_key" ]; then
    return 1
  fi
  local result
  result="$("$PYTHON_BIN" - "$api_key" <<'PY'
import json
import sys
import urllib.request
import urllib.error

api_key = sys.argv[1]
request = urllib.request.Request(
    "https://api.deepseek.com/user/balance",
    headers={
        "Authorization": "Bearer " + api_key,
        "Accept": "application/json",
    },
    method="GET",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
        print("ok" if 200 <= int(response.status) < 300 else "bad")
except Exception:
    print("bad")
PY
)"
  [ "$result" = "ok" ]
}


test_web_search_api_key() {
  local provider="$1"
  local api_key="$2"
  if [ -z "$provider" ] || [ -z "$api_key" ]; then
    return 1
  fi
  local result
  result="$("$PYTHON_BIN" - "$provider" "$api_key" <<'PYCODEEPSEEDEX_INSTALL_WEB_VALIDATION_P28A1'
import json
import sys
import urllib.parse
import urllib.request

provider = sys.argv[1].strip().lower()
api_key = sys.argv[2]
query = "test"

def has_auth_error(raw):
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    values = []
    for key in ("error", "error_message", "message", "msg", "detail", "code", "status_code"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value)
        elif isinstance(value, dict):
            for nested in ("message", "detail"):
                nested_value = value.get(nested)
                if isinstance(nested_value, str) and nested_value.strip():
                    values.append(nested_value)
    for value in values:
        lowered = value.lower()
        if any(token in lowered for token in ("unauthorized", "forbidden", "api key", "api-key", "apikey", "access key", "access token", "token", "authentication", "authorization", "auth", "invalid api key", "invalid apikey", "invalid token", "invalid authentication", "invalid authorization")) or lowered in {"1002", "401", "403"}:
            return True
    if str(data.get("status") or "").strip().lower() in {"error", "failed", "failure"}:
        return True
    return False

def request(method, url, headers=None, payload=None):
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request_headers.setdefault("Accept", "application/json")
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return 200 <= int(resp.status) < 300 and not has_auth_error(raw)
    except Exception:
        return False

if provider == "serpapi":
    params = urllib.parse.urlencode({"engine": "google", "q": query, "api_key": api_key, "num": "1"})
    ok = request("GET", "https://serpapi.com/search.json?" + params)
elif provider == "tavily":
    ok = request("POST", "https://api.tavily.com/search", {"Authorization": "Bearer " + api_key}, {"query": query, "max_results": 1, "search_depth": "basic", "include_answer": False})
elif provider == "exa":
    ok = request("POST", "https://api.exa.ai/search", {"Authorization": "Bearer " + api_key}, {"query": query, "numResults": 1})
elif provider == "firecrawl":
    ok = request("POST", "https://api.firecrawl.dev/v2/search", {"Authorization": "Bearer " + api_key}, {"query": query, "limit": 1})
else:
    ok = False
print("ok" if ok else "bad")
PYCODEEPSEEDEX_INSTALL_WEB_VALIDATION_P28A1
)"
  [ "$result" = "ok" ]
}


test_image_generation_api_key() {
  local provider="$1"
  local api_key="$2"
  if [ -z "$provider" ] || [ -z "$api_key" ]; then
    return 1
  fi
  local result
  result="$("$PYTHON_BIN" - "$provider" "$api_key" <<'PYCODEEPSEEDEX_INSTALL_IMAGE_VALIDATION_P28A3'
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

provider = sys.argv[1].strip().lower()
api_key = sys.argv[2]

def collect_values(data):
    values = []

    def collect(value):
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, (int, float)):
            values.append(str(value))
        elif isinstance(value, dict):
            for nested in ("error", "error_message", "message", "msg", "detail", "code", "status_code"):
                collect(value.get(nested))
        elif isinstance(value, list):
            for item in value[:5]:
                collect(item)

    if isinstance(data, dict):
        for key in ("error", "error_message", "message", "msg", "detail", "code", "status_code"):
            collect(data.get(key))
    return values

def decode(raw):
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}

def has_auth_error(raw):
    data = decode(raw)
    for value in collect_values(data):
        lowered = value.lower()
        if lowered in {"1002", "401", "403"} or any(token in lowered for token in ("unauthorized", "forbidden", "api key", "api-key", "apikey", "access key", "access token", "token", "authentication", "authorization", "auth", "invalid api key", "invalid apikey", "invalid token", "invalid authentication", "invalid authorization")):
            return True
    return False

def has_provider_error_body(raw):
    data = decode(raw)
    if not data:
        return False
    if collect_values(data):
        return True
    return str(data.get("status") or "").strip().lower() in {"error", "failed", "failure"}

def request(method, url, headers=None, payload=None, ok_statuses=(200,), require_error_body=False):
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request_headers.setdefault("Accept", "application/json")
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            ok = int(resp.status) in ok_statuses and not has_auth_error(raw)
            if ok and require_error_body and not has_provider_error_body(raw):
                ok = False
            return ok
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        ok = int(exc.code) in ok_statuses and not has_auth_error(raw)
        if ok and require_error_body and not has_provider_error_body(raw):
            ok = False
        return ok
    except Exception:
        return False

if provider in {"glm", "zai"}:
    ok = request("POST", "https://api.z.ai/api/paas/v4/images/generations", {"Authorization": "Bearer " + api_key}, {}, (400, 422), True)
elif provider in {"zhipu", "zhipuai", "bigmodel"}:
    ok = request("POST", "https://open.bigmodel.cn/api/paas/v4/images/generations", {"Authorization": "Bearer " + api_key}, {}, (400, 422), True)
elif provider in {"qwen_image", "qwen-image", "dashscope", "aliyun"}:
    ok = request("POST", "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation", {"Authorization": "Bearer " + api_key}, {}, (400, 422), True)
elif provider in {"stability", "stability_ai", "stable_image"}:
    ok = request("GET", "https://api.stability.ai/v1/user/balance", {"Authorization": "Bearer " + api_key}, None, (200,))
elif provider in {"fal", "fal_ai", "fal.ai"}:
    params = urllib.parse.urlencode({"endpoint_id": "fal-ai/flux/schnell", "limit": "1"})
    ok = request("GET", "https://api.fal.ai/v1/models?" + params, {"Authorization": "Key " + api_key}, None, (200,))
else:
    ok = False
print("ok" if ok else "bad")
PYCODEEPSEEDEX_INSTALL_IMAGE_VALIDATION_P28A3
)"
  [ "$result" = "ok" ]
}


model_api_base_url() {
  local provider="$1"
  case "$provider" in
    deepseek) printf '%s\n' "https://api.deepseek.com" ;;
    kimi|moonshot) printf '%s\n' "https://api.moonshot.ai/v1" ;;
    glm|zai|zhipu|zhipuai|bigmodel) printf '%s\n' "https://api.z.ai/api/paas/v4" ;;
    qwen|dashscope|aliyun) printf '%s\n' "https://dashscope-intl.aliyuncs.com/compatible-mode/v1" ;;
    *) printf '%s\n' "" ;;
  esac
}

model_api_default_model() {
  local provider="$1"
  case "$provider" in
    deepseek) printf '%s\n' "deepseek-v4-pro" ;;
    kimi|moonshot) printf '%s\n' "kimi-latest" ;;
    glm|zai|zhipu|zhipuai|bigmodel) printf '%s\n' "glm-5.1" ;;
    qwen|dashscope|aliyun) printf '%s\n' "qwen-plus" ;;
    *) printf '%s\n' "" ;;
  esac
}

test_model_api_key() {
  local provider="$1"
  local api_key="$2"
  local base_url="$3"
  if [ -z "$api_key" ]; then
    return 1
  fi
  if [ "$provider" = "deepseek" ]; then
    test_deepseek_api_key "$api_key"
    return $?
  fi
  if [ -z "$base_url" ]; then
    return 1
  fi
  local result
  result="$($PYTHON_BIN - "$api_key" "$base_url" <<'PYCODEEPSEEDEX_INSTALL_MODEL_API_VALIDATION_P28A4'
import sys
import urllib.request

api_key = sys.argv[1]
base_url = sys.argv[2].rstrip("/")
request = urllib.request.Request(
    base_url + "/models",
    headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
    method="GET",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
        print("ok" if 200 <= int(response.status) < 300 else "bad")
except Exception:
    print("bad")
PYCODEEPSEEDEX_INSTALL_MODEL_API_VALIDATION_P28A4
)"
  [ "$result" = "ok" ]
}

provider_option_line() {
  local number="$1"
  local name="$2"
  local status="$3"
  if [ "$status" = "supported" ]; then
    printf '  \033[1;32m%s\033[0m %s  \033[1;32mSupported\033[0m\n' "$number." "$name"
  else
    printf '  \033[2m%s %s  Unsupported\033[0m\n' "$number." "$name"
  fi
}



prompt_deepseek_api_key() {
  PROMPTED_API_KEY=""
  PROMPTED_MODEL_PROVIDER=""
  PROMPTED_MODEL_BASE_URL=""
  PROMPTED_MODEL_NAME=""

  if [ "$NON_INTERACTIVE" = "1" ]; then
    PROMPTED_API_KEY="${DEEPSEEK_API_KEY:-}"
    PROMPTED_MODEL_PROVIDER="${DEEPSEEK_PROXY_MODEL_PROVIDER:-deepseek}"
    PROMPTED_MODEL_BASE_URL="${DEEPSEEK_BASE_URL:-$(model_api_base_url "$PROMPTED_MODEL_PROVIDER")}"
    PROMPTED_MODEL_NAME="${DEEPSEEK_PROXY_MODEL:-$(model_api_default_model "$PROMPTED_MODEL_PROVIDER")}"
    return 0
  fi

  local configure=""
  configure="$(read_yes_no "Configure model API now? [Y/n]" "Y")"
  case "$configure" in
    n|N|no|NO|No)
      warn "Model API skipped. Configure later with: dsproxy config wizard"
      return 0
      ;;
  esac

  sub_title "Model providers"
  provider_option_line "1" "DeepSeek" "supported"
  provider_option_line "2" "Kimi / Moonshot" "supported"
  provider_option_line "3" "GLM / Z.AI" "supported"
  provider_option_line "4" "Qwen / DashScope" "supported"
  provider_option_line "5" "Mimo" "custom endpoint required"
  provider_option_line "6" "Baichuan" "custom endpoint required"
  provider_option_line "7" "Other OpenAI-compatible server" "custom"
  printf '%s
' "  0. Skip"

  local provider=""
  provider="$(read_from_tty "Select model provider" "1")"
  case "$provider" in
    1|deepseek|DeepSeek|DEEPSEEK)
      PROMPTED_MODEL_PROVIDER="deepseek"
      ;;
    2|kimi|moonshot|Kimi|Moonshot|KIMI|MOONSHOT)
      PROMPTED_MODEL_PROVIDER="kimi"
      ;;
    3|glm|zai|z.ai|zhipu|GLM|ZAI|Z.AI|ZHIPU)
      PROMPTED_MODEL_PROVIDER="glm"
      ;;
    4|qwen|dashscope|aliyun|Qwen|QWEN|DASHSCOPE|ALIYUN)
      PROMPTED_MODEL_PROVIDER="qwen"
      ;;
    5|mimo|Mimo|MIMO|6|baichuan|Baichuan|BAICHUAN|7|custom|other|Other|CUSTOM)
      PROMPTED_MODEL_PROVIDER="custom"
      ;;
    0|skip|Skip|SKIP)
      warn "Model API skipped. Configure later with: dsproxy config set-api-key --provider deepseek|kimi|glm|qwen|custom"
      return 0
      ;;
    *)
      warn "Selected model provider is currently unsupported. Configure as custom only if it is OpenAI-compatible."
      PROMPTED_MODEL_PROVIDER="custom"
      ;;
  esac

  PROMPTED_MODEL_BASE_URL="$(model_api_base_url "$PROMPTED_MODEL_PROVIDER")"
  PROMPTED_MODEL_NAME="$(model_api_default_model "$PROMPTED_MODEL_PROVIDER")"
  if [ "$PROMPTED_MODEL_PROVIDER" = "custom" ]; then
    PROMPTED_MODEL_BASE_URL="$(read_from_tty "OpenAI-compatible base URL" "${DEEPSEEK_BASE_URL:-}")"
    PROMPTED_MODEL_NAME="$(read_from_tty "Upstream model name" "${DEEPSEEK_PROXY_MODEL:-}")"
    if [ -z "$PROMPTED_MODEL_BASE_URL" ] || [ -z "$PROMPTED_MODEL_NAME" ]; then
      warn "Custom model API skipped because base URL or model name is empty."
      PROMPTED_API_KEY=""
      PROMPTED_MODEL_PROVIDER=""
      return 0
    fi
  fi

  local attempts=0
  local candidate=""
  while [ "$attempts" -lt 3 ]; do
    candidate="$(read_secret_from_tty "Model API key (optional; press Enter to skip)" "${DEEPSEEK_API_KEY:-}")"
    if [ -z "$candidate" ]; then
      PROMPTED_API_KEY=""
      warn "Model API key skipped. Configure later with: dsproxy config set-api-key --provider $PROMPTED_MODEL_PROVIDER"
      return 0
    fi

    if test_model_api_key "$PROMPTED_MODEL_PROVIDER" "$candidate" "$PROMPTED_MODEL_BASE_URL"; then
      PROMPTED_API_KEY="$candidate"
      ok "Model API key validated for provider: $PROMPTED_MODEL_PROVIDER"
      return 0
    fi

    warn "Model API key validation failed. Please paste it again, or press Enter to skip."
    attempts=$((attempts + 1))
  done

  PROMPTED_API_KEY=""
  if [ "$PROMPTED_MODEL_PROVIDER" = "deepseek" ]; then
    warn "DeepSeek API key was not saved because validation failed. Configure later with: dsproxy config set-api-key"
  else
    warn "Model API key was not saved because validation failed. Configure later with: dsproxy config set-api-key --provider $PROMPTED_MODEL_PROVIDER"
  fi
}


prompt_serpapi_api_key() {
  PROMPTED_SERPAPI_API_KEY=""
  PROMPTED_WEB_SEARCH_PROVIDER=""

  if [ "$NON_INTERACTIVE" = "1" ]; then
    PROMPTED_SERPAPI_API_KEY="${SERPAPI_API_KEY:-${TAVILY_API_KEY:-${BRAVE_SEARCH_API_KEY:-${EXA_API_KEY:-${FIRECRAWL_API_KEY:-}}}}}"
    PROMPTED_WEB_SEARCH_PROVIDER="${DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER:-serpapi}"
    return 0
  fi

  local configure=""
  configure="$(read_yes_no "Configure web search API now? [y/N]" "N")"
  case "$configure" in
    y|Y|yes|YES|Yes) ;;
    *)
      warn "Web search API skipped. Configure later with: dsproxy config set-web-search-api-key --provider serpapi|tavily|exa|firecrawl"
      return 0
      ;;
  esac

  sub_title "Web search providers"
  provider_option_line "1" "SerpAPI" "supported"
  provider_option_line "2" "Tavily" "supported"
  provider_option_line "3" "Exa" "supported"
  provider_option_line "4" "Firecrawl" "supported"
  provider_option_line "5" "Bing Web Search" "unsupported"
  provider_option_line "7" "Google Programmable Search" "unsupported"
  provider_option_line "8" "Other custom server" "unsupported"
  printf '%s\n' "  0. Skip"

  local provider=""
  local prompt=""
  provider="$(read_from_tty "Select web search provider" "1")"
  case "$provider" in
    1|serpapi|SerpAPI|SERPAPI) PROMPTED_WEB_SEARCH_PROVIDER="serpapi"; prompt="SerpAPI API key" ;;
    2|tavily|Tavily|TAVILY) PROMPTED_WEB_SEARCH_PROVIDER="tavily"; prompt="Tavily API key" ;;
    4|exa|Exa|EXA) PROMPTED_WEB_SEARCH_PROVIDER="exa"; prompt="Exa API key" ;;
    5|firecrawl|Firecrawl|FIRECRAWL) PROMPTED_WEB_SEARCH_PROVIDER="firecrawl"; prompt="Firecrawl API key" ;;
    8|other|Other|OTHER|custom|Custom)
      warn "Custom web search servers are configured manually. Ask your agent to read docs/custom_api_handoff.md for handoff instructions."
      return 0
      ;;
    0|skip|Skip|SKIP)
      warn "Web search API skipped. Configure later with: dsproxy config set-web-search-api-key --provider serpapi|tavily|exa|firecrawl"
      return 0
      ;;
    *)
      warn "Selected web search provider is currently unsupported."
      return 0
      ;;
  esac

  local attempts=0
  local candidate=""
  while [ "$attempts" -lt 3 ]; do
    candidate="$(read_secret_from_tty "$prompt (optional; press Enter to skip)" "")"
    if [ -z "$candidate" ]; then
      PROMPTED_SERPAPI_API_KEY=""
      warn "Web search API skipped. Configure later with: dsproxy config set-web-search-api-key --provider $PROMPTED_WEB_SEARCH_PROVIDER"
      return 0
    fi

    if test_web_search_api_key "$PROMPTED_WEB_SEARCH_PROVIDER" "$candidate"; then
      PROMPTED_SERPAPI_API_KEY="$candidate"
      ok "Web search API key validated for provider: $PROMPTED_WEB_SEARCH_PROVIDER"
      return 0
    fi

    warn "Web search API key validation failed. Please paste it again, or press Enter to skip."
    attempts=$((attempts + 1))
  done

  PROMPTED_SERPAPI_API_KEY=""
  warn "Web search API key was not saved because validation failed. Configure later with: dsproxy config set-web-search-api-key --provider $PROMPTED_WEB_SEARCH_PROVIDER"
}


prompt_image_generation_api_key() {
  PROMPTED_IMAGE_API_KEY=""
  PROMPTED_IMAGE_PROVIDER=""

  if [ "$NON_INTERACTIVE" = "1" ]; then
    PROMPTED_IMAGE_API_KEY="${DEEPSEEK_PROXY_IMAGE_API_KEY:-${DASHSCOPE_API_KEY:-${STABILITY_API_KEY:-${FAL_KEY:-}}}}"
    PROMPTED_IMAGE_PROVIDER="${DEEPSEEK_PROXY_IMAGE_PROVIDER:-zhipu}"
    return 0
  fi

  local configure=""
  configure="$(read_yes_no "Configure image generation API now? [y/N]" "N")"
  case "$configure" in
    y|Y|yes|YES|Yes) ;;
    *)
      warn "Image generation API skipped. Configure later with: dsproxy config set-image-api-key --provider zhipu|zai|qwen_image|stability|fal"
      return 0
      ;;
  esac

  sub_title "Image generation providers"
  provider_option_line "1" "ZhipuAI / BigModel" "supported"
  provider_option_line "2" "Qwen Image / DashScope" "supported"
  provider_option_line "3" "Stability AI" "supported"
  provider_option_line "4" "fal.ai" "supported"
  provider_option_line "5" "Kolors" "unsupported"
  provider_option_line "6" "Hunyuan Image" "unsupported"
  provider_option_line "7" "Volcengine Ark" "unsupported"
  provider_option_line "8" "Other custom server" "unsupported"
  printf '%s\n' "  0. Skip"

  local provider=""
  local prompt=""
  provider="$(read_from_tty "Select image generation provider" "1")"
  case "$provider" in
    1|glm|GLM|cogview|CogView|zai|ZAI) PROMPTED_IMAGE_PROVIDER="glm"; prompt="ZhipuAI / BigModel image API key" ;;
    2|qwen|Qwen|qwen_image|qwen-image|dashscope|DashScope|aliyun) PROMPTED_IMAGE_PROVIDER="qwen_image"; prompt="DashScope API key" ;;
    3|stability|Stability|stability_ai|stable_image) PROMPTED_IMAGE_PROVIDER="stability"; prompt="Stability AI API key" ;;
    4|fal|Fal|FAL|fal_ai|fal.ai) PROMPTED_IMAGE_PROVIDER="fal"; prompt="fal.ai API key" ;;
    8|other|Other|OTHER|custom|Custom)
      warn "Custom image generation servers are configured manually. Ask your agent to read docs/custom_api_handoff.md for handoff instructions."
      return 0
      ;;
    0|skip|Skip|SKIP)
      warn "Image generation API skipped. Configure later with: dsproxy config set-image-api-key --provider zhipu|zai|qwen_image|stability|fal"
      return 0
      ;;
    *)
      warn "Selected image generation provider is currently unsupported."
      return 0
      ;;
  esac

  local attempts=0
  local candidate=""
  while [ "$attempts" -lt 3 ]; do
    candidate="$(read_secret_from_tty "$prompt (optional; press Enter to skip)" "${DEEPSEEK_PROXY_IMAGE_API_KEY:-}")"
    if [ -z "$candidate" ]; then
      PROMPTED_IMAGE_API_KEY=""
      warn "Image generation API skipped. Configure later with: dsproxy config set-image-api-key --provider $PROMPTED_IMAGE_PROVIDER"
      return 0
    fi

    if test_image_generation_api_key "$PROMPTED_IMAGE_PROVIDER" "$candidate"; then
      PROMPTED_IMAGE_API_KEY="$candidate"
      ok "Image generation API key accepted by non-generating validation for provider: $PROMPTED_IMAGE_PROVIDER"
      warn "This does not prove real image generation works. Run a live provider probe before relying on it."
      return 0
    fi

    warn "Image generation API key validation failed. Please paste it again, or press Enter to skip."
    attempts=$((attempts + 1))
  done

  PROMPTED_IMAGE_API_KEY=""
  warn "Image generation API key was not saved because validation failed. Configure later with: dsproxy config set-image-api-key --provider $PROMPTED_IMAGE_PROVIDER"
}

backup_local_file_before_overwrite() {
  local path="$1"
  local label="$2"

  if [ "$DRY_RUN" = "1" ]; then
    if [ -e "$path" ]; then
      printf '+ backup existing %q before overwriting %s\n' "$path" "$label" >> "$INSTALL_LOG"
    fi
    return 0
  fi

  if [ ! -e "$path" ]; then
    return 0
  fi

  mkdir -p "$LOCAL_BACKUP_DIR"
  local safe_name
  safe_name="$(printf '%s' "$path" | sed 's#[/:]#_#g')"
  local backup_path="$LOCAL_BACKUP_DIR/${safe_name}.$(date +%Y%m%d_%H%M%S)"
  cp -p "$path" "$backup_path"
  printf '+ backup existing %q to %q before overwriting %s\n' "$path" "$backup_path" "$label" >> "$INSTALL_LOG"
  warn "Backed up existing $label to: $backup_path"
}


is_codeepseedex_managed_local_bin() {
  local path="$1"
  local kind="$2"

  if [ ! -e "$path" ]; then
    return 0
  fi
  if [ ! -f "$path" ]; then
    return 1
  fi

  case "$kind" in
    codex)
      grep -qE 'CoDeepSeedeX codex wrapper|CODEEPSEEDEX_DSPROXY|deepseek-responses-proxy|start_dsproxy_profile' "$path" 2>/dev/null
      ;;
    dsproxy)
      grep -qE 'CoDeepSeedeX|deepseek-responses-proxy|\.venv/bin/dsproxy' "$path" 2>/dev/null
      ;;
    *)
      return 1
      ;;
  esac
}

require_safe_local_bin_overwrite() {
  local path="$1"
  local label="$2"
  local kind="$3"
  local force_value="$4"

  if [ "$DRY_RUN" = "1" ]; then
    if [ -e "$path" ] && ! is_codeepseedex_managed_local_bin "$path" "$kind"; then
      printf '+ would require confirmation before overwriting unknown %q for %s\n' "$path" "$label" >> "$INSTALL_LOG"
    fi
    return 0
  fi

  if [ ! -e "$path" ]; then
    return 0
  fi

  if is_codeepseedex_managed_local_bin "$path" "$kind"; then
    backup_local_file_before_overwrite "$path" "$label"
    return 0
  fi

  backup_local_file_before_overwrite "$path" "$label"

  if [ "$force_value" = "1" ]; then
    warn "Forcing overwrite of unknown existing $label after backup: $path"
    return 0
  fi

  if [ "$NON_INTERACTIVE" = "1" ]; then
    warn "Refusing to overwrite unknown existing $label in non-interactive mode: $path"
    warn "The existing file was backed up under: $LOCAL_BACKUP_DIR"
    warn "Re-run with the explicit force variable only if this file should be replaced."
    case "$kind" in
      codex) warn "To force this replacement: DEEPSEEK_PROXY_FORCE_CODEX_WRAPPER=1" ;;
      dsproxy) warn "To force this replacement: DEEPSEEK_PROXY_FORCE_DSPROXY_WRAPPER=1" ;;
    esac
    return 1
  fi

  printf 'Existing %s at %s is not recognized as CoDeepSeedeX-managed. Overwrite after backup? [y/N] ' "$label" "$path" >&2
  local answer
  read -r answer
  case "$answer" in
    y|Y|yes|YES)
      warn "Overwriting unknown existing $label after user confirmation: $path"
      return 0
      ;;
    *)
      warn "Keeping unknown existing $label unchanged: $path"
      return 1
      ;;
  esac
}


env_file_value() {
  local key="$1"

  if [ ! -f "$ENV_FILE" ]; then
    printf '%s
' ""
    return 0
  fi

  "$PYTHON_BIN" - "$ENV_FILE" "$key" <<'PYENV'
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
target = sys.argv[2]
try:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
except FileNotFoundError:
    print("")
    raise SystemExit(0)

for line in lines:
    line = line.strip()
    if not line or line.startswith("#") or not line.startswith("export "):
        continue
    body = line[len("export "):]
    if "=" not in body:
        continue
    key, value = body.split("=", 1)
    if key.strip() != target:
        continue
    try:
        parts = shlex.split("x=" + value)
        if parts and parts[0].startswith("x="):
            print(parts[0][2:])
        else:
            print(value.strip("'\""))
    except Exception:
        print(value.strip("'\""))
    break
else:
    print("")
PYENV
}

choose_shell_profile_file() {
  if [ -n "${DEEPSEEK_PROXY_SHELL_PROFILE:-}" ]; then
    printf '%s\n' "$DEEPSEEK_PROXY_SHELL_PROFILE"
    return 0
  fi

  case "$(basename "${SHELL:-}")" in
    zsh) printf '%s\n' "$HOME/.zshrc" ;;
    bash) printf '%s\n' "$HOME/.bashrc" ;;
    *) printf '%s\n' "$HOME/.profile" ;;
  esac
}

ensure_shell_profile_integration() {
  if [ "$INSTALL_SHELL_PROFILE" != "1" ]; then
    ok "Shell profile update skipped"
    return 0
  fi

  local profile_file
  profile_file="$(choose_shell_profile_file)"
  SHELL_PROFILE_FILE="$profile_file"

  mkdir -p "$(dirname "$profile_file")"
  touch "$profile_file"

  if grep -q "CoDeepSeedeX environment" "$profile_file" 2>/dev/null; then
    ok "Shell profile already contains CoDeepSeedeX environment"
    return 0
  fi

  cat >> "$profile_file" <<EOF

# CoDeepSeedeX environment
if [ -d "$BIN_DIR" ]; then
  case ":\$PATH:" in
    *:"$BIN_DIR":*) ;;
    *) export PATH="$BIN_DIR:\$PATH" ;;
  esac
fi
if [ -f "$ENV_FILE" ]; then
  . "$ENV_FILE"
fi
EOF

  ok "Shell profile updated: $profile_file"
}

model_catalog_json_value() {
  local catalog_path="$INSTALL_DIR/experiments/model-catalog/deepseek-proxy-models.json"
  if [ ! -f "$catalog_path" ]; then
    printf '%s\n' ""
    return 0
  fi
  json_string "$catalog_path"
}

write_env_file() {
  local stable_port="$1"
  local thinking_port="$2"
  local api_key="$3"
  local web_search_key="$4"
  local image_api_key="$5"

  local final_api_key="$api_key"
  local final_web_search_key="$web_search_key"
  local final_image_api_key="$image_api_key"
  local final_web_search_provider="${PROMPTED_WEB_SEARCH_PROVIDER:-}"
  local final_image_provider="${PROMPTED_IMAGE_PROVIDER:-}"
  local final_model_provider="${PROMPTED_MODEL_PROVIDER:-}"
  local final_model_base_url="${PROMPTED_MODEL_BASE_URL:-}"
  local final_model_name="${PROMPTED_MODEL_NAME:-}"

  if [ -z "$final_api_key" ]; then
    final_api_key="$(env_file_value DEEPSEEK_API_KEY)"
  fi
  if [ -z "$final_model_provider" ]; then
    final_model_provider="$(env_file_value DEEPSEEK_PROXY_MODEL_PROVIDER)"
  fi
  if [ -z "$final_model_provider" ]; then
    final_model_provider="deepseek"
  fi
  if [ -z "$final_model_base_url" ]; then
    final_model_base_url="$(env_file_value DEEPSEEK_BASE_URL)"
  fi
  if [ -z "$final_model_base_url" ]; then
    final_model_base_url="$(model_api_base_url "$final_model_provider")"
  fi
  if [ -z "$final_model_name" ]; then
    final_model_name="$(env_file_value DEEPSEEK_PROXY_MODEL)"
  fi
  if [ -z "$final_model_name" ]; then
    final_model_name="$(model_api_default_model "$final_model_provider")"
  fi
  if [ -z "$final_model_base_url" ]; then
    final_model_base_url="https://api.deepseek.com"
  fi
  if [ -z "$final_model_name" ]; then
    final_model_name="deepseek-v4-pro"
  fi
  if [ -z "$final_web_search_provider" ]; then
    final_web_search_provider="$(env_file_value DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER)"
  fi
  if [ -z "$final_web_search_provider" ]; then
    final_web_search_provider="serpapi"
  fi
  if [ -z "$final_web_search_key" ]; then
    case "$final_web_search_provider" in
      tavily) final_web_search_key="$(env_file_value TAVILY_API_KEY)" ;;
      *) final_web_search_key="$(env_file_value SERPAPI_API_KEY)" ;;
    esac
  fi
  if [ -z "$final_image_provider" ]; then
    final_image_provider="$(env_file_value DEEPSEEK_PROXY_IMAGE_PROVIDER)"
  fi
  if [ -z "$final_image_provider" ]; then
    final_image_provider="zhipu"
  fi
  if [ -z "$final_image_api_key" ]; then
    final_image_api_key="$(env_file_value DEEPSEEK_PROXY_IMAGE_API_KEY)"
  fi

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ mkdir -p %q
' "$(dirname "$ENV_FILE")" >> "$INSTALL_LOG"
    printf '+ write %q with chmod 600
' "$ENV_FILE" >> "$INSTALL_LOG"
    ok "Local env file written"
    return 0
  fi

  mkdir -p "$(dirname "$ENV_FILE")"
  backup_local_file_before_overwrite "$ENV_FILE" "local env file"

  {
    printf '# deepseek-responses-proxy local environment
'
    printf '# Generated by scripts/install.sh
'
    printf 'export DEEPSEEK_API_KEY=%q
' "$final_api_key"
    printf 'export DEEPSEEK_BASE_URL=%q
' "$final_model_base_url"
    printf 'export DEEPSEEK_PROXY_MODEL_PROVIDER=%q
' "$final_model_provider"
    printf 'export DEEPSEEK_PROXY_PORT=%q
' "$stable_port"
    printf 'export DEEPSEEK_PROXY_THINKING_PORT=%q
' "$thinking_port"
    printf 'export DEEPSEEK_PROXY_MODEL=%q
' "$final_model_name"
    printf 'export DEEPSEEK_REASONING_EFFORT=%q
' "xhigh"
    printf 'export DEEPSEEK_PROXY_FORCE_MODEL=%q
' "1"
    printf 'export DEEPSEEK_PROXY_TOOL_MAX_ROUNDS=%q
' "6"
    printf 'export DEEPSEEK_PROXY_COMPACT_POLICY=%q
' "adaptive"
    printf 'export DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD=%q
' "1"
    printf 'export DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED=%q
' "1"
    printf 'export DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL=%q
' "v4-flash-no-thinking"
    printf 'export DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION=%q
' "1"
    if [ -n "$final_web_search_key" ]; then
      printf 'export DEEPSEEK_PROXY_TOOL_BRIDGE=%q
' "1"
      printf 'export DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER=%q
' "$final_web_search_provider"
      printf 'export DEEPSEEK_PROXY_WEB_SEARCH_MAX_RESULTS=%q
' "6"
      printf 'export DEEPSEEK_PROXY_WEB_SEARCH_TIMEOUT_SECONDS=%q
' "12.5"
      case "$final_web_search_provider" in
        tavily)
          printf 'export TAVILY_API_KEY=%q
' "$final_web_search_key"
          ;;
        exa)
          printf 'export EXA_API_KEY=%q
' "$final_web_search_key"
          ;;
        firecrawl)
          printf 'export FIRECRAWL_API_KEY=%q
' "$final_web_search_key"
          ;;
        *)
          printf 'export SERPAPI_API_KEY=%q
' "$final_web_search_key"
          ;;
      esac
    fi
    if [ -n "$final_image_api_key" ]; then
      printf 'export DEEPSEEK_PROXY_TOOL_BRIDGE=%q
' "1"
      printf 'export DEEPSEEK_PROXY_IMAGE_PROVIDER=%q
' "$final_image_provider"
      if [ "$final_image_provider" = "qwen_image" ]; then
        printf 'export DEEPSEEK_PROXY_IMAGE_MODEL=%q
' "qwen-image-2.0-pro"
      elif [ "$final_image_provider" = "stability" ]; then
        printf 'export DEEPSEEK_PROXY_IMAGE_MODEL=%q
' "stable-image-core"
      elif [ "$final_image_provider" = "fal" ]; then
        printf 'export DEEPSEEK_PROXY_IMAGE_MODEL=%q
' "fal-ai/flux/schnell"
      else
        printf 'export DEEPSEEK_PROXY_IMAGE_MODEL=%q
' "cogView-4-250304"
      fi
      printf 'export DEEPSEEK_PROXY_IMAGE_SIZE=%q
' "1024x1024"
      printf 'export DEEPSEEK_PROXY_IMAGE_N=%q
' "1"
      printf 'export DEEPSEEK_PROXY_IMAGE_DOWNLOAD=%q
' "1"
      printf 'export DEEPSEEK_PROXY_IMAGE_API_KEY=%q
' "$final_image_api_key"
    fi
  } > "$ENV_FILE"

  chmod 600 "$ENV_FILE"
  ok "Local env file written"
}

write_dsproxy_wrapper() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '+ mkdir -p %q\n' "$BIN_DIR" >> "$INSTALL_LOG"
    printf '+ write %q\n' "$BIN_DIR/dsproxy" >> "$INSTALL_LOG"
    ok "dsproxy command installed"
    return 0
  fi

  mkdir -p "$BIN_DIR"
  require_safe_local_bin_overwrite "$BIN_DIR/dsproxy" "dsproxy command wrapper" "dsproxy" "$FORCE_DSPROXY_WRAPPER" || return 1

  cat > "$BIN_DIR/dsproxy" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="\${DEEPSEEK_PROXY_ENV_FILE:-$ENV_FILE}"
if [ -f "\$ENV_FILE" ]; then
  source "\$ENV_FILE"
fi
exec "$INSTALL_DIR/.venv/bin/dsproxy" "\$@"
EOF

  chmod +x "$BIN_DIR/dsproxy"
  ok "dsproxy command installed"
}

write_codex_wrapper() {
  local stable_port="$1"
  local thinking_port="$2"
  local wrapper_path="$BIN_DIR/codex"
  local real_codex=""
  local backup_path=""

  if [ "$INSTALL_CODEX_WRAPPER" != "1" ]; then
    ok "Codex wrapper skipped"
    return 0
  fi

  real_codex="$(find_real_codex "$wrapper_path" || true)"
  local existing_wrapper_is_unknown="0"

  if [ -e "$wrapper_path" ] && ! is_codeepseedex_managed_local_bin "$wrapper_path" "codex"; then
    existing_wrapper_is_unknown="1"
  fi

  if [ "$DRY_RUN" = "1" ]; then
    require_safe_local_bin_overwrite "$wrapper_path" "codex command wrapper" "codex" "$FORCE_CODEX_WRAPPER"
    printf '+ write %q\n' "$wrapper_path" >> "$INSTALL_LOG"
    ok "Codex wrapper installed"
    return 0
  fi

  mkdir -p "$BIN_DIR"
  require_safe_local_bin_overwrite "$wrapper_path" "codex command wrapper" "codex" "$FORCE_CODEX_WRAPPER" || return 1

  if [ "$existing_wrapper_is_unknown" = "1" ]; then
    backup_path="$wrapper_path.codeepseedex.bak.$(date +%Y%m%d_%H%M%S)"
    mv "$wrapper_path" "$backup_path"
    if [ -z "$real_codex" ]; then
      real_codex="$backup_path"
    fi
  fi

  if [ -z "$real_codex" ]; then
    warn "real codex command not found; Codex wrapper skipped"
    return 0
  fi

  cat > "$wrapper_path" <<EOF
#!/usr/bin/env bash
# CoDeepSeedeX codex wrapper
set -euo pipefail

REAL_CODEX="$real_codex"
DSPROXY="\${CODEEPSEEDEX_DSPROXY:-$BIN_DIR/dsproxy}"
if [ ! -x "\$DSPROXY" ] && [ -x "$INSTALL_DIR/.venv/bin/dsproxy" ]; then
  DSPROXY="$INSTALL_DIR/.venv/bin/dsproxy"
fi
ENV_FILE="\${DEEPSEEK_PROXY_ENV_FILE:-$ENV_FILE}"

if [ -f "\$ENV_FILE" ]; then
  source "\$ENV_FILE"
fi

profile=""
prev=""
for arg in "\$@"; do
  if [ "\$prev" = "--profile" ] || [ "\$prev" = "-p" ]; then
    profile="\$arg"
    break
  fi
  case "\$arg" in
    --profile=*) profile="\${arg#--profile=}"; break ;;
    -p*) profile="\${arg#-p}"; break ;;
  esac
  prev="\$arg"
done

start_dsproxy_profile() {
  local profile_name="\$1"
  if [ ! -x "\$DSPROXY" ]; then
    return 0
  fi

  case "\$profile_name" in
    deepseek)
      "\$DSPROXY" start >/dev/null 2>&1 || "\$DSPROXY" status >/dev/null 2>&1 || true
      ;;
    deepseek-thinking)
      "\$DSPROXY" start thinking >/dev/null 2>&1 || "\$DSPROXY" status thinking >/dev/null 2>&1 || true
      ;;
  esac
}

case "\$profile" in
  deepseek|deepseek-thinking)
    start_dsproxy_profile "\$profile"
    ;;
esac

exec "\$REAL_CODEX" "\$@"
EOF

  chmod +x "$wrapper_path"

  cat > "$MANIFEST_FILE" <<EOF
CODEX_WRAPPER_PATH="$wrapper_path"
CODEX_WRAPPER_BACKUP="$backup_path"
REAL_CODEX="$real_codex"
ENV_FILE="$ENV_FILE"
INSTALL_DIR="$INSTALL_DIR"
BIN_DIR="$BIN_DIR"
STABLE_PORT="$stable_port"
THINKING_PORT="$thinking_port"
EOF

  chmod 600 "$MANIFEST_FILE" 2>/dev/null || true
  ok "Codex wrapper installed"
}

uninstall() {
  logo
  step "Uninstalling CoDeepSeedeX integration"

  local wrapper_path="$BIN_DIR/codex"
  local backup_path=""

  if [ -f "$MANIFEST_FILE" ]; then
    # shellcheck disable=SC1090
    source "$MANIFEST_FILE" || true
    wrapper_path="${CODEX_WRAPPER_PATH:-$wrapper_path}"
    backup_path="${CODEX_WRAPPER_BACKUP:-}"
  fi

  if [ -x "$INSTALL_DIR/.venv/bin/dsproxy" ]; then
    run_quiet "Codex profile removed: deepseek" "$INSTALL_DIR/.venv/bin/dsproxy" uninstall-codex-profile --name deepseek --no-backup || true
    run_quiet "Codex profile removed: deepseek-thinking" "$INSTALL_DIR/.venv/bin/dsproxy" uninstall-codex-profile --name deepseek-thinking --no-backup || true
  fi

  if [ -f "$wrapper_path" ] && grep -q "CoDeepSeedeX codex wrapper" "$wrapper_path" 2>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
      printf '+ remove %q\n' "$wrapper_path" >> "$INSTALL_LOG"
    else
      rm -f "$wrapper_path"
    fi
    ok "Codex wrapper removed"

    if [ -n "$backup_path" ] && [ -f "$backup_path" ]; then
      if [ "$DRY_RUN" = "1" ]; then
        printf '+ restore %q to %q\n' "$backup_path" "$wrapper_path" >> "$INSTALL_LOG"
      else
        mv "$backup_path" "$wrapper_path"
      fi
      ok "Previous codex command restored"
    fi
  fi

  if [ -f "$BIN_DIR/dsproxy" ] && grep -q "$INSTALL_DIR/.venv/bin/dsproxy" "$BIN_DIR/dsproxy" 2>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
      printf '+ remove %q\n' "$BIN_DIR/dsproxy" >> "$INSTALL_LOG"
    else
      rm -f "$BIN_DIR/dsproxy"
    fi
    ok "dsproxy wrapper removed"
  fi

  if [ "$REMOVE_FILES" = "1" ]; then
    if [ "$DRY_RUN" = "1" ]; then
      printf '+ remove install/env files\n' >> "$INSTALL_LOG"
    else
      rm -rf "$INSTALL_DIR"
      rm -f "$ENV_FILE"
      rm -f "$MANIFEST_FILE"
    fi
    ok "Install files removed"
  fi

  step "Done"
  sub_title "Install log"
  printf '  %s\n' "$INSTALL_LOG"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --non-interactive) NON_INTERACTIVE=1 ;;
    --install-dir) INSTALL_DIR="$2"; shift ;;
    --repo-url) REPO_URL="$2"; shift ;;
    --install-ref) INSTALL_REF="$2"; shift ;;
    --bin-dir) BIN_DIR="$2"; shift ;;
    --config-dir) CONFIG_DIR="$2"; ENV_FILE="$CONFIG_DIR/env"; MANIFEST_FILE="$CONFIG_DIR/install-manifest.env"; shift ;;
    --python-bin) PYTHON_BIN="$2"; shift ;;
    --env-file) ENV_FILE="$2"; shift ;;
    --no-codex-profile) INSTALL_CODEX_PROFILE=0 ;;
    --no-codex-wrapper) INSTALL_CODEX_WRAPPER=0 ;;
    --no-shell-profile) INSTALL_SHELL_PROFILE=0 ;;
    --uninstall) UNINSTALL=1 ;;
    --remove-files) REMOVE_FILES=1 ;;
    -h|--help|-H) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

: > "$INSTALL_LOG"

if [ "$UNINSTALL" = "1" ]; then
  uninstall
  exit 0
fi

logo

divider
section_title "Setup plan"
printf '%s\n' "  1. Check Python and Git"
printf '%s\n' "  2. Install or update repository"
printf '%s\n' "  3. Create virtual environment"
printf '%s\n' "  4. Install dsproxy"
printf '%s\n' "  5. Guided API configuration and local env file"
printf '%s\n' "  6. Install Codex profiles"
printf '%s\n' "  7. Install safe Codex wrapper, recommended"
sub_title "Install log"
printf '  %s\n' "$INSTALL_LOG"

step "Checking requirements"

PY_VERSION="$("$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("ERROR: Python >= 3.11 is required by the selected interpreter")
print(sys.version.split()[0])
PY
)"
ok "Python $PY_VERSION via $PYTHON_BIN"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required" >&2
  exit 1
fi
ok "Git available"

step "Guided configuration"

DEFAULT_STABLE_PORT="${DEEPSEEK_PROXY_PORT:-8000}"
DEFAULT_THINKING_PORT="${DEEPSEEK_PROXY_THINKING_PORT:-8001}"
STABLE_PORT="$(read_from_tty "Stable proxy port [press Enter to keep default]" "$DEFAULT_STABLE_PORT")"
THINKING_PORT="$(read_from_tty "Thinking proxy port [press Enter to keep default]" "$DEFAULT_THINKING_PORT")"
prompt_deepseek_api_key
API_KEY="$PROMPTED_API_KEY"
prompt_serpapi_api_key
SERPAPI_KEY="$PROMPTED_SERPAPI_API_KEY"
prompt_image_generation_api_key
IMAGE_API_KEY="$PROMPTED_IMAGE_API_KEY"
WRAPPER_CHOICE="$(read_yes_no "Install codex wrapper for deepseek/deepseek-thinking profiles? [Y/n] (Recommended):" "Y")"

case "$WRAPPER_CHOICE" in
  n|N|no|NO|No) INSTALL_CODEX_WRAPPER=0 ;;
  *) INSTALL_CODEX_WRAPPER=1 ;;
esac

if [ -z "$API_KEY" ]; then
  warn "DEEPSEEK_API_KEY is empty; configure later with: dsproxy config set-api-key"
fi

sync_install_checkout_to_ref() {
  local requested_ref="${1:-}"
  requested_ref="${requested_ref:-${DEEPSEEK_PROXY_INSTALL_REF:-}}"

  if [ -z "$requested_ref" ]; then
    return 0
  fi
  if [ ! -d "$INSTALL_DIR/.git" ]; then
    return 0
  fi

  printf '+ Synchronizing installed checkout to ref: %s\n' "$requested_ref" >> "$INSTALL_LOG"

  (
    cd "$INSTALL_DIR"

    git fetch --tags origin >> "$INSTALL_LOG" 2>&1 || return 1

    local untracked_count
    untracked_count="$(git ls-files --others --exclude-standard | wc -l | tr -d ' ')"

    if ! git diff --quiet || ! git diff --cached --quiet || [ "$untracked_count" != "0" ]; then
      mkdir -p "$LOCAL_BACKUP_DIR"
      local dirty_patch="$LOCAL_BACKUP_DIR/installed-checkout-dirty-$(date +%Y%m%d_%H%M%S).patch"
      git diff > "$dirty_patch" || true
      git diff --cached >> "$dirty_patch" || true
      warn "Backed up local installed checkout modifications to: $dirty_patch"

      if [ "$untracked_count" != "0" ]; then
        local untracked_list="$LOCAL_BACKUP_DIR/installed-checkout-untracked-$(date +%Y%m%d_%H%M%S).txt"
        local untracked_tar="$LOCAL_BACKUP_DIR/installed-checkout-untracked-$(date +%Y%m%d_%H%M%S).tar.gz"
        git ls-files --others --exclude-standard > "$untracked_list" || true
        tar -czf "$untracked_tar" -T "$untracked_list" >> "$INSTALL_LOG" 2>&1 || true
        warn "Backed up local installed checkout untracked files to: $untracked_tar"
      fi

      if [ "${NON_INTERACTIVE:-0}" != "1" ] && [ -t 0 ]; then
        printf 'Installed checkout has local modifications. Overwrite after backup? [y/N] ' >&2
        local answer
        read -r answer
        case "$answer" in
          y|Y|yes|YES)
            ;;
          *)
            warn "Keeping local installed checkout modifications. Installation cannot refresh package code."
            return 1
            ;;
        esac
      fi

      git reset --hard >> "$INSTALL_LOG" 2>&1 || return 1
      git clean -fd >> "$INSTALL_LOG" 2>&1 || return 1
    fi

    if git show-ref --verify --quiet "refs/remotes/origin/$requested_ref"; then
      git checkout -B "$requested_ref" "origin/$requested_ref" >> "$INSTALL_LOG" 2>&1 || return 1
      return 0
    fi

    if git show-ref --verify --quiet "refs/tags/$requested_ref"; then
      git checkout -f "$requested_ref" >> "$INSTALL_LOG" 2>&1 || return 1
      return 0
    fi

    git checkout -f "$requested_ref" >> "$INSTALL_LOG" 2>&1 || return 1
  )

  ok "Repository target checked out"
}


step "Installing"

INSTALL_TARGET_REF="$(resolve_install_ref)"
ok "Install target ref: $INSTALL_TARGET_REF"

if [ -d "$INSTALL_DIR/.git" ]; then
  run_git_quiet "Repository tags fetched" "git fetch --tags origin" git -C "$INSTALL_DIR" fetch --tags origin
else
  run_quiet "Install parent directory ready" mkdir -p "$(dirname "$INSTALL_DIR")"
  run_git_quiet "Repository installed" "git clone" git clone "$REPO_URL" "$INSTALL_DIR"
  run_git_quiet "Repository tags fetched" "git fetch --tags origin" git -C "$INSTALL_DIR" fetch --tags origin
fi

sync_install_checkout_to_ref "$INSTALL_TARGET_REF"

run_quiet "Virtual environment ready" "$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"
run_quiet "pip upgraded" "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
run_quiet "Python package installed" "$INSTALL_DIR/.venv/bin/python" -m pip install -e "$INSTALL_DIR"

write_env_file "$STABLE_PORT" "$THINKING_PORT" "$API_KEY" "$SERPAPI_KEY" "$IMAGE_API_KEY"
write_dsproxy_wrapper
ensure_shell_profile_integration

run_quiet "dsproxy config initialized" "$INSTALL_DIR/.venv/bin/dsproxy" config init

MODEL_CATALOG_JSON="$(model_catalog_json_value)"
MODEL_CATALOG_ARGS=()
if [ -n "$MODEL_CATALOG_JSON" ]; then
  MODEL_CATALOG_ARGS=(--model-catalog-json "$MODEL_CATALOG_JSON")
fi

if [ "$INSTALL_CODEX_PROFILE" = "1" ]; then
  run_quiet "Codex profile installed: deepseek" "$INSTALL_DIR/.venv/bin/dsproxy" install-codex-profile \
    --name deepseek \
    --provider-name deepseek-proxy \
    --base-url "http://127.0.0.1:${STABLE_PORT}/v1" \
    --model deepseek-v4-flash \
    --reasoning-effort high \
    "${MODEL_CATALOG_ARGS[@]}"

  run_quiet "Codex profile installed: deepseek-thinking" "$INSTALL_DIR/.venv/bin/dsproxy" install-codex-profile \
    --name deepseek-thinking \
    --provider-name deepseek-thinking-proxy \
    --base-url "http://127.0.0.1:${THINKING_PORT}/v1" \
    --model deepseek-v4-pro \
    --reasoning-effort xhigh \
    "${MODEL_CATALOG_ARGS[@]}"
fi

write_codex_wrapper "$STABLE_PORT" "$THINKING_PORT"

step "Done"


# codeepseedex_repair_codex_model_catalog_json_v2746a1
if [ "$DRY_RUN" != "1" ]; then
  backup_local_file_before_overwrite "$HOME/.codex/config.toml" "Codex config"
  "$PYTHON_BIN" - "$HOME/.codex/config.toml" "$INSTALL_DIR/experiments/model-catalog/deepseek-proxy-models.json" <<'PYCODEXCAT'
from __future__ import annotations

import sys
from pathlib import Path

config = Path(sys.argv[1])
catalog = sys.argv[2]
if not config.exists():
    raise SystemExit(0)

lines = config.read_text(encoding="utf-8").splitlines()
targets = {"profiles.deepseek", "profiles.deepseek-thinking"}
out = []
current = None
pending_insert = None

def flush_pending() -> None:
    global pending_insert
    if pending_insert is not None:
        out.append(f'model_catalog_json = "{catalog}"')
        pending_insert = None

for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        flush_pending()
        current = stripped.strip("[]")
        out.append(line)
        pending_insert = "profile" if current in targets else None
        continue

    if current in targets and stripped.startswith("model_catalog_json"):
        if pending_insert is not None:
            out.append(f'model_catalog_json = "{catalog}"')
            pending_insert = None
        continue

    out.append(line)

    if current in targets and pending_insert is not None and stripped.startswith("model_provider"):
        out.append(f'model_catalog_json = "{catalog}"')
        pending_insert = None

flush_pending()
config.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PYCODEXCAT
  ok "Codex model catalog linked"
else
  ok "Codex model catalog linked"
fi

sub_title "Installation files"
printf '%s\n' "  env file: $ENV_FILE"
printf '%s\n' "  dsproxy: $BIN_DIR/dsproxy"
if [ -n "$SHELL_PROFILE_FILE" ]; then
  printf '%s\n' "  shell profile: $SHELL_PROFILE_FILE"
  printf '%s\n' "  current shell may need: source $SHELL_PROFILE_FILE"
  printf '  current shell immediate PATH: export PATH="%s:$PATH"\n' "$BIN_DIR"
  printf '  verify wrapper: command -v codex && command -v dsproxy\n'
fi

sub_title "Next steps"
printf '%s\n' "  codex --profile deepseek"
printf '%s\n' "  codex --profile deepseek-thinking  # recommended"

sub_title "Inside Codex TUI"
printf '%s\n' "  /status       show session/runtime status"
printf '%s\n' "  /model        switch model or reasoning effort"
printf '%s\n' "  /plan         plan before implementation"
printf '%s\n' "  check balance"

sub_title "Shell commands"
printf '%s\n' "  dsproxy start"
printf '%s\n' "  dsproxy start thinking"
printf '%s\n' "  dsproxy status"
printf '%s\n' "  dsproxy status thinking"
printf '%s\n' "  dsproxy stop"
printf '%s\n' "  dsproxy stop thinking"
printf '%s\n' "  dsproxy config test-api-key"
printf '%s\n' "  dsproxy balance"
printf '%s\n' "  dsproxy config show"
printf '%s\n' "  dsproxy config wizard"
printf '%s\n' "  dsproxy config set-api-key"
printf '%s\n' "  dsproxy config test-api-key"
printf '%s\n' "  dsproxy config set-web-search-api-key --provider serpapi|tavily|exa|firecrawl"
printf '%s\n' "  dsproxy config set-image-api-key --provider zhipu|zai|qwen_image|stability|fal"
printf '%s\n' "  dsproxy config set-model deepseek-v4-flash"
printf '%s\n' "  dsproxy config set-effort high"

sub_title "Continue a previous Codex conversation"
printf '%s\n' "  codex --profile deepseek-thinking resume"

sub_title "Uninstall integration"
printf '  bash %s --uninstall\n' "$INSTALL_DIR/scripts/install.sh"

sub_title "Install log"
printf '  %s\n' "$INSTALL_LOG"

divider
