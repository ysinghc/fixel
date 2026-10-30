import os

from fixel.env import load_dotenv, parse


def test_parse_handles_comments_quotes_and_blanks():
    text = """
# a comment
MODEL_API_KEY=            # META_MODEL_API is read too
MODEL_BASE_URL=https://api.meta.ai/v1
FIXEL_MODE=record # inline comment
QUOTED="has # hash"
SINGLE='abc'
export_style=1
NOEQUALS
"""
    assert parse(text) == {"MODEL_BASE_URL": "https://api.meta.ai/v1", "FIXEL_MODE": "record",
                           "QUOTED": "has # hash", "SINGLE": "abc", "export_style": "1"}


def test_empty_values_are_not_loaded_and_real_environment_wins(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("MODEL_API_KEY=\nMETA_MODEL_API=from-file\nFIXEL_MODE=replay\n")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_MODEL_API", raising=False)
    monkeypatch.setenv("FIXEL_MODE", "live")
    assert load_dotenv(f) == [f]
    assert "MODEL_API_KEY" not in os.environ          # a blank placeholder must not shadow META_MODEL_API
    assert os.environ["META_MODEL_API"] == "from-file"
    assert os.environ["FIXEL_MODE"] == "live"          # already set: not overridden
    monkeypatch.delenv("META_MODEL_API")


def test_missing_file_is_fine(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == []
