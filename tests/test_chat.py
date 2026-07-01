import pytest
from unittest.mock import MagicMock


MOCK_UTTERANCES = [
    {
        "id": 1,
        "speaker_name": "Alice",
        "meeting_name": "Council 2024-01-01",
        "start": 65.0,
        "text": "Hello world",
        "score": 0.9,
    },
]


def test_build_context_message_formats_utterances():
    from webapp.lib.chat import build_context_message
    result = build_context_message(MOCK_UTTERANCES)
    assert "[Alice, Council 2024-01-01, 1:05] Hello world" in result


def test_build_context_message_with_empty_list():
    from webapp.lib.chat import build_context_message
    result = build_context_message([])
    assert "No relevant context" in result


def test_chat_includes_conversation_history(mocker):
    mock_client = _make_mock_client(mocker, content="Answer.")

    history = [
        {"role": "user", "content": "Prior question"},
        {"role": "assistant", "content": "Prior answer"},
    ]
    from webapp.lib.chat import run_chat
    run_chat("follow-up?", history)

    messages = mock_client.chat.call_args.kwargs["messages"]
    contents = [m["content"] for m in messages if isinstance(m, dict)]
    assert "Prior question" in contents
    assert "Prior answer" in contents
    assert "follow-up?" in contents


def _make_mock_client(mocker, content=None, tool_calls=None, thinking=None, prompt_eval_count=100):
    """Return a mock ollama Client whose chat() yields a single configured response."""
    mocker.patch("webapp.lib.chat.get_schemas", return_value="")
    mock_client = MagicMock()
    mocker.patch("webapp.lib.chat.Client", return_value=mock_client)
    resp = MagicMock()
    resp.message.content = content
    resp.message.tool_calls = tool_calls
    resp.message.thinking = thinking
    resp.prompt_eval_count = prompt_eval_count
    mock_client.chat.return_value = resp
    return mock_client


def test_no_context_response_strips_token_and_clears_utterances(mocker):
    mock_client = _make_mock_client(mocker, content="[NO_CONTEXT] Nothing relevant found.")

    from webapp.lib.chat import run_chat
    result = run_chat("anything?", [])

    assert result["answer"] == "Nothing relevant found."
    assert result["utterances"] == []


def test_tool_limit_exhaustion_returns_empty_answer(mocker):
    mock_client = _make_mock_client(mocker)  # content=None, tool_calls=None, thinking=None

    from webapp.lib.chat import run_chat
    result = run_chat("anything?", [])

    assert result["answer"] == ""
    assert result["utterances"] == []
    assert mock_client.chat.call_count == 10  # TOOL_LIMIT exhausted
