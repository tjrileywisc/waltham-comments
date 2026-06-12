import pytest
from unittest.mock import MagicMock


def test_get_transcript_returns_rows():
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        (0, 0.0, 2.0, "Hello", "SPEAKER_00"),
        (1, 2.5, 4.0, "World", "SPEAKER_01"),
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from lib.db import get_transcript
    result = get_transcript(mock_conn, "Test Meeting")

    sql = mock_cur.execute.call_args.args[0]
    assert "WHERE meeting_name" in sql

    assert result == [
        {"id": 0, "start": 0.0, "end": 2.0, "text": "Hello", "speaker": "SPEAKER_00"},
        {"id": 1, "start": 2.5, "end": 4.0, "text": "World", "speaker": "SPEAKER_01"},
    ]


def test_get_transcript_empty_returns_empty_list():
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from lib.db import get_transcript
    result = get_transcript(mock_conn, "Missing Meeting")
    assert result == []


def test_do_search_returns_results(mocker, monkeypatch):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        ("City Council 1-12-26", 10.0, "Traffic on Main Street", "SPEAKER_00", 0.91),
        ("City Council 1-26-26", 45.2, "The traffic light proposal", "SPEAKER_01", 0.87),
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_embed_resp = MagicMock()
    mock_embed_resp.json.return_value = {"embeddings": [[0.1] * 384]}
    mocker.patch("lib.search.requests.post", return_value=mock_embed_resp)
    mocker.patch("lib.search.psycopg.connect", return_value=mock_conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    from lib.search import do_search
    results = do_search("traffic")

    assert len(results) == 2
    assert results[0]["meeting_name"] == "City Council 1-12-26"
    assert results[0]["start"] == 10.0
    assert results[0]["score"] == pytest.approx(0.91)

    sql = mock_cur.execute.call_args.args[0]
    assert "utterance_embeddings" in sql
    assert "ORDER BY" in sql
