import csv
from pathlib import Path
from unittest.mock import MagicMock


def test_migrate_single_csv(mocker, tmp_path):
    csv_file = tmp_path / "City Council 1-1-26.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "start", "end", "text", "speaker"])
        writer.writeheader()
        writer.writerow({"id": 0, "start": 0.0, "end": 1.5, "text": "Hello", "speaker": "SPEAKER_00"})
        writer.writerow({"id": 1, "start": 2.0, "end": 3.0, "text": "World", "speaker": "SPEAKER_01"})

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (0,)       # no existing rows for this meeting
    mock_cur.fetchall.return_value = [(1,), (2,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 384, [0.2] * 384]}
    mocker.patch("migrate_csv_to_db.requests.post", return_value=mock_resp)
    mocker.patch("migrate_csv_to_db.psycopg.connect", return_value=mock_conn)

    import migrate_csv_to_db
    migrate_csv_to_db.migrate_directory(str(tmp_path))

    mock_cur.executemany.assert_called_once()
    _, rows = mock_cur.executemany.call_args.args
    assert len(rows) == 2
    assert rows[0][0] == "City Council 1-1-26"  # meeting_name
    assert rows[0][4] == "Hello"                 # text


def test_migrate_skips_meetings_already_in_db(mocker, tmp_path):
    csv_file = tmp_path / "City Council 1-1-26.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "start", "end", "text", "speaker"])
        writer.writeheader()
        writer.writerow({"id": 0, "start": 0.0, "end": 1.5, "text": "Hello", "speaker": "SPEAKER_00"})

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (3,)       # 3 rows already exist — skip
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    mocker.patch("migrate_csv_to_db.psycopg.connect", return_value=mock_conn)

    import migrate_csv_to_db
    migrate_csv_to_db.migrate_directory(str(tmp_path))

    mock_cur.executemany.assert_not_called()
