# RAG Chat Interface Design

**Date:** 2026-06-26  
**Status:** Approved

## Overview

Replace the current keyword/vector search results list with a multi-turn RAG chat interface. The user types questions in natural language; the system retrieves relevant utterances from meeting transcripts, feeds them as context to a locally hosted LLM, and returns a synthesized answer with citations linking back to the source video timestamps.

---

## Architecture

Five Docker services total. Only `ollama` (new) and `webapp` (modified) change.

| Service | Change |
|---|---|
| `ollama` | New — Ollama server with GPU passthrough, internal port 11434 |
| `webapp` | New `lib/chat.py`, new `POST /api/chat` endpoint, rewritten `Search.tsx` |
| `embeddings-service` | No change |
| `transcription-service` | No change |
| `meeting-downloader` | No change |

Conversation history is held **client-side** in React state and sent with each request. The backend is stateless — no session storage, no DB changes.

---

## compose.yml Changes

Add an `ollama` service with NVIDIA GPU passthrough:

```yaml
ollama:
  image: ollama/ollama
  volumes:
    - ollama_models:/root/.ollama
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

Add `ollama_models` to the top-level `volumes` block. The `webapp` service gets two new env vars: `OLLAMA_URL` (default `http://ollama:11434`) and `OLLAMA_MODEL` (default `qwen2.5:14b`).

The chosen model (`qwen2.5:14b` at 4-bit quantization, ~9GB VRAM) fits comfortably within the 12GB VRAM budget.

---

## API

### `POST /api/chat`

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "What did the council say about the parking garage?"},
    {"role": "assistant", "content": "The council discussed..."}
  ],
  "query": "Did anyone oppose it?"
}
```

`messages` is the prior conversation history (may be empty on first turn). `query` is the new user message. Context retrieval uses only `query`, keeping retrieval focused even across multi-turn conversations.

**Response:**
```json
{
  "answer": "Councilor Smith opposed the parking garage on cost grounds...",
  "sources": [
    {
      "meeting_name": "City Council 2024-03-12",
      "video_id": 3,
      "start": 1842.5,
      "text": "I have serious concerns about the projected cost..."
    }
  ]
}
```

The existing `GET /api/search` endpoint is retained in the backend (used internally by `do_search`) but is no longer called by the frontend.

---

## RAG Pipeline (`webapp/lib/chat.py`)

1. Call `do_search(query)` — returns top-10 utterances via existing hybrid RRF search (exact + vector).
2. Build an Ollama messages array:
   - **System message:** instructs the model to answer questions about Waltham city council meetings using only the provided context, to cite speakers and meeting names, and to say when no relevant context was found rather than speculating.
   - **Context message (user role):** the retrieved utterances, formatted as `[Speaker, Meeting, Timestamp] text` entries.
   - **Conversation history:** the `messages` array from the request, appended after context.
   - **New question:** the `query` appended as the final user message.
3. `POST` to `{OLLAMA_URL}/api/chat` with `stream: false`.
4. Return the model's reply text and the source utterances from step 1.

---

## Frontend (`webapp/frontend/src/Search.tsx`)

`Search.tsx` is rewritten as a chat component. The `/search` route and Navbar link are unchanged.

**Layout:**
- Scrollable message history area (grows upward)
- Each user turn shows the question
- Each assistant turn shows the LLM answer followed by a "Sources" section (expanded by default, collapsible)
- Sources render as clickable links in the same format as current search results: `Meeting Name @ M:SS` linking to `/videos?video={id}&t={start}`
- Input box + Submit button pinned at bottom

**State:**
```ts
type Message = 
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; sources: Source[] };

const [messages, setMessages] = useState<Message[]>([]);
const [input, setInput] = useState("");
const [loading, setLoading] = useState(false);
```

On submit: append the user message to state immediately, call `POST /api/chat` with the existing history and new query, then append the assistant response.

The URL param `?q=` is removed (multi-turn conversation state doesn't map cleanly to a single query string).

---

## Error Handling

| Scenario | Backend | Frontend |
|---|---|---|
| Ollama unreachable | 503 with detail message | "Chat is currently unavailable." |
| No search results found | LLM is still called; system prompt instructs it to say so | Normal display — model states no relevant context |
| Ollama returns error | 502 forwarding Ollama's error | "Something went wrong. Please try again." |

---

## Out of Scope

- Streaming token-by-token responses
- Persisting conversation history across page reloads
- A separate `/chat` route (search page is repurposed)
- Changes to the transcription, downloader, or embeddings services
