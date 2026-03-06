import operator
from typing import TypedDict, Annotated, Sequence, Literal
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from langgraph.checkpoint.memory import MemorySaver
import os

# 1. State definition
class AgentState(TypedDict):
    user_id: str
    messages: Annotated[Sequence[BaseMessage], operator.add]
    intent: str
    search_query: str
    context: str

# 2. Structured output for LLM routing
class IntentOutput(BaseModel):
    intent: Literal["NAVIGATION", "EMERGENCY", "BOOKING", "OTHER"] = Field(
        description="The user's core intent."
    )
    search_query: str = Field(
        description=(
            "A detailed, standalone search query for the vector database. "
            "Expand acronyms (e.g. 'usg' -> 'ultrasound'), fix typos, resolve pronouns. "
            "Empty string if intent is BOOKING or OTHER."
        )
    )

def _get_llm(temperature: float = 0):
    """Factory: returns configured LLM from env vars."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "local":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        return ChatOllama(base_url=base_url, model=model, temperature=temperature)
    return ChatGroq(model="llama-3.1-8b-instant", temperature=temperature)

# 3. Intent detection node
def intent_detection_node(state: AgentState) -> dict:
    """Detects intent and formulates a vector DB search query."""
    llm = _get_llm(temperature=0)
    structured_llm = llm.with_structured_output(IntentOutput)

    system_prompt = (
        "You are a routing assistant for a hospital.\n"
        "Analyze the user's message history to determine their intent and create a descriptive search query.\n"
        "INTENT DEFINITIONS:\n"
        "- NAVIGATION: Questions about 'where to go', 'find', 'location', or directions.\n"
        "- BOOKING: Only if they explicitly want to 'schedule', 'reserve', or 'book an appointment'.\n"
        "- EMERGENCY: Life-threatening situations (bleeding, heart attack, urgent).\n"
        "- OTHER: General questions.\n"
        "For search_query (NAVIGATION/EMERGENCY only):\n"
        "- Expand medical acronyms (e.g. 'usg' -> 'ultrasound Diagnostic Center').\n"
        "- Fix typos and resolve synonyms.\n"
        "- Resolve contextual references from conversation history.\n"
        "- Format as comma-separated keywords, not a question.\n"
    )

    prompt_msgs = [SystemMessage(content=system_prompt)] + list(state["messages"])
    try:
        result = structured_llm.invoke(prompt_msgs)
        return {"intent": result.intent, "search_query": result.search_query}
    except Exception as e:
        print(f"[AgentError] Routing failed: {e}")
        return {"intent": "OTHER", "search_query": ""}

# 4. RAG retrieval node
def rag_retrieval_node(state: AgentState) -> dict:
    """Retrieves context from pgvector for NAVIGATION and EMERGENCY intents."""
    # Import here to avoid circular imports at module level
    from app.services.rag_service import rag_service

    intent = state.get("intent")
    if intent in ["NAVIGATION", "EMERGENCY"]:
        search_query = state.get("search_query") or state["messages"][-1].content
        context = rag_service.retrieve(search_query)
        return {"context": context}
    return {"context": ""}

# 5. Response generation node
def response_generation_node(state: AgentState) -> dict:
    """Generates final response using the configured LLM."""
    llm = _get_llm(temperature=0)
    intent = state.get("intent")
    context = state.get("context", "")

    if intent == "EMERGENCY":
        system_msg = (
            "This is an emergency. First, instruct the user to call emergency services immediately. "
            f"Then, using ONLY the following context, provide the nearest Emergency Room location.\n\nContext:\n{context}"
        )
    elif intent == "NAVIGATION":
        system_msg = (
            "You are a helpful hospital navigation assistant.\n"
            "CRITICAL: Use ONLY the provided context for location answers.\n"
            "If context is empty or does not contain the answer, reply ONLY with: "
            "'I am sorry, but I do not have information about that location.'\n"
            "Do NOT guess or use pre-trained knowledge.\n\n"
            f"Context:\n{context}"
        )
    elif intent == "BOOKING":
        system_msg = (
            "You are a hospital assistant. Appointment booking is not yet supported. "
            "Do NOT give directions or invent locations."
        )
    else:
        system_msg = "You are a general hospital assistant. Answer helpfully and ask for clarification when needed."

    messages = [SystemMessage(content=system_msg)] + list(state["messages"])
    response = llm.invoke(messages)
    return {"messages": [response]}

# 6. Build and compile the graph
def create_hospital_agent():
    workflow = StateGraph(AgentState)
    workflow.add_node("detect_intent", intent_detection_node)
    workflow.add_node("retrieve_context", rag_retrieval_node)
    workflow.add_node("generate_response", response_generation_node)
    workflow.set_entry_point("detect_intent")
    workflow.add_edge("detect_intent", "retrieve_context")
    workflow.add_edge("retrieve_context", "generate_response")
    workflow.add_edge("generate_response", END)
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

# Singleton
hospital_agent_app = create_hospital_agent()
