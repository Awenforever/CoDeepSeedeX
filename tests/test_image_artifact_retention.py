import json
from pathlib import Path

from deepseek_responses_proxy.app import _apply_tool_output_safe_trimming, _write_mock_image_artifact


def test_generated_image_artifact_retention_prunes_known_prefixes_only(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_MAX_ARTIFACTS", "2")

    manual_file = tmp_path / "manual-user-image.png"
    manual_file.write_bytes(b"do-not-delete")

    written = []
    for _ in range(5):
        file_path = _write_mock_image_artifact(provider="mock")
        assert file_path is not None
        written.append(Path(file_path))

    retained = sorted(tmp_path.glob("mock_*.png"))
    assert len(retained) == 2
    assert manual_file.exists()
    assert all(path.exists() for path in retained)
    assert any(not path.exists() for path in written)


def test_generated_image_artifact_retention_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_MAX_ARTIFACTS", "0")

    for _ in range(4):
        file_path = _write_mock_image_artifact(provider="mock")
        assert file_path is not None

    assert len(list(tmp_path.glob("mock_*.png"))) == 4



def test_tool_output_image_payload_is_preserved_verbatim_without_artifact_ref(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS", "2000")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_ARTIFACT_DIR", str(tmp_path / "tool-output-artifacts"))

    original_payload = [{"mime_type": "image/png", "b64_json": "A" * 5000}]
    input_items = [
        {"type": "function_call", "call_id": "call_image", "name": "view_image", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_image", "output": original_payload},
    ]

    compacted, report = _apply_tool_output_safe_trimming(input_items)

    assert compacted == input_items
    assert report["applied"] is False
    assert report["targets"] == []
    assert report["skipped_outputs"][0]["skip_reason"] == "image_payload_preserved_verbatim_no_trim_no_artifact_ref"
    assert report["skipped_outputs"][0]["image_payload_preserve_verbatim"] is True
    assert report["skipped_outputs"][0]["artifact_ref_written"] is False
    assert not list((tmp_path / "tool-output-artifacts").glob("*.json"))
