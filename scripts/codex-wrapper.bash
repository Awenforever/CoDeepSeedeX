# Auto-start DeepSeek Responses Proxy when using CoDeepSeedeX Codex profiles.
#
# Add this function to ~/.bashrc after ~/bin is on PATH.
#
# Behavior:
# - codex --profile deepseek-thinking starts the thinking proxy on port 8001.
# - codex --profile <custom-provider-id> activates that configured provider and starts the thinking proxy.
# - codex --profile deepseek is deprecated and fails closed.
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
      printf 'CoDeepSeedeX error: profile "deepseek" is deprecated. Use: codex --profile deepseek-thinking\n' >&2
      return 2
      ;;
    deepseek-thinking)
      source "$HOME/.config/deepseek-responses-proxy/env"
      dsproxy start thinking
      DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" command codex "$@"
      ;;
    "")
      command codex "$@"
      ;;
    *)
      source "$HOME/.config/deepseek-responses-proxy/env"
      if dsproxy config custom-provider use --name "$selected_profile" --no-profile-sync >/dev/null 2>&1; then
        dsproxy start thinking
        DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" command codex "$@"
      else
        command codex "$@"
      fi
      ;;
  esac
}
