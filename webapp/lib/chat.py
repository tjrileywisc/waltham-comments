import os
from monitoring import setup_logging
import json
from lib.search import UtteranceResult
from lib.tools import get_schemas, execute_sql, get_video_ids
from ollama import ChatResponse, Client, Message

logger = setup_logging("webapp")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:12b")

SYSTEM_PROMPT = (
    """
    You are an assistant that answers questions about Waltham, MA city council meetings.
    You have access to a read-only account in a postgres database and a
    `execute_sql` function tool to write your own queries. The relevant table schemas are provided to you.
    You will be limited to 10 back and forth tool calls. When running the 'execute_sql' function, be sure you limit utterance results
    to 50 or less.
    
    If you need to produce a link to a video timestamp, use this format:
    [MEETING @ MM:SS](/videos?video=VIDEO_ID&t=START_SECONDS)
    
    There is a `get_video_ids` tool that returns a map of the meeting name to a video id.
    
    Produce output in markdown format.

    Answer using ONLY the provided context from meeting transcripts.
    Strongly prefer to provide example utterances with the speaker's name and meeting name when referencing information.
    If the provided context does not contain relevant information to answer the question,
    begin your response with the exact token [NO_CONTEXT] and then briefly say you couldn't find anything relevant.
    Otherwise, do NOT include [NO_CONTEXT] in your response.
    """
)

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


def run_chat(query: str, prev_messages: list[Message]) -> ChatResult:
    """Run the RAG pipeline: retrieve context, build prompt, call Ollama, return answer + sources."""
    
    client = Client(OLLAMA_URL)
    
    available_functions = {
        execute_sql.__name__: execute_sql,
        get_video_ids.__name__: get_video_ids
    }

    schema = get_schemas()
    system_content = SYSTEM_PROMPT + f"\n\nDatabase schema:\n{schema}"

    ollama_messages = [
        {"role": "system", "content": system_content},
        *prev_messages,
        {"role": "user", "content": query},
    ]
    
    TOOL_LIMIT = 10
    answer = None
    utterances: list[UtteranceResult] = []
    _utterance_keys = {"text", "speaker_name", "meeting_name", "start_time"}

    while TOOL_LIMIT > 0:
        response: ChatResponse = client.chat(
            model=OLLAMA_MODEL,
            messages=ollama_messages,
            tools=[execute_sql],
        )

        ollama_messages.append(response.message)

        failed_call = False
        if response.message.tool_calls:
            for tc in response.message.tool_calls:
                if tc.function.name in available_functions:
                    try:
                        logger.debug(f"Calling {tc.function.name}")
                        result = available_functions[tc.function.name](**tc.function.arguments)
                    except Exception as e:
                        result = f"Error: {e}. Your query was rejected. Please correct it and try again."
                        failed_call = True
                        logger.warning(f"Function call {tc.function.name} failed: {e}")
                    finally:
                        content = json.dumps(result, default=str)[:8000] if isinstance(result, (list, dict)) else str(result)
                        ollama_messages.append({'role': 'tool', 'tool_name': tc.function.name, 'content': content})

                    if failed_call:
                        break

                    if tc.function.name == execute_sql.__name__ and isinstance(result, list):
                        for row in result:
                            if isinstance(row, dict) and _utterance_keys.issubset(row.keys()):
                                utterances.append({**row, "start": row["start_time"]})
            if not failed_call:
                TOOL_LIMIT -= 1
        else:
            answer = response.message.content
            logger.debug(f"Final response message: {response.message}")
            break

    if not answer:
        answer = ""
        utterances = []
    elif answer.startswith("[NO_CONTEXT]"):
        answer = answer[len("[NO_CONTEXT]"):].lstrip()
        utterances = []

    return {"answer": answer, "utterances": utterances}
