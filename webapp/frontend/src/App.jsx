
import { useState } from "react";

import VideoPlayer from "./VideoPlayer";
import VideoList from "./VideoList";
import TranscriptDisplay from "./TranscriptDisplay";

import "./styles.css";

function App() {

  const [videoId, setVideoId] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);

  return (
    <div className="main-container">
      <div className="app-container">

        <div className="left-pane">
          <VideoPlayer videoId={videoId} onTimeUpdate={setCurrentTime} />
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