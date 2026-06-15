
import { useEffect, useState } from "react";

type Video = {
  video_id: number,
  name: string,
};

type VideoListProps = {
  onSelectVideo:(video_id: number) => void;
};

function VideoList({ onSelectVideo }: VideoListProps) {
    const [videos, setVideos] = useState<Video[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;

        async function fetchVideos() { 
            try {
                const res = await fetch("./api/videos");
                if(!res.ok) {
                    throw new Error(`HTTP ${res.status}`);
                }

                const data = await res.json();
                if (!cancelled) {
                    setVideos(data)
                }
            } catch (err) {
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : String(err));
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        fetchVideos();

        return () => {
            cancelled = true;
        };
    

    }, []);

    if (loading) return <p>Loading videos...</p>;
    if (error) return <p style={{ color: "red" }}>Error: {error}</p>;

    return (
      <table style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th>Id</th>
            <th>Name</th>
            <th>Path</th>
          </tr>
        </thead>
        <tbody>
          {videos.map((s) => (
            <tr key={s.video_id}>
              <td>{s.video_id}</td>
              <td>{s.name}</td>
              <td>
                <button
                  onClick={() => {
                    onSelectVideo(s.video_id);
                  }}
                >
                  Load video
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
};

export default VideoList;
