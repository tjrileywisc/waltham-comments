import { useState } from "react";
import { Link } from "react-router-dom";

type SearchResult = {
    video_id: number,
    start: number,
    meeting_name: string,
    text: string,
};

function Search() {

    const [query, setQuery] = useState("");
    const [results, setResults] = useState<SearchResult[]>([]);
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async (e: any) => {
        e.preventDefault();

        if (!query.trim()) return;

        setLoading(true);
        setError(null);

        try {
            const response = await fetch(`/api/search?query=${encodeURIComponent(query)}`);
            if (!response.ok) throw new Error("Search failed");
            const data = await response.json();
            setResults(data);
        } catch (err) {
            setError(`Something went wrong (${err}). Please try again.`);
        } finally {
            setLoading(false);
        }
    };

    const formatTimeStamp = (seconds: number): string => {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, "0")}`;
    };

    return (
        <div className="search-page">
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
                {results.map((result, i:number) => (
                    <li key={i} className="search-result">
                        <Link to={`/videos?video=${result.video_id}&t=${Math.max(0, result.start - 5).toFixed(1)}`}>
                            {result.meeting_name} @ {formatTimeStamp(result.start)}
                        </Link>
                        <p className="snippet">{result.text}</p>
                    </li>
                ))}
            </ul>
        </div>
    );
}

export default Search;
