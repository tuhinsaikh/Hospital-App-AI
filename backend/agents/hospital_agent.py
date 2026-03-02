import operator
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, SystemMessage
from backend.services.rag_service import rag_service

# 1. State definition using TypedDict
class AgentState(TypedDict):
    user_id: str
    messages: Annotated[Sequence[BaseMessage], operator.add]
    intent: str
    search_query: str
    context: str

from typing import TypedDict, Annotated, Sequence, Literal
from pydantic import BaseModel, Field

# Define the expected structured output from the LLM routing
class IntentOutput(BaseModel):
    intent: Literal["NAVIGATION", "EMERGENCY", "BOOKING", "OTHER"] = Field(description="The user's core intent.")
    search_query: str = Field(description="A detailed, standalone search query formulated from the user's message history to search a vector database for locations (e.g., expanding acronyms like 'usg' to 'ultrasound', fixing spelling, and replacing pronouns like 'there' with the actual location). If NA, return empty string.")

# 2. Intent detection node (USING LLM)
def intent_detection_node(state: AgentState) -> dict:
    """Detects the user's intent and formulates a search query using an LLM."""
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
    structured_llm = llm.with_structured_output(IntentOutput)
    
    # Give the LLM all messages (conversation history) so it can resolve "there" or "it"
    messages = state["messages"]
    
    system_prompt = (
        "You are a routing assistant for a hospital.\n"
        "Analyze the user's message history to determine their intent and create a highly descriptive search query for our vector database.\n"
        "INTENT DEFINITIONS:\n"
        "- NAVIGATION: ANY question asking 'where to go', 'find', 'location', or directions to a department.\n"
        "- BOOKING: ONLY if they explicitly want to 'schedule', 'reserve', or 'book an appointment'.\n"
        "- EMERGENCY: Life-threatening situations (bleeding, heart attack, urgent).\n"
        "- OTHER: General questions.\n"
        "Important rules for search_query (ONLY for Navigation/Emergency, else empty):\n"
        "- Expand medical acronyms (e.g., 'usg' -> 'ultrasound Diagnostic Center', 'ecg' -> 'electrocardiogram cardiology').\n"
        "- Fix typos and resolve synonyms: 'patent' or 'see patient' -> 'General Wards, Semi-Private Rooms, Maternity'.\n"
        "- Resolve contextual references. If the user asks 'how do I get there?' and previously asked about the 'Blood Bank', the query must be 'Blood Bank location directions'.\n"
        "- Do not formulate queries like 'where is the x' - formulate them as comma separated keywords 'x location, department, floor'.\n"
    )
    
    # Create a prompt combining instructions and the conversation
    prompt_msgs = [SystemMessage(content=system_prompt)] + list(messages)
    
    try:
        result = structured_llm.invoke(prompt_msgs)
        with open("llm_routing_debug.txt", "a") as f:
            f.write(f"--- LLM ROUTING ---\nMsg: {messages[-1].content}\nIntent: {result.intent}\nQuery: {result.search_query}\n-------------------\n")
        return {"intent": result.intent, "search_query": result.search_query}
    except Exception as e:
        print(f"Error in routing: {e}")
        # Fallback
        return {"intent": "OTHER", "search_query": ""}

# 3. RAG retrieval node
def rag_retrieval_node(state: AgentState) -> dict:
    """Retrieves context from Qdrant if the intent is NAVIGATION or EMERGENCY."""
    intent = state.get("intent")
    
    if intent in ["NAVIGATION", "EMERGENCY"]:
        # Use the highly descriptive LLM-generated search query
        search_query = state.get("search_query", "")
        # Fallback to last message if search_query is somehow empty
        if not search_query:
            search_query = state["messages"][-1].content
            
        context = rag_service.retrieve(search_query)
        return {"context": context}
        
    return {"context": ""}

# 4. Response generation node (USING GROQ API)
def response_generation_node(state: AgentState) -> dict:
    """Generates final response using Groq's high-speed API with Llama 3."""
    # Initialize the Groq LLM (Ensure GROQ_API_KEY is in your .env)
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
    
    intent = state.get("intent")
    context = state.get("context", "")
    
    if intent == "EMERGENCY":
        system_msg = (
            "This is an emergency. First, instruct the user to call 911 immediately. "
            "Then, using the following context, provide the location of the nearest Emergency Room (ER) or relevant department.\n\n"
            f"Context:\n{context}"
        )
    elif intent == "NAVIGATION":
        system_msg = (
            "You are a helpful hospital navigation assistant.\n"
            "CRITICAL INSTRUCTION: You must ONLY use the provided context to answer where something is located.\n"
            "If the provided Context is empty, or if the answer is not explicitly stated in the Context, "
            "you MUST reply ONLY with: 'I am sorry, but I do not have information about that location.'\n"
            "Do NOT guess, do NOT use your pre-trained knowledge, and do NOT make up floor plans.\n\n"
            f"Context:\n{context}"
        )
    elif intent == "BOOKING":
        system_msg = (
            "You are a hospital assistant. We do not support booking appointments yet.\n"
            "CRITICAL: Do NOT try to give directions, do NOT invent locations, and do NOT provide any floor numbers."
        )
    else:
        system_msg = "You are a general hospital assistant. Answer nicely and ask for clarification."

    # Construct complete message chain for LLM processing
    messages = [SystemMessage(content=system_msg)] + list(state["messages"])
    response = llm.invoke(messages)
    
    return {"messages": [response]}

from langgraph.checkpoint.memory import MemorySaver

# 5. Define Graph
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

# Singleton compiled application
hospital_agent_app = create_hospital_agent()
