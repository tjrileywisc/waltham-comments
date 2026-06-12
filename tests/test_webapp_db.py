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
