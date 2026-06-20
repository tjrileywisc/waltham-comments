import pytest
from unittest.mock import MagicMock
from helpers import make_mock_conn
from db import build_window_text, extract_meeting_type, extract_meeting_date, extract_meeting_part, is_meeting_processed, save_meeting


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

def test_save_meeting_returns_meeting_id_and_speaker_lookup(mocker):
    segments = [{"start": 0.0, "end": 2.0, "text": "Hello", "speaker": "DEFAULT"}]

    mock_conn = make_mock_conn(
        fetchone_results=[(7,)],
        fetchall_results=[[(99, "DEFAULT")], [(1,)]],
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    meeting_id, speaker_lookup = save_meeting(mock_conn, "Test Meeting 1-1-26", segments)

    assert meeting_id == 7
    assert speaker_lookup["DEFAULT"] == 99


def test_save_meeting_stores_diarization_speaker_and_confidence(mocker):
    segments = [{
        "start": 0.0, "end": 2.0, "text": "Hello",
        "speaker": "DEFAULT",
        "diarization_speaker": "SPEAKER_2",
        "confidence": 0.83,
    }]

    mock_conn = make_mock_conn(
        fetchone_results=[(1,)],
        fetchall_results=[[(99, "DEFAULT")], [(1,)]],
    )
    mock_cur = mock_conn.cursor.return_value

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.0] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    save_meeting(mock_conn, "Test Meeting 1-2-26", segments)

    sql, rows = mock_cur.executemany.call_args.args
    assert "diarization_speaker" in sql
    assert "confidence" in sql
    assert rows[0][6] == "SPEAKER_2"   # diarization_speaker at index 6
    assert rows[0][7] == pytest.approx(0.83)  # confidence at index 7
    
def test_is_meeting_processed_returns_true_when_present():
    assert is_meeting_processed(make_mock_conn(fetchone_results=[("meeting_name",)]), "meeting_name") is True


def test_is_meeting_processed_returns_false_when_absent():
    assert is_meeting_processed(make_mock_conn(fetchone_results=[None]), "new_meeting") is False

def test_extract_meeting_type_strips_trailing_date():
    assert extract_meeting_type("City Council 6-13-26") == "City Council"

def test_extract_meeting_type_supports_continued_meetings():
    assert extract_meeting_type("City Council 6-13-26 Part 2") == "City Council"

def test_extract_meeting_type_strips_four_digit_year():
    assert extract_meeting_type("Finance Committee 12-31-2024") == "Finance Committee"

def test_extract_meeting_type_strips_single_digit_month_and_day():
    assert extract_meeting_type("Board Meeting 1-1-26") == "Board Meeting"

def test_extract_meeting_type_no_date_unchanged():
    assert extract_meeting_type("Special Session") == "Special Session"

def test_extract_meeting_type_date_not_at_end_unchanged():
    # regex is anchored to $, so a date in the middle is not stripped
    assert extract_meeting_type("6-13-26 City Council") == "6-13-26 City Council"

def test_extract_meeting_date_no_match():
    assert extract_meeting_date("City Council") is None
    
def test_extract_incomplete_meeting_date():
    assert extract_meeting_date("City Council 2-26") is None
    
def test_extract_meeting_date():
    meeting_date = extract_meeting_date("City Council 2-22-02")
    assert meeting_date.month == 2
    assert meeting_date.day == 22
    assert meeting_date.year == 2002
    
def test_extract_meeting_part():

    assert extract_meeting_part("City Council") is None
    assert extract_meeting_part("City Council Part") is None
    assert extract_meeting_part("City Part 1 Council") is None
    assert extract_meeting_part("City Council Part 1") == "1"
    assert extract_meeting_part("City Council 2-2-02 Part 1") == "1"


def test_save_meeting_stores_none_for_missing_diarization_fields(mocker):
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello", "speaker": "DEFAULT"}]

    mock_conn = make_mock_conn(
        fetchone_results=[(1,)],
        fetchall_results=[[(99, "DEFAULT")], [(1,)]],
    )
    mock_cur = mock_conn.cursor.return_value

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.0] * 384]}
    mocker.patch("db.requests.post", return_value=mock_resp)

    save_meeting(mock_conn, "Test Meeting 1-3-26", segments)

    _, rows = mock_cur.executemany.call_args.args
    assert rows[0][6] is None   # diarization_speaker
    assert rows[0][7] is None   # confidence


def test_save_speaker_embeddings_inserts_one_row_per_cluster(mocker):
    import numpy as np
    from db import save_speaker_embeddings

    mock_conn = make_mock_conn()
    mock_cur = mock_conn.cursor.return_value

    embeddings = {
        "SPEAKER_0": np.zeros(256),
        "SPEAKER_1": np.ones(256),
    }
    cluster_to_speaker_id = {"SPEAKER_0": 5, "SPEAKER_1": None}

    save_speaker_embeddings(mock_conn, meeting_id=3, speaker_embeddings=embeddings,
                            cluster_to_speaker_id=cluster_to_speaker_id)

    assert mock_cur.execute.call_count == 2
    first_call_args = mock_cur.execute.call_args_list[0].args
    assert "INSERT INTO speaker_embeddings" in first_call_args[0]


def test_save_speaker_embeddings_passes_none_speaker_id_for_unmatched(mocker):
    import numpy as np
    from db import save_speaker_embeddings

    mock_conn = make_mock_conn()
    mock_cur = mock_conn.cursor.return_value

    embeddings = {"SPEAKER_0": np.zeros(256)}
    save_speaker_embeddings(mock_conn, meeting_id=1, speaker_embeddings=embeddings,
                            cluster_to_speaker_id={"SPEAKER_0": None})

    params = mock_cur.execute.call_args_list[0].args[1]
    assert params[0] is None   # speaker_id is None for unmatched cluster
    assert params[2] == "SPEAKER_0"