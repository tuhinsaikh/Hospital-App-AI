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
    context: str

# 2. Intent detection node (FREE)
def intent_detection_node(state: AgentState) -> dict:
    """Detects the user's intent using simple rule-based keywords (100% free) instead of an LLM."""
    last_message = state["messages"][-1].content.lower()
    
    # Keyword-based routing rules
    nav_keywords = ["where", "location", "floor", "room", "find", "get to", "navigate", "directions"]
    emergency_keywords = ["emergency", "help", "heart attack", "bleeding", "collapse", "urgent"]
    booking_keywords = ["book", "appointment", "schedule", "reserve"]
    
    if any(word in last_message for word in nav_keywords):
        intent = "NAVIGATION"
    elif any(word in last_message for word in emergency_keywords):
        intent = "EMERGENCY"
    elif any(word in last_message for word in booking_keywords):
        intent = "BOOKING"
    else:
        intent = "OTHER"
        
    return {"intent": intent}

# 3. RAG retrieval node
def rag_retrieval_node(state: AgentState) -> dict:
    """Retrieves context from Qdrant if the intent is NAVIGATION or EMERGENCY."""
    intent = state.get("intent")
    
    if intent in ["NAVIGATION", "EMERGENCY"]:
        last_message = state["messages"][-1].content
        context = rag_service.retrieve(last_message)
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
            "You are a helpful hospital navigation assistant. "
            "Use the provided context to answer where something is located. "
            "If the context doesn't contain the answer, politely state that you cannot find it.\n\n"
            f"Context:\n{context}"
        )
    elif intent == "BOOKING":
        system_msg = "You are a hospital assistant. We do not support booking appointments yet."
    else:
        system_msg = "You are a general hospital assistant. Answer nicely and ask for clarification."

    # Construct complete message chain for LLM processing
    messages = [SystemMessage(content=system_msg)] + list(state["messages"])
    response = llm.invoke(messages)
    
    return {"messages": [response]}

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
    
    return workflow.compile()

# Singleton compiled application
hospital_agent_app = create_hospital_agent()
