from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.genai import errors, types

from app.ask import DEFAULT_QUESTION, MODEL, ask, main


@pytest.fixture(autouse=True)
def dummy_api_key(monkeypatch):
    monkeypatch.setattr("app.ask.get_api_key", lambda: "test-api-key")


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


def model_response(text):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            finish_reason="STOP",
        )],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=12, candidates_token_count=34,
        ),
    )


@pytest.mark.parametrize("initial_question", [[], ["LoRAとは？"]])
def test_chat_sends_previous_question_and_answer(initial_question, capsys):
    inputs = ([] if initial_question else ["LoRAとは？"]) + ["それを短く説明して", "/exit"]
    with (
        patch("sys.argv", ["app.ask", "--chat", *initial_question]),
        patch("builtins.input", side_effect=inputs),
        patch("google.genai.models.Models.generate_content", side_effect=[
            model_response("LoRAの説明"), model_response("短い説明"),
        ]) as generate,
    ):
        main()

    assert generate.call_count == 2
    assert generate.call_args.kwargs["model"] == MODEL
    contents = generate.call_args.kwargs["contents"]
    assert [(c.role, c.parts[0].text) for c in contents] == [
        ("user", "LoRAとは？"),
        ("model", "LoRAの説明"),
        ("user", "それを短く説明して"),
    ]
    output = capsys.readouterr().out
    assert "LoRAの説明" in output and "短い説明" in output
    assert output.count("input=12 output=34") == 2


@pytest.mark.parametrize("exit_input", ["/exit", "/quit", EOFError(), KeyboardInterrupt()])
def test_chat_skips_blank_lines_and_exits_without_sending(exit_input):
    with (
        patch("sys.argv", ["app.ask", "--chat"]),
        patch("builtins.input", side_effect=["", "  ", exit_input]),
        patch("google.genai.models.Models.generate_content") as generate,
    ):
        main()
    generate.assert_not_called()


def test_chat_preserves_history_after_api_error(capsys):
    with (
        patch("sys.argv", ["app.ask", "--chat", "最初の質問"]),
        patch("builtins.input", side_effect=["失敗する質問", "再度質問", "/quit"]),
        patch("google.genai.models.Models.generate_content", side_effect=[
            model_response("最初の回答"),
            errors.ClientError(429, {"error": {"message": "rate limit"}}),
            model_response("次の回答"),
        ]) as generate,
    ):
        main()
    contents = generate.call_args.kwargs["contents"]
    assert [c.parts[0].text for c in contents] == ["最初の質問", "最初の回答", "再度質問"]
    output = capsys.readouterr().out
    assert "レート制限に達しました" in output
    assert "次の回答" in output


def test_new_chat_starts_without_previous_session_history():
    with (
        patch("sys.argv", ["app.ask", "--chat", "質問"]),
        patch("builtins.input", side_effect=["/exit", "/exit"]),
        patch("google.genai.models.Models.generate_content", side_effect=[
            model_response("回答1"), model_response("回答2"),
        ]) as generate,
    ):
        main()
        main()
    assert [len(call.kwargs["contents"]) for call in generate.call_args_list] == [1, 1]


@pytest.mark.parametrize("arguments, question", [([], DEFAULT_QUESTION), (["質問"], "質問")])
def test_single_question_cli_is_preserved(arguments, question):
    with patch("sys.argv", ["app.ask", *arguments]), patch("app.ask.ask", return_value="回答") as single_ask:
        main()
    single_ask.assert_called_once_with(question)


def test_single_question_cli_exits_on_api_error(capsys):
    with (
        patch("sys.argv", ["app.ask", "質問"]),
        patch("app.ask.ask", side_effect=errors.ServerError(503, {"error": {"message": "busy"}})),
        pytest.raises(SystemExit, match="1"),
    ):
        main()
    assert "モデルが混み合っています" in capsys.readouterr().out
