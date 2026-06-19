import numpy as np
import pytest
from helpers import make_mock_conn
from identification import Identifier


def test_returns_default_when_no_labeled_embeddings():
    identifier = Identifier()
    result = identifier(make_mock_conn(fetchall_results=[[]]), {"SPEAKER_0": np.array([1.0, 0.0])})
    assert result == [("DEFAULT", None)]


def test_matches_speaker_above_threshold():
    conn = make_mock_conn(fetchall_results=[[("Alice", "[1.0,0.0]")]])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([1.0, 0.0])})
    name, score = result[0]
    assert name == "Alice"
    assert score == pytest.approx(1.0)


def test_returns_default_when_below_threshold():
    conn = make_mock_conn(fetchall_results=[[("Alice", "[1.0,0.0]")]])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([0.0, 1.0])})
    name, score = result[0]
    assert name == "DEFAULT"
    assert score is None


def test_picks_best_match_among_multiple_speakers():
    conn = make_mock_conn(fetchall_results=[[("Alice", "[1.0,0.0]"), ("Bob", "[0.0,1.0]")]])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([0.9, 0.1])})
    name, score = result[0]
    assert name == "Alice"
    assert score > 0.7


def test_multiple_clusters_matched_independently():
    conn = make_mock_conn(fetchall_results=[[("Alice", "[1.0,0.0]"), ("Bob", "[0.0,1.0]")]])
    identifier = Identifier()
    result = identifier(conn, {
        "SPEAKER_0": np.array([1.0, 0.0]),
        "SPEAKER_1": np.array([0.0, 1.0]),
    })
    assert result[0][0] == "Alice"
    assert result[1][0] == "Bob"


def test_centroid_averages_multiple_embeddings_per_speaker():
    # Alice has two embeddings; their centroid points toward [1, 0], so [0.9, 0.1] matches her
    conn = make_mock_conn(fetchall_results=[[
        ("Alice", "[1.0,0.0]"),
        ("Alice", "[0.8,0.2]"),
        ("Bob",   "[0.0,1.0]"),
    ]])
    identifier = Identifier()
    result = identifier(conn, {"SPEAKER_0": np.array([0.9, 0.1])})
    assert result[0][0] == "Alice"
