import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";

type Source = {
    meeting_name: string;
    speaker_name: string;
    video_id: number | null;
    start: number;
    text: string;
};

type UserMessage = { role: "user"; content: string };
type AssistantMessage = { role: "assistant"; content: string; sources: Source[] };
type Message = UserMessage | AssistantMessage;

type ChatHistoryItem = { role: "user" | "assistant"; content: string };

function formatTimestamp(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
}

function SourceList({ sources }: { sources: Source[] }) {
    const [open, setOpen] = useState(true);
    if (sources.length === 0) return null;
    return (
        <div className="sources">
            <button className="sources-toggle" onClick={() => setOpen(o => !o)}>
                Sources ({sources.length}) {open ? "▲" : "▼"}
            </button>
            {open && (
                <ul className="sources-list">
                    {sources.map((s, i) => (
                        <li key={i}>
                            {s.video_id !== null ? (
                                <Link to={`/videos?video=${s.video_id}&t=${Math.max(0, s.start - 5).toFixed(1)}`}>
                                    {s.meeting_name} @ {formatTimestamp(s.start)}
                                </Link>
                            ) : (
                                <span>{s.meeting_name} @ {formatTimestamp(s.start)}</span>
                            )}
                            <p className="snippet">{s.speaker_name}: {s.text}</p>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

function Search() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || loading) return;

        const query = input.trim();
        setInput("");
        setError(null);

        setMessages(prev => [...prev, { role: "user", content: query }]);

        const history: ChatHistoryItem[] = messages.map(m => ({
            role: m.role,
            content: m.content,
        }));

        setLoading(true);
        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ messages: history, query }),
            });
            if (!response.ok) {
                const status = response.status;
                throw new Error(`${status}`);
            }
            const data = await response.json();
            setMessages(prev => [
                ...prev,
                { role: "assistant", content: data.answer, sources: data.sources },
            ]);
        } catch (err) {
            const msg = err instanceof Error ? err.message : "";
            if (msg.includes("503")) {
                setError("Chat is currently unavailable.");
            } else {
                setError("Something went wrong. Please try again.");
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="chat-page">
            <div className="chat-history">
                {messages.map((m, i) => (
                    <div key={i} className={`chat-message chat-message--${m.role}`}>
                        <p className="chat-bubble">{m.content}</p>
                        {m.role === "assistant" && <SourceList sources={m.sources} />}
                    </div>
                ))}
                {loading && (
                    <div className="chat-message chat-message--assistant">
                        <p className="chat-bubble">Thinking…</p>
                    </div>
                )}
                {error && <p className="chat-error">{error}</p>}
                <div ref={bottomRef} />
            </div>
            <form onSubmit={handleSubmit} className="chat-form">
                <input
                    type="text"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    placeholder="Ask about Waltham city council meetings…"
                    className="chat-input"
                    disabled={loading}
                />
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    className="chat-button"
                >
                    Ask
                </button>
            </form>
        </div>
    );
}

export default Search;
