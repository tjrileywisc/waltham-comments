import os
import requests

from lib.search import do_search, UtteranceResult

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

SYSTEM_PROMPT = (
    "You are an assistant that answers questions about Waltham, MA city council meetings. "
    "Answer using ONLY the provided context from meeting transcripts. "
    "Always cite the speaker's name and meeting name when referencing information. "
    "If the provided context does not contain relevant information, say so clearly rather than speculating."
)

type ChatMessage = dict[str, str]
type ChatResult = dict[str, str | list[UtteranceResult]]


def build_context_message(utterances: list[UtteranceResult]) -> str:
    """Format retrieved utterances as a context block for the LLM."""
    if not utterances:
        return "No relevant context found in the meeting transcripts."
    lines = []
    for u in utterances:
        minutes = int(u["start"] // 60)
        seconds = int(u["start"] % 60)
        lines.append(f"[{u['speaker_name']}, {u['meeting_name']}, {minutes}:{seconds:02d}] {u['text']}")
    return "Context from meeting transcripts:\n\n" + "\n".join(lines)


def chat(query: str, messages: list[ChatMessage]) -> ChatResult:
    """Run the RAG pipeline: retrieve context, build prompt, call Ollama, return answer + sources."""
    utterances = do_search(query)

    ollama_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_context_message(utterances)},
        *messages,
        {"role": "user", "content": query},
    ]

    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": OLLAMA_MODEL, "messages": ollama_messages, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()

    answer = resp.json()["message"]["content"]
    return {"answer": answer, "utterances": utterances}
