# Home Search + Videos Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the two-pane video viewer to `/videos` and make the home page a vertically-centered search box.

**Architecture:** Rename `App.jsx` → `Videos.jsx`, wire `Search.jsx` to the `/` route, add `/videos` route, update navbar and search result links, add centering CSS for the search page.

**Tech Stack:** React 19, React Router DOM, Vite, plain CSS

---

### Task 1: Create `Videos.jsx` from `App.jsx`

**Files:**
- Create: `webapp/frontend/src/Videos.jsx`
- No changes to existing files yet

- [ ] **Step 1: Create `Videos.jsx`**

Create `webapp/frontend/src/Videos.jsx` with this content (identical logic to `App.jsx`, component renamed):

```jsx
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import VideoPlayer from "./VideoPlayer";
import VideoList from "./VideoList";
import TranscriptDisplay from "./TranscriptDisplay";

import "./styles.css";

function Videos() {
  const [searchParams] = useSearchParams();
  const initialVideoId = searchParams.get("video") != null ? parseInt(searchParams.get("video")) : null;
  const startTime = searchParams.get("t") != null ? parseFloat(searchParams.get("t")) : 0;

  const [videoId, setVideoId] = useState(initialVideoId);
  const [seekTo, setSeekTo] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);

  return (
    <div className="main-container">
      <div className="app-container">

        <div className="left-pane">
          <VideoPlayer videoId={videoId} startTime={startTime} onTimeUpdate={setCurrentTime} seekTo={seekTo} />
          <TranscriptDisplay videoId={videoId} currentTime={currentTime} onSeek={setSeekTo} />
        </div>

        <div className="right-pane">
          <VideoList onSelectVideo={setVideoId} />
        </div>
      </div>
    </div>
  );
}

export default Videos;
```

- [ ] **Step 2: Commit**

```bash
git add webapp/frontend/src/Videos.jsx
git commit -m "feat: add Videos page component (extracted from App)"
```

---

### Task 2: Update `index.jsx` routes

**Files:**
- Modify: `webapp/frontend/src/index.jsx`

- [ ] **Step 1: Rewrite `index.jsx`**

Replace the entire file content:

```jsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import "./styles.css";

import Videos from "./Videos";
import Search from "./Search"
import Navbar from "./Navbar";

const root = createRoot(document.getElementById("root"));
root.render(
  <StrictMode>
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<Search />} />
        <Route path="/videos" element={<Videos />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
);
```

- [ ] **Step 2: Commit**

```bash
git add webapp/frontend/src/index.jsx
git commit -m "feat: route / to Search, /videos to Videos"
```

---

### Task 3: Update `Navbar.jsx`

**Files:**
- Modify: `webapp/frontend/src/Navbar.jsx`

- [ ] **Step 1: Replace navbar links**

Replace the entire file content (remove "Search" link, add "Videos" link):

```jsx
import { Link } from 'react-router-dom';

function Navbar() {
    return (
        <nav className="navbar">
            <Link to="/" className="nav-item">Home</Link>
            <Link to="/about" className="nav-item">About</Link>
            <Link to="/videos" className="nav-item">Videos</Link>
        </nav>
    );
}

export default Navbar;
```

- [ ] **Step 2: Commit**

```bash
git add webapp/frontend/src/Navbar.jsx
git commit -m "feat: add Videos nav link, remove Search nav link"
```

---

### Task 4: Update `Search.jsx` — result links and root class

**Files:**
- Modify: `webapp/frontend/src/Search.jsx`

Two changes: result links point to `/videos?...` instead of `/?...`, and the root div uses `search-page` class (which will receive centering CSS in Task 5).

- [ ] **Step 1: Rewrite `Search.jsx`**

Replace the entire file content:

```jsx
import { useState } from "react";
import { Link } from "react-router-dom";

function Search() {

    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleSearch = async (e) => {
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

    const formatTimeStamp = (seconds) => {
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
                {results.map((result, i) => (
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
```

- [ ] **Step 2: Commit**

```bash
git add webapp/frontend/src/Search.jsx
git commit -m "feat: update search result links to /videos, rename root class to search-page"
```

---

### Task 5: Add centering CSS for search page

**Files:**
- Modify: `webapp/frontend/src/styles.css`

- [ ] **Step 1: Append `.search-page` rule to `styles.css`**

Add at the end of `webapp/frontend/src/styles.css`:

```css
.search-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 60px);
}
```

- [ ] **Step 2: Commit**

```bash
git add webapp/frontend/src/styles.css
git commit -m "feat: center search box vertically on home page"
```

---

### Task 6: Build and verify

**Files:** No code changes — build and manual check only.

- [ ] **Step 1: Build the frontend**

```bash
cd webapp/frontend
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 2: Start the app and verify**

```bash
cd ../..
docker compose up --build
```

Check:
1. `http://localhost:8000/` — search box appears centered vertically with no video list visible
2. `http://localhost:8000/videos` — two-pane layout: VideoPlayer + TranscriptDisplay left, VideoList right
3. Navbar shows "Home", "About", "Videos" (no "Search")
4. Run a search on the home page, click a result — navigates to `/videos?video=...&t=...` and loads the correct video at the correct timestamp

- [ ] **Step 3: Delete `App.jsx`** (no longer needed)

```bash
git rm webapp/frontend/src/App.jsx
git commit -m "chore: remove App.jsx replaced by Videos.jsx"
```
