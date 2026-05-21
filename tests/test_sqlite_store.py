from deepseek_responses_proxy.app import SQLiteResponseStore


def test_sqlite_store_persists_response_state_across_instances(tmp_path):
    db_path = tmp_path / "responses.sqlite3"

    response = {
        "id": "resp_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": "deepseek-v4-flash",
        "previous_response_id": None,
        "output": [],
        "output_text": "",
        "usage": {},
    }
    chat_messages = [
        {"role": "user", "content": "call a tool"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "pwd", "arguments": "{}"},
                }
            ],
        },
    ]

    first = SQLiteResponseStore(db_path)
    first.save(response, chat_messages)

    second = SQLiteResponseStore(db_path)
    stored = second.get("resp_test")

    assert stored is not None
    assert stored.response == response
    assert stored.chat_messages == chat_messages


def test_sqlite_store_returns_none_for_missing_response(tmp_path):
    store = SQLiteResponseStore(tmp_path / "responses.sqlite3")
    assert store.get("missing") is None


def test_sqlite_store_persists_profile_tokenizer_report_across_instances(tmp_path):
    db_path = tmp_path / "responses.sqlite3"
    report = {
        "available": True,
        "profile": "deepseek-thinking",
        "session_id": "sess-1",
        "request_id": "resp-1",
        "response_id": "resp-1",
        "prompt_subcategory_split": {
            "available": True,
            "categories": {"user": {"tokens": 3}},
        },
    }

    first = SQLiteResponseStore(db_path)
    first.save_profile_tokenizer_report(report)

    second = SQLiteResponseStore(db_path)
    restored = second.profile_tokenizer_report("deepseek-thinking", session_id="sess-1")

    assert restored is not None
    assert restored["session_id"] == "sess-1"
    assert restored["request_id"] == "resp-1"
    assert restored["restored_from_persistence"] is True
    assert restored["source"] == "sqlite_profile_tokenizer_report_store"
    assert restored["prompt_subcategory_split"]["restored_from_persistence"] is True
