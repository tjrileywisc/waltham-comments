
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import VideoPlayer from "./VideoPlayer";
import VideoList from "./VideoList";
import TranscriptDisplay from "./TranscriptDisplay";

import "./styles.css";

function App() {
  const [searchParams] = useSearchParams();
  const initialVideoId = searchParams.get("video") != null ? parseInt(searchParams.get("video")) : null;
  const startTime = searchParams.get("t") != null ? parseFloat(searchParams.get("t")) : 0;

  const [videoId, setVideoId] = useState(initialVideoId);
  const [currentTime, setCurrentTime] = useState(0);

  return (
    <div className="main-container">
      <div className="app-container">

        <div className="left-pane">
          <VideoPlayer videoId={videoId} startTime={startTime} onTimeUpdate={setCurrentTime} />
          <TranscriptDisplay videoId={videoId} currentTime={currentTime} />
        </div>

        <div className="right-pane">
          <VideoList onSelectVideo={setVideoId} />
        </div>
      </div>
    </div>
  );
}

export default App;