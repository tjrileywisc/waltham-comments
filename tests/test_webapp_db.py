import pytest
from unittest.mock import MagicMock
from helpers import make_mock_conn


def test_get_transcript_returns_rows():
    mock_conn = make_mock_conn(fetchall_results=[[
        (0, 0.0, 2.0, "Hello", "SPEAKER_00"),
        (1, 2.5, 4.0, "World", "SPEAKER_01"),
    ]])

    from webapp.lib.db import get_transcript
    result = get_transcript(mock_conn, "Test Meeting")

    assert result == [
        {"id": 0, "start": 0.0, "end": 2.0, "text": "Hello", "speaker": "SPEAKER_00"},
        {"id": 1, "start": 2.5, "end": 4.0, "text": "World", "speaker": "SPEAKER_01"},
    ]


def test_get_transcript_empty_returns_empty_list():
    mock_conn = make_mock_conn(fetchall_results=[[]])

    from webapp.lib.db import get_transcript
    result = get_transcript(mock_conn, "Missing Meeting")
    assert result == []


def test_vector_search_returns_results(mocker, monkeypatch):
    mock_conn = make_mock_conn(fetchall_results=[[
        (0, "City Council 1-12-26", 10.0, "Traffic on Main Street", "SPEAKER_00", 0.91),
        (1, "City Council 1-26-26", 45.2, "The traffic light proposal", "SPEAKER_01", 0.87),
    ]])
    mock_cur = mock_conn.cursor.return_value

    mock_embed_resp = MagicMock()
    mock_embed_resp.json.return_value = {"embeddings": [[0.1] * 384]}
    mocker.patch("webapp.lib.search.requests.post", return_value=mock_embed_resp)
    mocker.patch("webapp.lib.search.connect", return_value=mock_conn)

    from webapp.lib.search import vector_search
    results = vector_search("traffic")

    assert len(results) == 2
    assert results[0]["meeting_name"] == "City Council 1-12-26"
    assert results[0]["start"] == 10.0
    assert results[0]["score"] == pytest.approx(0.91)

    sql = mock_cur.execute.call_args.args[0]
    assert "utterance_embeddings" in sql
    assert "ORDER BY" in sql
