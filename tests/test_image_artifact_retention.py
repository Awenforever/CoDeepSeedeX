from pathlib import Path

from deepseek_responses_proxy.app import _write_mock_image_artifact


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
