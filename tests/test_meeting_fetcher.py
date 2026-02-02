
import pytest

from lib.download import MeetingDownloader
from lib.publicmeeting import PublicMeeting

def test_wont_redownload_existing_meeting(mocker):
    
    MOCK_VIDEO_ID = "12345"
    MOCK_MEETING_NAME = "Test Meeting"

    mock_response = mocker.Mock()
    mock_response.content = f"""
    <div class="summary">
        <a href="/media/{MOCK_VIDEO_ID}"></a>
        <p>{MOCK_MEETING_NAME}</p>
    </div>
    """
    
    mocker.patch('lib.download.requests.Session.get', return_value=mock_response)
    mocker.patch('lib.publicmeeting.PublicMeeting.meeting_exists', return_value=True)

    downloader = MeetingDownloader()
    meetings = downloader.get_new_public_meetings(["City Council"])

    assert len(meetings) == 0

    PublicMeeting.meeting_exists.assert_called_once_with(MOCK_MEETING_NAME) # type: ignore