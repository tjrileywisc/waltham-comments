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
    from lib.chat import build_context_message
    result = build_context_message(MOCK_UTTERANCES)
    assert "[Alice, Council 2024-01-01, 1:05] Hello world" in result


def test_build_context_message_with_empty_list():
    from lib.chat import build_context_message
    result = build_context_message([])
    assert "No relevant context" in result


def test_chat_returns_answer_and_utterances(mocker, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    mocker.patch("lib.chat.do_search", return_value=MOCK_UTTERANCES)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "Alice said hello."}}
    mock_post = mocker.patch("lib.chat.requests.post", return_value=mock_resp)

    from lib.chat import chat
    result = chat("what did Alice say?", [])

    assert result["answer"] == "Alice said hello."
    assert result["utterances"] == MOCK_UTTERANCES

    call_json = mock_post.call_args.kwargs["json"]
    assert call_json["stream"] is False
    assert call_json["messages"][0]["role"] == "system"
    assert call_json["messages"][-1] == {"role": "user", "content": "what did Alice say?"}


def test_chat_includes_conversation_history(mocker, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    mocker.patch("lib.chat.do_search", return_value=[])

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "Answer."}}
    mock_post = mocker.patch("lib.chat.requests.post", return_value=mock_resp)

    history = [
        {"role": "user", "content": "Prior question"},
        {"role": "assistant", "content": "Prior answer"},
    ]
    from lib.chat import chat
    chat("follow-up?", history)

    messages = mock_post.call_args.kwargs["json"]["messages"]
    contents = [m["content"] for m in messages]
    assert "Prior question" in contents
    assert "Prior answer" in contents
    assert messages[-1]["content"] == "follow-up?"


def test_chat_raises_on_ollama_http_error(mocker, monkeypatch):
    import requests as req
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    mocker.patch("lib.chat.do_search", return_value=[])

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError("500")
    mocker.patch("lib.chat.requests.post", return_value=mock_resp)

    from lib.chat import chat
    with pytest.raises(req.exceptions.HTTPError):
        chat("test?", [])


def test_chat_raises_on_connection_error(mocker, monkeypatch):
    import requests as req
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    mocker.patch("lib.chat.do_search", return_value=[])
    mocker.patch("lib.chat.requests.post", side_effect=req.exceptions.ConnectionError())

    from lib.chat import chat
    with pytest.raises(req.exceptions.ConnectionError):
        chat("test?", [])
