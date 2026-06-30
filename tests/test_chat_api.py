import os
import pytest
import requests as req

os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test")
os.environ.setdefault("DATA_DIR", "/tmp")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)

MOCK_CHAT_RESULT = {
    "answer": "The council discussed the parking garage.",
    "utterances": [
        {
            "id": 1,
            "meeting_name": "City Council 2024-03-12",
            "start": 1842.5,
            "text": "I have concerns about the cost.",
            "speaker_name": "Alice",
            "score": 0.9,
        }
    ],
}


def test_chat_returns_answer_and_sources(mocker):
    mocker.patch("main.chat_rag", return_value=MOCK_CHAT_RESULT)
    r = client.post("/api/chat", json={"messages": [], "query": "parking garage?"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "The council discussed the parking garage."
    assert len(data["sources"]) == 1
    assert data["sources"][0]["meeting_name"] == "City Council 2024-03-12"
    assert data["sources"][0]["start"] == 1842.5
    assert data["sources"][0]["text"] == "I have concerns about the cost."


def test_chat_returns_503_when_ollama_unreachable(mocker):
    mocker.patch("main.chat_rag", side_effect=req.exceptions.ConnectionError())
    r = client.post("/api/chat", json={"messages": [], "query": "test?"})
    assert r.status_code == 503


def test_chat_returns_502_on_ollama_error(mocker):
    mocker.patch("main.chat_rag", side_effect=req.exceptions.HTTPError("500"))
    r = client.post("/api/chat", json={"messages": [], "query": "test?"})
    assert r.status_code == 502


def test_chat_passes_history_and_query_to_rag(mocker):
    mock = mocker.patch("main.chat_rag", return_value=MOCK_CHAT_RESULT)
    history = [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "First answer"},
    ]
    client.post("/api/chat", json={"messages": history, "query": "follow-up?"})
    _, kwargs = mock.call_args
    assert kwargs["query"] == "follow-up?"
    assert kwargs["messages"][0]["content"] == "First question"
