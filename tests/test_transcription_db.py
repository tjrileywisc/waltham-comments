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
