import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import VideoPlayer from "./VideoPlayer";

type Utterance = {
  id: number;
  start: number;
  end: number;
  text: string;
  confidence: number | null;
};

type Cluster = {
  embedding_id: number;
  diarization_speaker: string;
  speaker_name: string | null;
  is_canonical: boolean;
  utterances: Utterance[];
};

type KnownSpeaker = { id: number; speaker_name: string };

function formatTime(s: number) {
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function AdminLabel() {
  const { id } = useParams<{ id: string }>();
  const meetingId = Number(id);

  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [selected, setSelected] = useState<Cluster | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [knownSpeakers, setKnownSpeakers] = useState<KnownSpeaker[]>([]);
  const [seekTo, setSeekTo] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState<string | null>(null);

  function loadClusters() {
    fetch(`/admin/meetings/${meetingId}/clusters`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((data: Cluster[]) => {
        setClusters(data);
        setSelected((prev) => {
          const updated = data.find((c) => c.diarization_speaker === prev?.diarization_speaker);
          return updated ?? (data[0] ?? null);
        });
      })
      .catch((e: Error) => setError(e.message));
  }

  function loadSpeakers() {
    fetch("/admin/speakers")
      .then((r) => r.json())
      .then(setKnownSpeakers)
      .catch(() => {});
  }

  useEffect(() => {
    loadClusters();
    loadSpeakers();
  }, [meetingId]);

  useEffect(() => {
    if (selected) setNameInput(selected.speaker_name ?? "");
  }, [selected?.diarization_speaker]);

  function submitLabel() {
    if (!selected || !nameInput.trim()) return;
    fetch(`/admin/meetings/${meetingId}/clusters/${selected.diarization_speaker}/label`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speaker_name: nameInput.trim() }),
    })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); })
      .then(() => { loadClusters(); loadSpeakers(); })
      .catch((e: Error) => setError(e.message));
  }

  function markCanonical(embeddingId: number) {
    fetch(`/admin/speaker-embeddings/${embeddingId}/canonical`, { method: "POST" })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); })
      .then(loadClusters)
      .catch((e: Error) => setError(e.message));
  }

  if (error) return <p>Error: {error}</p>;

  return (
    <div style={{ display: "flex", gap: "16px" }}>
      {/* Left: cluster list */}
      <div style={{ width: "200px", overflowY: "auto", maxHeight: "700px", flexShrink: 0 }}>
        <h2 style={{ fontSize: "1rem" }}>Clusters</h2>
        {clusters.map((c) => (
          <div
            key={c.diarization_speaker}
            onClick={() => setSelected(c)}
            style={{
              padding: "6px 8px",
              cursor: "pointer",
              background: selected?.diarization_speaker === c.diarization_speaker ? "#e8e8e8" : undefined,
              borderBottom: "1px solid #eee",
            }}
          >
            <div style={{ fontWeight: "bold", fontSize: "0.85rem" }}>{c.diarization_speaker}</div>
            <div style={{ fontSize: "0.8rem", color: c.speaker_name ? "#333" : "#999" }}>
              {c.speaker_name ?? "Unlabeled"}
            </div>
            {c.is_canonical && <div style={{ fontSize: "0.7rem", color: "#888" }}>★ canonical</div>}
          </div>
        ))}
      </div>

      {/* Right: cluster detail */}
      <div style={{ flex: 1 }}>
        {selected && (
          <>
            <div style={{ marginBottom: "8px", display: "flex", gap: "8px", alignItems: "center" }}>
              <input
                list="speaker-names"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submitLabel()}
                placeholder="Speaker name"
                style={{ padding: "4px 8px" }}
              />
              <datalist id="speaker-names">
                {knownSpeakers.map((s) => (
                  <option key={s.id} value={s.speaker_name} />
                ))}
              </datalist>
              <button onClick={submitLabel}>Assign</button>
            </div>

            <VideoPlayer
              videoId={meetingId}
              onTimeUpdate={setCurrentTime}
              seekTo={seekTo}
            />

            <div style={{ overflowY: "auto", maxHeight: "250px", marginTop: "8px" }}>
              <table style={{ tableLayout: "fixed", width: "100%", fontSize: "0.85rem" }}>
                <tbody>
                  {selected.utterances.map((u) => (
                    <tr
                      key={u.id}
                      onClick={() => setSeekTo(u.start)}
                      style={{ cursor: "pointer" }}
                    >
                      <td style={{ width: "45px" }}>{formatTime(u.start)}</td>
                      <td
                        style={{
                          width: "42px",
                          color: u.confidence !== null && u.confidence < 0.7 ? "red" : undefined,
                        }}
                      >
                        {u.confidence !== null ? u.confidence.toFixed(2) : "—"}
                      </td>
                      <td>{u.text}</td>
                      <td style={{ width: "28px" }}>
                        <button
                          title="Mark embedding as canonical"
                          onClick={(e) => {
                            e.stopPropagation();
                            markCanonical(selected.embedding_id);
                          }}
                        >
                          ☆
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default AdminLabel;
