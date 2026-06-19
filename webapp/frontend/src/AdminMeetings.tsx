import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type Meeting = {
  id: number;
  meeting_name: string;
  meeting_date: string;
  meeting_type: string;
  unlabeled_count: number;
  video_id: number | null;
};

/**
 * Meeting level view of currently unlabeled speakers in meetings
 * @returns 
 */
function AdminMeetings() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/admin/meetings")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setMeetings)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p>Error: {error}</p>;

  return (
    <div>
      <h1>Speaker Labeling</h1>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Name</th>
            <th>Type</th>
            <th>Unlabeled clusters</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {meetings.map((m) => (
            <tr key={m.id}>
              <td>{m.meeting_date}</td>
              <td>{m.meeting_name}</td>
              <td>{m.meeting_type}</td>
              <td>{m.unlabeled_count > 0 ? m.unlabeled_count : "—"}</td>
              <td>
                <Link to={`/admin/meetings/${m.id}/label`}>Label</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default AdminMeetings;
