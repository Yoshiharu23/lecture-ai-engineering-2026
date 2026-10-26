from types import SimpleNamespace
from unittest.mock import patch

from app.ask import ask


def test_ask_prints_input_and_output_token_counts(capsys):
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=34,
        ),
        text="answer",
    )
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: response)
    )

    with patch("app.ask.genai.Client", return_value=client):
        result = ask("question")

    assert result == "answer"
    assert "input=12 output=34" in capsys.readouterr().out


def test_ask_handles_missing_usage_metadata(capsys):
    response = SimpleNamespace(usage_metadata=None, text="answer")
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: response)
    )

    with patch("app.ask.genai.Client", return_value=client):
        result = ask("question")

    assert result == "answer"
    assert "input=None output=None" in capsys.readouterr().out
