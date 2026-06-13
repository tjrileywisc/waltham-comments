from db import build_window_text


def test_build_window_text_includes_preceding_segments_within_window():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hello"},
        {"start": 1.5, "end": 2.5, "text": "world"},
        {"start": 3.0, "end": 4.0, "text": "today"},
    ]
    # window_start = 4.0 - 5.0 = -1.0; all three start times >= -1.0
    assert build_window_text(segments, 2) == "Hello world today"


def test_build_window_text_excludes_segments_outside_window():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Old"},
        {"start": 5.0, "end": 6.0, "text": "Recent"},
        {"start": 7.0, "end": 8.0, "text": "Current"},
    ]
    # window_start = 8.0 - 5.0 = 3.0; "Old" starts at 0.0 < 3.0, excluded
    assert build_window_text(segments, 2) == "Recent Current"


def test_build_window_text_long_segment_used_alone():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Before"},
        {"start": 2.0, "end": 10.0, "text": "Long segment"},
    ]
    # duration 8.0 >= 5.0 — use alone regardless of preceding segments
    assert build_window_text(segments, 1) == "Long segment"


def test_build_window_text_first_segment():
    segments = [{"start": 0.0, "end": 2.0, "text": "First"}]
    assert build_window_text(segments, 0) == "First"


from unittest.mock import MagicMock


def test_save_meeting_inserts_utterances_and_embeddings(mocker):
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello", "speaker": "SPEAKER_00"},
        {"start": 2.5, "end": 4.0, "text": "World", "speaker": "SPEAKER_01"},
    ]

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [(1,), (2,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 384, [0.2] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    from db import save_meeting
    save_meeting(mock_conn, "Test Meeting 1-1-26", segments)

    mock_cur.executemany.assert_called_once()
    insert_sql, rows = mock_cur.executemany.call_args.args
    assert "INSERT INTO utterances" in insert_sql
    assert len(rows) == 2
    assert rows[0] == ("Test Meeting 1-1-26", 0, 0.0, 2.0, "Hello", "SPEAKER_00")
    assert rows[1] == ("Test Meeting 1-1-26", 1, 2.5, 4.0, "World", "SPEAKER_01")

    assert mock_conn.commit.call_count == 2

    embedding_calls = [
        c for c in mock_cur.execute.call_args_list
        if "utterance_embeddings" in c.args[0]
    ]
    assert len(embedding_calls) == 2


def test_save_meeting_uses_default_speaker_when_missing(mocker):
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello"}]  # no "speaker" key

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [(1,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.0] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    from db import save_meeting
    save_meeting(mock_conn, "Test Meeting", segments)

    _, rows = mock_cur.executemany.call_args.args
    assert rows[0][5] == "DEFAULT"
