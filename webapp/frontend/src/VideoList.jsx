
import { useEffect, useState } from "react";

function VideoList({ onSelectVideo }) {
    const [videos, setVideos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

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
                    setError(err.message);
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
      <table border="1" cellPadding="8">
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