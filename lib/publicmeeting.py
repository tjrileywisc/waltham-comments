
import os

class PublicMeeting:
    """
    A meeting with filename and playlist id
    """

    def __init__(self, video_id: str, name: str, playlist_id: str):
        self.video_id = video_id
        self.name = name
        self.filename = "{}.mp4".format(name.replace(" ", "_"))
        self.playlist_id = playlist_id
        self.filesize = 0
    
    @staticmethod
    def meeting_exists(meeting_name: str) -> bool:
        """Check if meeting has already been downloaded

        Args:
            meeting_name (str): The name of the meeting to check.

        Returns:
            bool: True if the meeting has already been downloaded, False otherwise.
        """

        output_file = f"videos/{meeting_name}.mp4"
        return os.path.exists(output_file)

    def delete_video(self):
        if PublicMeeting.meeting_exists(self.name):
            os.remove(self.filename)
