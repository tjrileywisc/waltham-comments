from unittest.mock import MagicMock


def make_mock_conn(fetchall_results=None, fetchone_results=None):
    """
    Returns a mock psycopg connection for `with conn.cursor() as cur:` usage.

    fetchall_results: list where each element is the return value for one fetchall() call
    fetchone_results: list where each element is the return value for one fetchone() call

    Access the mock cursor via conn.cursor.return_value for post-call assertions.
    """
    mock_cur = MagicMock()
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    if fetchall_results is not None:
        mock_cur.fetchall.side_effect = fetchall_results
    if fetchone_results is not None:
        mock_cur.fetchone.side_effect = fetchone_results
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: mock_conn
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur
    return mock_conn
