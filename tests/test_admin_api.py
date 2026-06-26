import os
import pytest
from unittest.mock import patch
from helpers import make_mock_conn

os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "secret"
os.environ.setdefault("DATABASE_URL", "postgresql://test")
os.environ.setdefault("DATA_DIR", "/tmp")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)
AUTH = ("admin", "secret")



def test_admin_meetings_requires_auth():
    r = client.get("/api/admin/meetings")
    assert r.status_code == 401


def test_admin_meetings_rejects_wrong_password():
    r = client.get("/api/admin/meetings", auth=("admin", "wrong"))
    assert r.status_code == 401


def test_admin_meetings_returns_list():
    mock_conn = make_mock_conn(
        fetchall_results=[[(1, "City Council 1-12-26", "2026-01-12", "City Council", 2, None)]]
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.get("/api/admin/meetings", auth=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["meeting_name"] == "City Council 1-12-26"
    assert data[0]["unlabeled_count"] == 2


def test_admin_meetings_includes_relabel_status():
    mock_conn = make_mock_conn(
        fetchall_results=[[(1, "City Council 1-12-26", "2026-01-12", "City Council", 0, "pending")]]
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.get("/api/admin/meetings", auth=AUTH)
    assert r.status_code == 200
    assert r.json()[0]["relabel_status"] == "pending"


def test_admin_label_cluster_returns_ok():
    mock_conn = make_mock_conn(
        fetchone_results=[None, (42,)],  # no existing speaker, then new id
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.post(
            "/api/admin/meetings/1/clusters/SPEAKER_0/label",
            json={"speaker_name": "Councilor Smith"},
            auth=AUTH,
        )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_admin_set_canonical_404_for_missing_embedding():
    mock_conn = make_mock_conn(fetchone_results=[None])
    with patch("main.connect", return_value=mock_conn):
        r = client.post("/api/admin/speaker-embeddings/999/canonical", auth=AUTH)
    assert r.status_code == 404


def test_admin_set_canonical_400_when_embedding_unlabeled():
    mock_conn = make_mock_conn(fetchone_results=[(None,)])  # speaker_id is NULL
    with patch("main.connect", return_value=mock_conn):
        r = client.post("/api/admin/speaker-embeddings/1/canonical", auth=AUTH)
    assert r.status_code == 400


def test_admin_speakers_returns_list():
    mock_conn = make_mock_conn(
        fetchall_results=[[(3, "Councilor Smith", None, 42, 100, 0.81, 5)]]
    )
    with patch("main.connect", return_value=mock_conn):
        r = client.get("/api/admin/speakers", auth=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data[0]["speaker_name"] == "Councilor Smith"
    assert data[0]["mean_confidence"] == pytest.approx(0.81)


def test_admin_relabel_requires_auth():
    r = client.post("/api/admin/meetings/1/relabel")
    assert r.status_code == 401


def test_admin_relabel_enqueues_job():
    mock_conn = make_mock_conn(fetchone_results=[(99,)])
    with patch("main.connect", return_value=mock_conn):
        r = client.post("/api/admin/meetings/1/relabel", auth=AUTH)
    assert r.status_code == 200
    assert r.json() == {"job_id": 99}
