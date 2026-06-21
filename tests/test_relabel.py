import numpy as np
import pytest
from unittest.mock import patch
from helpers import make_mock_conn
from relabel import relabel_meeting, process_pending_jobs


def test_relabel_meeting_does_nothing_when_no_unassigned_clusters():
    """When all clusters are already assigned, no UPDATEs should run."""
    conn = make_mock_conn(fetchall_results=[[]])  # empty SELECT
    relabel_meeting(conn, meeting_id=1)
    sqls = [call.args[0] for call in conn.cursor.return_value.execute.call_args_list]
    assert not any("UPDATE" in sql for sql in sqls)


def test_relabel_meeting_skips_clusters_that_stay_default():
    """Clusters that Identifier still can't match are left alone (no UPDATE)."""
    conn = make_mock_conn(
        fetchall_results=[
            [("SPEAKER_0", "[0.0,1.0]")],  # relabel SELECT: one unassigned cluster
            [],                              # Identifier's SELECT: no known speakers in DB
        ],
    )
    relabel_meeting(conn, meeting_id=1)
    sqls = [call.args[0] for call in conn.cursor.return_value.execute.call_args_list]
    assert not any("UPDATE" in sql for sql in sqls)


def test_relabel_meeting_updates_matched_clusters():
    """Clusters matched above threshold get utterances and speaker_embeddings updated."""
    conn = make_mock_conn(
        fetchall_results=[
            [("SPEAKER_0", "[1.0,0.0]")],       # relabel SELECT
            [("Alice", "[1.0,0.0]")],             # Identifier's SELECT
        ],
        fetchone_results=[(7,)],                  # SELECT id FROM speakers WHERE speaker_name = 'Alice'
    )
    relabel_meeting(conn, meeting_id=3)
    sqls = [call.args[0] for call in conn.cursor.return_value.execute.call_args_list]
    update_sqls = [s for s in sqls if "UPDATE" in s]
    assert len(update_sqls) == 2  # utterances + speaker_embeddings


def test_relabel_meeting_skips_update_when_speaker_not_found():
    """If Identifier returns a name not in speakers table, skip rather than crash."""
    conn = make_mock_conn(
        fetchall_results=[
            [("SPEAKER_0", "[1.0,0.0]")],
            [("Alice", "[1.0,0.0]")],
        ],
        fetchone_results=[None],  # speaker not in DB
    )
    relabel_meeting(conn, meeting_id=3)
    sqls = [call.args[0] for call in conn.cursor.return_value.execute.call_args_list]
    assert not any("UPDATE" in sql for sql in sqls)


def test_process_pending_jobs_dispatches_relabel():
    """process_pending_jobs calls relabel_meeting with the payload meeting_id."""
    conn = make_mock_conn()
    with patch("relabel.claim_pending_job", side_effect=[(1, "relabel", {"meeting_id": 5}), None]), \
         patch("relabel.relabel_meeting") as mock_relabel, \
         patch("relabel.complete_job") as mock_complete:
        process_pending_jobs(conn)
    mock_relabel.assert_called_once_with(conn, 5)
    mock_complete.assert_called_once_with(conn, 1)


def test_process_pending_jobs_calls_fail_job_on_error():
    """When relabel_meeting raises, the job is marked failed with the error message."""
    conn = make_mock_conn()
    with patch("relabel.claim_pending_job", side_effect=[(1, "relabel", {"meeting_id": 5}), None]), \
         patch("relabel.relabel_meeting", side_effect=Exception("disk full")), \
         patch("relabel.fail_job") as mock_fail:
        process_pending_jobs(conn)
    mock_fail.assert_called_once_with(conn, 1, "disk full")


def test_process_pending_jobs_stops_when_queue_empty():
    """process_pending_jobs stops looping as soon as claim returns None."""
    conn = make_mock_conn()
    with patch("relabel.claim_pending_job", return_value=None) as mock_claim:
        process_pending_jobs(conn)
    mock_claim.assert_called_once()
