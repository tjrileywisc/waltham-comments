import numpy as np
import pytest
from unittest.mock import MagicMock
from identification import Identifier


def make_conn(rows):
    """Mock psycopg connection whose cursor returns `rows` from fetchall."""
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = rows
    conn.cursor.return_value = cur
    return conn


def test_returns_default_when_no_labeled_embeddings():
    identifier = Identifier()
    result = identifier(make_conn([]), {"SPEAKER_0": np.array([1.0, 0.0])})
    assert result == [("DEFAULT", None)]


def test_matches_speaker_above_threshold():
    conn = make_conn([("Alice", "[1.0,0.0]")])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([1.0, 0.0])})
    name, score = result[0]
    assert name == "Alice"
    assert score == pytest.approx(1.0)


def test_returns_default_when_below_threshold():
    conn = make_conn([("Alice", "[1.0,0.0]")])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([0.0, 1.0])})
    name, score = result[0]
    assert name == "DEFAULT"
    assert score is None


def test_picks_best_match_among_multiple_speakers():
    conn = make_conn([("Alice", "[1.0,0.0]"), ("Bob", "[0.0,1.0]")])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([0.9, 0.1])})
    name, score = result[0]
    assert name == "Alice"
    assert score > 0.7


def test_multiple_clusters_matched_independently():
    conn = make_conn([("Alice", "[1.0,0.0]"), ("Bob", "[0.0,1.0]")])
    identifier = Identifier()
    result = identifier(conn, {
        "SPEAKER_0": np.array([1.0, 0.0]),
        "SPEAKER_1": np.array([0.0, 1.0]),
    })
    assert result[0][0] == "Alice"
    assert result[1][0] == "Bob"


def test_centroid_averages_multiple_embeddings_per_speaker():
    # Alice has two embeddings that individually point in different directions
    # but their centroid points toward [1, 0], so a [0.9, 0.1] cluster should match her
    conn = make_conn([
        ("Alice", "[1.0,0.0]"),
        ("Alice", "[0.8,0.2]"),
        ("Bob",   "[0.0,1.0]"),
    ])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([0.9, 0.1])})
    assert result[0][0] == "Alice"
