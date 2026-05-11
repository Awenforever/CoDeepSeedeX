# Auto-start DeepSeek Responses Proxy when using Codex profiles.
#
# Add this function to ~/.bashrc after ~/bin is on PATH.
#
# Behavior:
# - codex --profile deepseek starts stable proxy on port 8000.
# - codex --profile deepseek-thinking starts both stable and thinking proxies.
#   The stable proxy is started too because the account/usage skill queries both
#   profiles by default.
codex() {
  local selected_profile=""
  local arg
  local next_is_profile=0

  for arg in "$@"; do
    if [ "$next_is_profile" = "1" ]; then
      selected_profile="$arg"
      next_is_profile=0
      continue
    fi

    case "$arg" in
      --profile|-p)
        next_is_profile=1
        ;;
      --profile=*)
        selected_profile="${arg#--profile=}"
        ;;
    esac
  done

  export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
  export no_proxy="127.0.0.1,localhost,${no_proxy:-}"

  case "$selected_profile" in
    deepseek)
      source "$HOME/.config/deepseek-responses-proxy/env"
      dsproxy start
      DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" command codex "$@"
      ;;
    deepseek-thinking)
      source "$HOME/.config/deepseek-responses-proxy/env"
      dsproxy start
      dsproxy start thinking
      DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" command codex "$@"
      ;;
    *)
      command codex "$@"
      ;;
  esac
}
