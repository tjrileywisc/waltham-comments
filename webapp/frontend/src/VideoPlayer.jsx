import { useEffect, useRef } from "react";

function VideoPlayer({ videoId, onTimeUpdate }) {
  const videoRef = useRef(null);

  useEffect(() => {
    if (videoId && videoRef.current) {
      videoRef.current.load();
      videoRef.current.play();
    }
  }, [videoId]);

  if (videoId == null) {
    return <p>Select a video to play</p>;
  }

  const videoSrc = `/api/video/${videoId}`;

  return (
    <video
      ref={videoRef}
      controls
      width="800"
      height="800"
      onTimeUpdate={() => {
        onTimeUpdate(videoRef.current.currentTime);
      }}
    >
      <source src={videoSrc} type="video/mp4" />
    </video>
  );
}

export default VideoPlayer;
