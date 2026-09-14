import json
import shutil
from pathlib import Path

import pytest

from openclaw_longbanana import config
from openclaw_longbanana.judge import runner


def test_claude_official_defaults(monkeypatch):
    monkeypatch.setattr(config, 'load_env_file', lambda: None)
    for key in ('OPENCLAW_MODEL_PROVIDER', 'OPENCLAW_MODEL_ID', 'OPENCLAW_MODEL_BASE_URL',
                'OPENCLAW_MODEL_API_KEY_ENV', 'OPENCLAW_MODEL_API'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    cfg = config.load_openclaw_model_config()
    assert cfg.provider == 'anthropic'
    assert cfg.base_url == 'https://api.anthropic.com'
    assert cfg.api == 'anthropic-messages'
    assert cfg.api_key_env == 'ANTHROPIC_API_KEY'
    assert not cfg.allow_private_network


def test_gemini_official_without_service_account(monkeypatch, tmp_path):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('OPENCLAW_JUDGE_PROVIDER', 'google')
    monkeypatch.setenv('OPENCLAW_MODEL_ID', 'claude-sonnet-4-6')
    monkeypatch.setenv('AGENT_JUDGE_GEMINI_MODEL', 'gemini-3-flash-preview')
    monkeypatch.setenv('LONGBANANA_DATA_ROOT', str(tmp_path))
    monkeypatch.setattr(runner, '_google_vertex_access_token', lambda _: pytest.fail('must not use Vertex auth'))
    env, root = runner._build_openclaw_env()
    try:
        cfg = json.loads(Path(env['OPENCLAW_CONFIG_PATH']).read_text())
        provider = cfg['models']['providers']['google']
        assert provider['baseUrl'] == 'https://generativelanguage.googleapis.com/v1beta'
        assert provider['apiKey'] == 'test-key'
        assert not provider['headers']
        assert cfg['agents']['defaults']['model'] == 'google/gemini-3-flash-preview'
    finally:
        shutil.rmtree(root)
