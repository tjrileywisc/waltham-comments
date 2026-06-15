import { useEffect, useRef } from "react";

type VideoPlayerProps = {
  videoId: number | null,
  startTime?: number,
  onTimeUpdate: (time: number) => void,
  seekTo: number | null
};

function VideoPlayer({ videoId, startTime = 0, onTimeUpdate, seekTo } : VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoId && videoRef.current) {
      videoRef.current.load();
    }
  }, [videoId]);

  useEffect(() => {
    if (seekTo != null && videoRef.current) {
      videoRef.current.currentTime = seekTo;
    }
  }, [seekTo]);

  if (videoId == null) {
    return <p>Select a video to play</p>;
  }

  const handleLoadedMetadata = () => {
    if (startTime > 0 && videoRef.current) {
      videoRef.current.currentTime = startTime;
    }
    videoRef.current?.play();
  };

  return (
    <video
      ref={videoRef}
      controls
      width="800"
      height="800"
      onLoadedMetadata={handleLoadedMetadata}
      onTimeUpdate={() => videoRef.current && onTimeUpdate(videoRef.current.currentTime)}
    >
      <source src={`/api/video/${videoId}`} type="video/mp4" />
    </video>
  );
}

export default VideoPlayer;
