
import { useState } from "react";

function Search() {

    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleSearch = async (e) => {
        e.preventDefault();

        // query is empty
        if (!query.trim()) return;

        setLoading(true);
        setError(null);

        try {
            const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
            if (!response.ok) throw new Error("Search failed");
            const data = await response.json();
            setResults(data);
        } catch (err) {
            setError("Something went wrong. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const formatTimeStamp = (seconds) => {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, "0")}`;
    };

    return (
        <div className="search-container">
            <form onSubmit={handleSearch} className="search-form">
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Enter search text"
                    className="search-input"
                />
                <button type="submit" disabled={loading} className="search-button">
                    {loading ? "Searching..." : "Search"}
                </button>
            </form>

            {error && <p className="search-error">{error}</p>}

            <ul className="search-results">
                {results.map((result, i) => (
                    <li key={i} className="search-result">
                        <a href={`/api/video/${result.video_id}`}>{result.video_title}</a>
                        <span className="timestamp">@ {formatTimeStamp(result.start)}</span>
                        <p className="snippet">{result.text}</p>
                    </li>
                ))}
            </ul>
        </div>
    );
}

export default Search;