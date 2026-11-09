"""エージェントの配線テスト。

TestModel は実際のLLMを呼ばない偽モデルで、登録されたツールを全部呼んでから
ダミーの回答を返す。APIキーも利用枠も使わずに、
「ツールが登録され、呼ばれ、結果がモデルに戻るか」を確かめられる。
"""

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.test import TestModel

from app import agent as agent_module
from app import tools
from app.agent import agent

BASE_TOOLS = {"search_glossary", "get_lecture_summary", "make_quiz"}


def _parts(result, kind):
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, kind)]


def test_base_tools_are_registered_and_called():
    model = TestModel()
    with agent.override(model=model):
        result = agent.run_sync("LoRAとは？")

    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert BASE_TOOLS <= offered  # 演習でツールを足しても壊れないよう「含む」で判定

    called = {p.tool_name for p in _parts(result, ToolCallPart)}
    assert BASE_TOOLS <= called
    # 承認が必要なツール（requires_approval=True）は、実行されずに承認待ちになるので戻り値が無い
    waiting = len(result.output.approvals) if isinstance(result.output, DeferredToolRequests) else 0
    assert len(_parts(result, ToolReturnPart)) + waiting == len(_parts(result, ToolCallPart))
    assert result.output


def test_glossary_result_reaches_the_model():
    model = TestModel(call_tools=["search_glossary"])
    with agent.override(model=model):
        result = agent.run_sync("RAGとは？")
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == "search_glossary"


def test_learning_log_is_saved_only_after_approval(tmp_path, monkeypatch):
    log_dir = tmp_path / "learning_log"
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", log_dir)
    with agent.override(model=TestModel(call_tools=["save_learning_log"])):
        pending = agent.run_sync("学習記録を保存して")

    assert isinstance(pending.output, DeferredToolRequests)
    assert [call.tool_name for call in pending.output.approvals] == ["save_learning_log"]
    assert not log_dir.exists()

    monkeypatch.setattr("builtins.input", lambda _: "y")
    approvals = agent_module.request_tool_approvals(pending.output)
    with agent.override(model=TestModel(call_tools=[])):
        completed = agent.run_sync(
            message_history=pending.all_messages(),
            deferred_tool_results=pending.output.build_results(approvals=approvals),
        )

    assert isinstance(completed.output, str)
    saved_files = list(log_dir.glob("*.md"))
    assert len(saved_files) == 1
    assert saved_files[0].read_text(encoding="utf-8").startswith("# ")


def test_declining_learning_log_approval_does_not_save(tmp_path, monkeypatch):
    log_dir = tmp_path / "learning_log"
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", log_dir)
    with agent.override(model=TestModel(call_tools=["save_learning_log"])):
        pending = agent.run_sync("学習記録を保存して")

    assert isinstance(pending.output, DeferredToolRequests)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    approvals = agent_module.request_tool_approvals(pending.output)
    assert approvals[pending.output.approvals[0].tool_call_id] is False

    with agent.override(model=TestModel(call_tools=[])):
        agent.run_sync(
            message_history=pending.all_messages(),
            deferred_tool_results=pending.output.build_results(approvals=approvals),
        )

    assert not log_dir.exists()
