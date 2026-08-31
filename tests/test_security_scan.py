from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "security_scan", ROOT / "tools" / "security_scan.py"
)
security_scan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(security_scan)


def _rules(text: str) -> set[str]:
    return {item[2] for item in security_scan.scan_bytes("fixture", text.encode())}


def test_rejects_literal_credentials_and_private_translation_urls():
    credential_name = "api_" + "key"
    credential = credential_name + " = " + repr("live_" + "a" * 28)
    endpoint = 'morph_ai_api_url = "https://' + 'private.gateway.local/v1"'
    assert "literal-credential" in _rules(credential)
    assert "ai-translation-url" in _rules(endpoint)


def test_allows_empty_settings_placeholders_and_unrelated_public_urls():
    text = "\n".join(
        (
            'morph_ai_api_url = ""',
            'api_key = "YOUR_API_KEY"',
            'morph_ai_api_url = "https://api.example.com"',
            'project_url = "https://github.com/AliciaSource/MMD-Station"',
        )
    )
    assert not security_scan.scan_bytes("fixture", text.encode())
