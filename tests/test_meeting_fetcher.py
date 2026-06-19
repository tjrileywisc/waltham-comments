
import yaml

from downloader import MeetingDownloader
from publicmeeting import PublicMeeting


def _empty_response(mocker):
    mock = mocker.Mock()
    mock.content = b"<div></div>"
    return mock

def test_wont_redownload_existing_meeting(mocker):
    
    MOCK_VIDEO_ID = "12345"
    MOCK_MEETING_NAME = "Test Meeting 2-01-01"

    mock_response = mocker.Mock()
    mock_response.content = f"""
    <div class="summary">
        <a href="/media/{MOCK_VIDEO_ID}"></a>
        <p>{MOCK_MEETING_NAME}</p>
    </div>
    """
    
    mocker.patch('downloader.requests.Session.get', return_value=mock_response)
    mocker.patch('publicmeeting.PublicMeeting.meeting_exists', return_value=True)

    downloader = MeetingDownloader()
    meetings = downloader.get_new_public_meetings(["City Council"])

    assert len(meetings) == 0

    PublicMeeting.meeting_exists.assert_called_once_with(MOCK_MEETING_NAME) # type: ignore
    
def test_wont_download_nodate_meetings(mocker):

    MOCK_VIDEO_ID = "12345"
    
    for meeting_name, result in [
        ["test meeting", 0],
        ["test meeting 2-2-02", 1],
        ["test meeting 2-2-02 a", 0],
        ["test meeting 2-2-02 Part 1", 1],
        ["2-2-02", 0]
    ]:

        mock_response = mocker.Mock()
        mock_response.content = f"""
        <div class="summary">
            <a href="/media/{MOCK_VIDEO_ID}"></a>
            <p>{meeting_name}</p>
        </div>
        """
        
        mocker.patch('downloader.requests.Session.get', return_value=mock_response)
        mocker.patch('publicmeeting.PublicMeeting.meeting_exists', return_value=False)

        downloader = MeetingDownloader()
        meetings = downloader.get_new_public_meetings(["City Council"])

        assert len(meetings) == result

        PublicMeeting.meeting_exists.assert_called_once_with(meeting_name) # type: ignore


def test_filters_to_specified_playlists(mocker):
    mock_get = mocker.patch("downloader.requests.Session.get", return_value=_empty_response(mocker))
    mocker.patch("publicmeeting.PublicMeeting.meeting_exists", return_value=False)
    mocker.patch("downloader.time.sleep")

    downloader = MeetingDownloader()
    downloader.get_new_public_meetings(["City Council"])

    assert mock_get.call_count == 1
    assert "5499" in mock_get.call_args.args[0]


def test_queries_all_playlists_when_no_filter(mocker):
    mock_get = mocker.patch("downloader.requests.Session.get", return_value=_empty_response(mocker))
    mocker.patch("publicmeeting.PublicMeeting.meeting_exists", return_value=False)
    mocker.patch("downloader.time.sleep")

    with open("settings.yaml") as f:
        expected_count = len(yaml.safe_load(f)["playlists"])

    downloader = MeetingDownloader()
    downloader.get_new_public_meetings(None)

    assert mock_get.call_count == expected_count


def test_unknown_playlist_name_skipped(mocker):
    mock_get = mocker.patch("downloader.requests.Session.get", return_value=_empty_response(mocker))
    mocker.patch("downloader.time.sleep")

    downloader = MeetingDownloader()
    meetings = downloader.get_new_public_meetings(["Not A Real Playlist"])

    assert meetings == []
    mock_get.assert_not_called()