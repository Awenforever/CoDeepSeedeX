# Troubleshooting

## Port already in use

Symptom:

    address already in use

Check:

    ss -ltnp | grep -E ':8000|:8001'

Stop thinking proxy:

    dsproxy stop --thinking

If an old process remains, kill it manually and restart.

## CLI version and service version mismatch

Run:

    dsproxy doctor --thinking

Check:

    version_match

If it is false, an older proxy service is running on the port. Stop it and restart.

## Missing API key

Check:

    echo "$DEEPSEEK_API_KEY"

Set:

    export DEEPSEEK_API_KEY="..."

## Missing Codex profile

Reinstall:

    dsproxy install-codex-profile

Inspect Codex config:

    grep -nA20 'profiles.deepseek-thinking' ~/.codex/config.toml

## High context cost

Check usage:

    dsproxy usage --thinking --summary
    dsproxy usage --thinking --summary --purpose compaction
    dsproxy usage --thinking --summary --purpose tool_bridge

If tool_bridge is high, reduce max tool rounds.

If compaction is high, inspect:

    python3 -m json.tool .debug/context_compaction_report.json
