import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type Meeting = {
  id: number;
  meeting_name: string;
  meeting_date: string;
  meeting_type: string;
  unlabeled_count: number;
  video_id: number | null;
  relabel_status: string | null;
};

type SortKey = "meeting_date" | "meeting_name" | "meeting_type" | "unlabeled_count";
type SortDir = "asc" | "desc";

/**
 * Meeting level view of currently unlabeled speakers in meetings
 * @returns
 */
function AdminMeetings() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("meeting_date");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [relabeling, setRelabeling] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/admin/meetings")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setMeetings)
      .catch((e: Error) => setError(e.message));
  }, []);

  /**
   * POST to the relabel endpoint for the given meeting, then update local state.
   * @param meetingId - the meeting to relabel
   */
  async function handleRelabel(meetingId: number) {
    setRelabeling(meetingId);
    try {
      const r = await fetch(`/api/admin/meetings/${meetingId}/relabel`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMeetings((ms) =>
        ms.map((m) => (m.id === meetingId ? { ...m, relabel_status: "pending" } : m))
      );
    } finally {
      setRelabeling(null);
    }
  }

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const sorted = [...meetings].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

  function SortIndicator({ col }: { col: SortKey }) {
    if (col !== sortKey) return null;
    return <span>{sortDir === "asc" ? " ↑" : " ↓"}</span>;
  }

  if (error) return <p>Error: {error}</p>;

  return (
    <div>
      <h1>Speaker Labeling</h1>
      <table>
        <thead>
          <tr>
            <th style={{ cursor: "pointer" }} onClick={() => handleSort("meeting_date")}>
              Date<SortIndicator col="meeting_date" />
            </th>
            <th style={{ cursor: "pointer" }} onClick={() => handleSort("meeting_name")}>
              Name<SortIndicator col="meeting_name" />
            </th>
            <th style={{ cursor: "pointer" }} onClick={() => handleSort("meeting_type")}>
              Type<SortIndicator col="meeting_type" />
            </th>
            <th style={{ cursor: "pointer" }} onClick={() => handleSort("unlabeled_count")}>
              Unlabeled clusters<SortIndicator col="unlabeled_count" />
            </th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((m) => (
            <tr key={m.id}>
              <td>{m.meeting_date}</td>
              <td>{m.meeting_name}</td>
              <td>{m.meeting_type}</td>
              <td>{m.unlabeled_count > 0 ? m.unlabeled_count : "—"}</td>
              <td>
                <Link to={`/admin/meetings/${m.id}/label`}>Label</Link>
                {m.unlabeled_count > 0 && (
                  <>
                    {" "}
                    <button
                      onClick={() => handleRelabel(m.id)}
                      disabled={relabeling === m.id}
                    >
                      {relabeling === m.id ? "Relabeling…" : "Relabel"}
                    </button>
                    {m.relabel_status && <span> ({m.relabel_status})</span>}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default AdminMeetings;
