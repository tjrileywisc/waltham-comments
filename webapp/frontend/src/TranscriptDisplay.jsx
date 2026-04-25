import { useEffect, useState } from "react";

function TranscriptDisplay({ videoId, currentTime }) {
  const [segments, setSegments] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (videoId == null) return;

    async function loadTranscript() {
      try {
        const res = await fetch(`/api/transcript/${videoId}`);
        if(!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        setSegments(data);
      } catch (err) {
        setError(err.message);
      }
    }

    loadTranscript();
  }, [videoId]);

  if (error) return <p>Error loading transcript</p>;
  if (!segments.length) return null;

  const active = segments.find(
    seg => currentTime >= seg.start && currentTime <= seg.end
  );

  const speaker = active ? active.speaker : "----";
  const text = active ? active.text : "----";

  return (
    <div className="transcript-line">
      <strong>{speaker}</strong>: {text}
    </div>
  );
}

export default TranscriptDisplay;
