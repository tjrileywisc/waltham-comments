import { useEffect, useState, useRef } from "react";

type TranscriptProps = {
  videoId: number,
  currentTime: number
  onSeek: (time: number) => void
};

interface SpeechSegment {
  id: number,
  start: number,
  end: number,
  text: string,
  speaker: string
};

function TranscriptDisplay({ videoId, currentTime, onSeek }: TranscriptProps) {
  const [segments, setSegments] = useState<Array<SpeechSegment>>([]);
  const [error, setError] = useState<string | null>(null);
  const itemsRef = useRef<(HTMLTableRowElement | null)[]>([])

  // we don't want this active flag between utterances,
  // so check within a window
  const activeIdx = segments.length
    ? segments.findIndex(seg => currentTime >= seg.start && currentTime <= seg.end)
    : -1;

  // load transcript
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
      } catch (err: any) {
        setError(err.message);
      }
    }

    loadTranscript();
  }, [videoId]);

  // scrolling behavior
  useEffect(() => {
    if (activeIdx !== -1) {
      itemsRef.current[activeIdx]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeIdx]);

  if (error) return <p>Error loading transcript</p>;
  if (!segments.length) return null;

  function formatTime(seconds: number): string {
    const m: number = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function loadSegment(segIdx: number) {
    onSeek(segments[segIdx].start);
  }

  return (
    <div style={{ overflowY: 'auto', height: '300px' }}>
      <table style={{ tableLayout: 'fixed' }}>
        <tbody>
          {segments.map((segment, i) => (
            <tr onClick={() => loadSegment(i)} key={i} ref={(el) => (itemsRef.current[i] = el)}
                className={i === activeIdx ? 'active' : ''}>
              <td>{formatTime(segment.start)}</td>
              <td style={{width: '50px' }}>{segment.speaker}</td>
              <td style={{width: '500px' }}>{segment.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default TranscriptDisplay;
