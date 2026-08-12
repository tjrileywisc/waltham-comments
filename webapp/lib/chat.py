import os
import json

from monitoring import setup_logging
from lib.search import UtteranceResult
from lib.tools import get_schemas, execute_meetings_sql, video_ids_tool, vector_search_tool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware, ToolCallLimitMiddleware, ToolErrorMiddleware, ToolRetryMiddleware, ToolCallRequest
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage

logger = setup_logging("webapp")

OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "gemma4:12b")
NUM_CTX: int = 16384

SYSTEM_PROMPT = (
    """
    You are an assistant that answers questions about Waltham, MA city council meetings.
    You are also a GIS expert.
    You have access to a read-only accounts in a postgres database containing meeting data, and 
    a postgis database containing relevant GIS data for the city.
        
    You will be limited to 20 back and forth tool calls, and thinking cycles (when you hit the limit, you will be
    told to wrap it up with what you have). When running the 'execute_*_sql' functions, be sure you limit utterance or GIS results
    to 50 records or less.
    
    If you need to produce a link to a video timestamp, use this format:
    [MEETING @ MM:SS](/videos?video=VIDEO_ID&t=START_SECONDS)
    
    If you need to output data from GIS, use human-readable JSON objects.

    Produce output in markdown format.

    For meetings data only:
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

def on_tool_error(exc: Exception, request: ToolCallRequest) -> str | None:
    """Handle errors during tool calls"""
    return f"`{request.tool_call['name']}` failed: {type(exc).__name__}. Fix the input and retry."

async def run_chat(query: str, prev_messages: list) -> ChatResult:
    """Run the RAG pipeline: retrieve context, build prompt, call Ollama, return answer + sources."""
    
    TOOL_LIMIT = 20
    UTTERANCE_TOOLS = [
        execute_meetings_sql.name,
        vector_search_tool().name
    ]
    
    async with streamable_http_client(f"http://{os.environ['POSTGIS_MCP']}") as (read, write, _):
        async with ClientSession(read, write) as session:
    
            await session.initialize()
            tools = await load_mcp_tools(session)
            tools.extend([
                execute_meetings_sql, vector_search_tool(),
                get_schemas, video_ids_tool()
            ])

            model = ChatOllama(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_URL,
                num_ctx=NUM_CTX,
                temperature=1.0,
                top_p=0.95,
                top_k=64
            )

            # ref. https://github.com/langchain-ai/langchain/issues/33732)
            
            agent = create_agent(# pyright: ignore[reportCallIssue]
                model=model,
                tools=tools,
                middleware=[
                    ToolRetryMiddleware(max_retries=3, on_failure="error"),
                    ToolErrorMiddleware(on_error=on_tool_error),
                    SummarizationMiddleware(
                        model=model,
                        trigger=("tokens", int(0.8 * NUM_CTX))
                    ),
                    ToolCallLimitMiddleware(run_limit=TOOL_LIMIT) # pyright: ignore[reportArgumentType]
                ]
            )

            messages = [
                SystemMessage(SYSTEM_PROMPT),
                *prev_messages,
                HumanMessage(query),
            ]

            result = await agent.ainvoke(
                {"messages": messages}
            )
            
            # look for utterances
            utterances = []
            _utterance_keys = {"text", "speaker_name", "meeting_name", "start_time"}
            for message in result["messages"]:
                if isinstance(message, ToolMessage) and message.name in UTTERANCE_TOOLS and message.artifact:
                    rows = message.artifact
                    if rows and isinstance(rows[0], dict) and _utterance_keys.issubset(rows[0].keys()):
                        utterances.extend(rows)
                    
            # use last AIMesage as result
            ai_messages = [message for message in result["messages"][::-1] if isinstance(message, AIMessage)]
            
            text_blocks = [b["text"] for b in ai_messages[0].content_blocks if b["type"] == "text"]
            answer = text_blocks[0] if text_blocks else ""

            if answer.startswith("[NO_CONTEXT]"):
                answer = answer[len("[NO_CONTEXT]"):].lstrip()
                utterances = []

            return {"answer": answer, "utterances": utterances}

