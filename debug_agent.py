import uuid
from dotenv import load_dotenv
from pathlib import Path

# Load env variables so it can connect to DB and Groq
dotenv_path = Path(__file__).parent / "backend" / ".env"
load_dotenv(dotenv_path=dotenv_path)

from langchain_core.messages import HumanMessage
from backend.agents.hospital_agent import hospital_agent_app

def run_debug_chat(message: str, user_id: str):
    print(f"\n{'='*50}")
    print(f"DEBUGGING SESSION START")
    print(f"User ID: {user_id}")
    print(f"Message: {message}")
    print(f"{'='*50}\n")

    initial_state = {
        "user_id": user_id,
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "search_query": "",
        "context": ""
    }
    
    config = {"configurable": {"thread_id": user_id}}
    
    # Stream the graph execution step by step
    print("Graph Execution Steps:")
    for step_event in hospital_agent_app.stream(initial_state, config=config):
        for node_name, node_state in step_event.items():
            print(f"\n--- Node Executed: [{node_name}] ---")
            
            if "intent" in node_state:
                print(f"Detected Intent: {node_state['intent']}")
            if "search_query" in node_state:
                print(f"Search Query formulated for DB: '{node_state['search_query']}'")
            if "context" in node_state:
                print(f"Context Retrieved from DB:\n{node_state['context']}")
            if "messages" in node_state:
                last_msg = node_state["messages"][-1].content
                print(f"LLM Response Generated:\n{last_msg}")
                
    print(f"\n{'='*50}")
    print(f"DEBUGGING SESSION END")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    # Create a unique random session ID for this debug run
    session_id = str(uuid.uuid4())
    
    print("Welcome to the Hospital Agent Debugger!")
    print("Type your message below. Type 'exit' or 'quit' to stop.\n")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            break
            
        run_debug_chat(user_input, session_id)
