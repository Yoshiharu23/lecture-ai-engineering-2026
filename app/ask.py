"""第1回: 素のLLMに質問するスクリプト。

使い方:
    uv run python -m app.ask "LoRAとは何ですか？"
    uv run python -m app.ask            # 質問を省略すると、講座に固有の質問をする
    uv run python -m app.ask --chat     # 会話履歴を保って続けて質問する
    uv run python -m app.ask --chat "LoRAとは何ですか？"

通常は会話履歴を持たない1回だけの呼び出し。--chat では同じセッションを使い続ける。
会話履歴は実行中のメモリにのみ保持し、終了時に破棄する。ツールは使わない。
講座に固有のことを聞くと、「分からない」と答えるか、一般論でもっともらしく答える
（講座の実際とは違う）ことを確かめよう。
（第3回で、用語集を検索できるエージェントにして改善する）
"""

import argparse

from google import genai
from google.genai import errors, types

from app.config import MODEL, api_error_message, get_api_key

# 講座に固有の質問。正しい答えは data/glossary.json の homework-levels にある
DEFAULT_QUESTION = "AIE2026の講座の宿題にある「3レベル」とは何ですか？"


def response_text(response: types.GenerateContentResponse) -> str:
    """通常の質問・対話の両方で、トークン数を表示して回答を返す。"""
    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else None
    output_tokens = usage.candidates_token_count if usage else None
    print(f"[tokens] input={input_tokens} output={output_tokens}")

    return response.text


def ask(question: str) -> str:
    client = genai.Client(api_key=get_api_key())
    response = client.models.generate_content(model=MODEL, contents=question)
    return response_text(response)


def run_chat(first_question: str | None = None) -> None:
    """同じチャットに質問を送り、過去の質問と回答を次の質問に引き継ぐ。"""
    with genai.Client(api_key=get_api_key()) as client:
        chat = client.chats.create(model=MODEL)
        print("会話履歴を保って質問します。/exit または /quit、Ctrl+D、Ctrl+C で終了します。")
        question = first_question
        try:
            while True:
                if question is None:
                    question = input("質問> ")
                question = question.strip()
                if question in ("/exit", "/quit"):
                    return
                if question:
                    print(f"[質問] {question}\n")
                    try:
                        print(response_text(chat.send_message(question)))
                    except errors.APIError as e:
                        print(api_error_message(e.code, e.message))
                question = None
        except (EOFError, KeyboardInterrupt):
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description="素のLLMに質問する")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--chat", action="store_true", help="会話履歴を保って続けて質問する")
    args = parser.parse_args()

    print(f"[model] {MODEL}")
    if args.chat:
        run_chat(args.question)
        return

    question = args.question if args.question is not None else DEFAULT_QUESTION
    print(f"[質問] {question}\n")
    try:
        print(ask(question))
    except errors.APIError as e:
        print(api_error_message(e.code, e.message))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
