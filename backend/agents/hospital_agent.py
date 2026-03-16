import operator, os
from typing import TypedDict, Annotated, Sequence, Literal, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from backend.services.rag_service import rag_service


# ── LLM Factory ─────────────────────────────────────────────────────
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

def _get_llm(temperature=0):
    """Factory method to return the configured LLM."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "local":
        base_url = os.getenv("OLLAMA_BASE_URL") or "http://192.168.1.202:11434"
        model = os.getenv("OLLAMA_MODEL") or "llama3.1:8b"
        return ChatOllama(base_url=base_url, model=model, temperature=temperature)
    else:
        return ChatGroq(model="llama-3.1-8b-instant", temperature=temperature)


# ── State Definition ────────────────────────────────────────────────

class AgentState(TypedDict):
    user_id: str
    messages: Annotated[Sequence[BaseMessage], operator.add]
    intent: str
    search_query: str
    context: str
    # Booking-specific fields
    booking_phase: str            # "", "ask_problem", "suggest_doctors", "select_slot", "ask_name", "confirm", "done"
    selected_doctor: dict         # {id, name, specialization, availability, department}
    selected_slot: dict           # {id, slot_date, start_time, end_time}
    patient_name: str
    booking_reason: str


# ── Structured Output Models ────────────────────────────────────────

class IntentOutput(BaseModel):
    intent: Literal["NAVIGATION", "EMERGENCY", "BOOKING", "OTHER"] = Field(
        description="The user's core intent."
    )
    search_query: str = Field(
        default="",
        description=(
            "A detailed, standalone search query for a vector database for locations "
            "(expanding acronyms, fixing spelling, resolving pronouns). "
            "Only for NAVIGATION/EMERGENCY, else empty."
        ),
    )


class BookingExtraction(BaseModel):
    """Extracted booking info from the latest user message."""
    doctor_name: Optional[str] = Field(default=None, description="Doctor name mentioned by user, or None.")
    health_issue: Optional[str] = Field(default=None, description="Health issue or symptom described, or None.")
    slot_number: Optional[int] = Field(default=None, description="Slot number (1-based index) chosen by user, or None.")
    preferred_day: Optional[str] = Field(default=None, description="Day of week mentioned (e.g. 'monday', 'thursday'), or None.")
    preferred_time: Optional[str] = Field(default=None, description="Preferred time mentioned (e.g. '10 am', '2:30 pm', '14:00'), or None.")
    patient_name: Optional[str] = Field(default=None, description="Patient's own name if they provided it, or None.")
    confirmed: Optional[bool] = Field(default=None, description="True if user said yes/confirm, False if no/cancel, None if not applicable.")


# ══════════════════════════════════════════════════════════════════════
#  NODE 1: Intent Detection
# ══════════════════════════════════════════════════════════════════════

def intent_detection_node(state: AgentState) -> dict:
    """Detects intent and formulates a search query using an LLM."""
    llm = _get_llm(temperature=0)
    structured_llm = llm.with_structured_output(IntentOutput)
    messages = state["messages"]

    system_prompt = (
        "You are a routing assistant for a hospital.\n"
        "Analyze the user's message history to determine their intent.\n"
        "INTENT DEFINITIONS:\n"
        "- NAVIGATION: asking 'where to go', 'find', 'location', or directions "
        "to a department. NOT when asking 'which doctor to see'.\n"
        "- BOOKING: wants to 'schedule', 'reserve', 'book an appointment', "
        "OR wants to 'consult a doctor' OR describes a medical problem.\n"
        "- EMERGENCY: life-threatening situations.\n"
        "- OTHER: general questions.\n"
        "Rules for search_query (ONLY for Navigation/Emergency, else empty):\n"
        "- Expand acronyms; fix typos; resolve references.\n"
    )

    prompt_msgs = [SystemMessage(content=system_prompt)] + list(messages)
    try:
        result = structured_llm.invoke(prompt_msgs)
        with open("llm_routing_debug.txt", "a") as f:
            f.write(f"--- LLM ROUTING ---\nMsg: {messages[-1].content}\n"
                    f"Intent: {result.intent}\nQuery: {result.search_query}\n---\n")
        return {"intent": result.intent, "search_query": result.search_query}
    except Exception as e:
        print(f"Error in routing: {e}")
        return {"intent": "OTHER", "search_query": ""}


# ══════════════════════════════════════════════════════════════════════
#  NODE 2: RAG Retrieval
# ══════════════════════════════════════════════════════════════════════

def rag_retrieval_node(state: AgentState) -> dict:
    intent = state.get("intent")
    if intent in ("NAVIGATION", "EMERGENCY"):
        sq = state.get("search_query") or state["messages"][-1].content
        return {"context": rag_service.retrieve(sq)}
    return {"context": ""}


# ══════════════════════════════════════════════════════════════════════
#  NODE 3: Booking Data Extraction  (only runs for BOOKING intent)
# ══════════════════════════════════════════════════════════════════════

def booking_extraction_node(state: AgentState) -> dict:
    """
    Uses the LLM to extract structured booking info from the conversation,
    then uses CODE LOGIC to advance the booking_phase state machine.
    The LLM never gets tools — all decisions are made here in code.
    """
    intent = state.get("intent")
    if intent != "BOOKING":
        return {}

    from backend.services.booking_service import booking_service

    # Current state
    phase = state.get("booking_phase") or ""
    selected_doctor = state.get("selected_doctor") or {}
    selected_slot = state.get("selected_slot") or {}
    patient_name = state.get("patient_name") or ""
    booking_reason = state.get("booking_reason") or ""

    # ── Use LLM to extract structured data from the latest message ──
    llm = _get_llm(temperature=0)
    structured_llm = llm.with_structured_output(BookingExtraction)

    extraction_prompt = (
        "You are a data extraction assistant.\n"
        "Extract the following from the user's LATEST message ONLY (not from previous messages):\n"
        "- doctor_name: if the user mentions a specific doctor name they want to book\n"
        "- health_issue: if the user describes a health problem or symptom\n"
        "- slot_number: if the user picks a slot by number (e.g. 'slot 3' or just '3')\n"
        "- preferred_day: if the user mentions a specific day of the week (e.g. 'thursday', 'monday')\n"
        "- preferred_time: if the user mentions a specific time (e.g. '10 am', '2:30 pm', '14:00')\n"
        "- patient_name: ONLY if the user explicitly introduces their own personal name for the booking (e.g. 'My name is John'). Doctor names are NOT patient names. Return None if not provided.\n"
        "- confirmed: True if user says yes/confirm/book it, False if they say no/cancel\n"
        "Only extract what is explicitly present. Return None for anything not mentioned.\n"
    )

    try:
        extraction = structured_llm.invoke(
            [SystemMessage(content=extraction_prompt)] + list(state["messages"])
        )
    except Exception as e:
        print(f"Booking extraction error: {e}")
        extraction = BookingExtraction()

    # ── State machine logic ─────────────────────────────────────────

    updates = {}

    print(f"\n[BOOKING DEBUG] Phase={phase}, Doctor={selected_doctor.get('name','?')}, "
          f"Slot={selected_slot.get('id','?')}, Name={patient_name}, Reason={booking_reason}")
    print(f"[BOOKING DEBUG] Extraction: doctor={extraction.doctor_name}, issue={extraction.health_issue}, "
          f"slot_num={extraction.slot_number}, day={extraction.preferred_day}, time={extraction.preferred_time}, "
          f"name={extraction.patient_name}, confirmed={extraction.confirmed}")
    if extraction.health_issue and not booking_reason:
        booking_reason = extraction.health_issue
        updates["booking_reason"] = booking_reason

    # Helper: try to select a doctor and optionally filter slots by day/time
    def _try_select_doctor_and_slots(doc, extraction, updates):
        """If user gave doctor + day/time preference, try to auto-select best slot."""
        updates["selected_doctor"] = doc
        pday = extraction.preferred_day
        ptime = extraction.preferred_time
        if pday or ptime:
            # User gave a time preference — filter slots
            filtered = booking_service.get_available_slots_filtered(
                doc["id"], preferred_day=pday, preferred_time=ptime, limit=10
            )
            if filtered and len(filtered) == 1:
                # Exact match — auto-select
                updates["selected_slot"] = filtered[0]
                updates["booking_phase"] = "ask_name"
            else:
                # Multiple matches or no exact — show filtered list
                updates["booking_phase"] = "select_slot"
        else:
            updates["booking_phase"] = "select_slot"

    # Phase: "" or "ask_problem" → figure out what user provided
    if phase in ("", "ask_problem"):
        if extraction.doctor_name:
            doc = booking_service.find_doctor_by_name(extraction.doctor_name)
            if doc:
                _try_select_doctor_and_slots(doc, extraction, updates)
            else:
                updates["booking_phase"] = "suggest_doctors"
        elif extraction.health_issue:
            updates["booking_phase"] = "suggest_doctors"
        else:
            updates["booking_phase"] = "ask_problem"

    # Phase: "suggest_doctors" → user should pick a doctor
    elif phase == "suggest_doctors":
        if extraction.doctor_name:
            doc = booking_service.find_doctor_by_name(extraction.doctor_name)
            if doc:
                _try_select_doctor_and_slots(doc, extraction, updates)
            else:
                updates["booking_phase"] = "suggest_doctors"  # ask again
            # Fallback: if user just says "yes" and there's only one recommended doctor
            last_msg = state["messages"][-1].content.lower().strip()
            is_confirmed = extraction.confirmed or any(w in last_msg for w in ("yes", "sure", "ok", "go ahead"))
            
            # Or if they just mentioned the doctor's name without the LLM extracting it
            found_doc = None
            if booking_reason:
                docs = booking_service.get_doctors_by_department_keyword(booking_reason)
                if len(docs) == 1 and (is_confirmed or docs[0]["name"].lower() in last_msg or docs[0]["name"].split()[-1].lower() in last_msg):
                    found_doc = docs[0]
            
            if found_doc:
                _try_select_doctor_and_slots(found_doc, extraction, updates)
            else:
                updates["booking_phase"] = "suggest_doctors"  # still waiting

    # Phase: "select_slot" → user should pick a slot number
    elif phase == "select_slot":
        doctor = selected_doctor or updates.get("selected_doctor", {})
        if extraction.slot_number and doctor:
            # Use filtered slots if user gave day/time preferences
            pday = extraction.preferred_day
            ptime = extraction.preferred_time
            if pday or ptime:
                slots = booking_service.get_available_slots_filtered(
                    doctor["id"], preferred_day=pday, preferred_time=ptime, limit=10
                )
            else:
                slots = booking_service.get_available_slots(doctor["id"], limit=10)
            idx = extraction.slot_number - 1  # 1-based to 0-based
            if 0 <= idx < len(slots):
                updates["selected_slot"] = slots[idx]
                extracted_name = (extraction.patient_name or "").strip()
                if extracted_name and len(extracted_name) > 1:
                    updates["patient_name"] = extracted_name
                    updates["booking_phase"] = "confirm"
                else:
                    updates["booking_phase"] = "ask_name"
            else:
                updates["booking_phase"] = "select_slot"  # invalid slot, ask again
        elif extraction.patient_name:
            extracted_name = (extraction.patient_name or "").strip()
            if extracted_name and len(extracted_name) > 1:
                updates["patient_name"] = extracted_name
            updates["booking_phase"] = "select_slot"
        # else: stay

    # Phase: "ask_name" → user should give their name
    elif phase == "ask_name":
        if extraction.patient_name:
            updates["patient_name"] = extraction.patient_name
            updates["booking_phase"] = "confirm"
        else:
            updates["booking_phase"] = "ask_name"

    # Phase: "confirm" → user should say yes or no
    elif phase == "confirm":
        # Safeguard: if we got here without a patient_name, go back to ask_name
        if not patient_name.strip():
            updates["booking_phase"] = "ask_name"
        else:
            # Check structured output first
            user_confirmed = extraction.confirmed
            
            # Fallback: if structured output didn't give clear True/False,
            # check the raw user message for confirmation keywords
            if user_confirmed is None:
                last_msg = state["messages"][-1].content.lower().strip()
                if any(w in last_msg for w in ("yes", "confirm", "book it", "go ahead", "sure", "proceed")):
                    user_confirmed = True
                elif any(w in last_msg for w in ("no", "cancel", "don't", "stop", "nevermind")):
                    user_confirmed = False

            if user_confirmed is True:
                updates["booking_phase"] = "book"
            elif user_confirmed is False:
                updates["booking_phase"] = "ask_problem"
                updates["selected_doctor"] = {}
                updates["selected_slot"] = {}
                updates["patient_name"] = ""
                updates["booking_reason"] = ""
            # else: still waiting for yes/no

    # Phase: "done" → previous booking is complete, user wants another
    elif phase == "done":
        # Reset everything for a fresh booking
        updates["selected_doctor"] = {}
        updates["selected_slot"] = {}
        updates["patient_name"] = ""
        updates["booking_reason"] = ""
        if extraction.doctor_name:
            doc = booking_service.find_doctor_by_name(extraction.doctor_name)
            if doc:
                updates["selected_doctor"] = doc
                updates["booking_phase"] = "select_slot"
            else:
                updates["booking_phase"] = "suggest_doctors"
        elif extraction.health_issue:
            updates["booking_reason"] = extraction.health_issue
            updates["booking_phase"] = "suggest_doctors"
        else:
            updates["booking_phase"] = "ask_problem"

    print(f"[BOOKING DEBUG] Updates returned: {updates}")
    return updates


# ══════════════════════════════════════════════════════════════════════
#  NODE 4: Response Generation
# ══════════════════════════════════════════════════════════════════════

def response_generation_node(state: AgentState) -> dict:
    """Generates the final response. For BOOKING, uses phase to build the prompt."""
    llm = _get_llm(temperature=0)
    intent = state.get("intent")
    context = state.get("context", "")

    # ── Non-booking intents ─────────────────────────────────────────
    if intent == "EMERGENCY":
        system_msg = (
            "This is an emergency. Instruct the user to call 911 immediately. "
            f"Then provide the nearest ER location.\n\nContext:\n{context}"
        )
    elif intent == "NAVIGATION":
        system_msg = (
            "You are a helpful hospital navigation assistant.\n"
            "CRITICAL: ONLY use the provided context to answer.\n"
            "If the context is empty or irrelevant, reply: "
            "'I am sorry, but I do not have information about that location.'\n"
            "Do NOT guess or invent locations.\n\n"
            f"Context:\n{context}"
        )

    # ── BOOKING intent: code-driven flow ────────────────────────────
    elif intent == "BOOKING":
        from backend.services.booking_service import booking_service

        phase = state.get("booking_phase") or "ask_problem"
        selected_doctor = state.get("selected_doctor") or {}
        selected_slot = state.get("selected_slot") or {}
        patient_name = state.get("patient_name") or ""
        booking_reason = state.get("booking_reason") or ""

        if phase == "ask_problem":
            system_msg = (
                "You are a hospital booking assistant.\n"
                "Ask the user: 'Which doctor would you like to book an appointment with, "
                "or what health issue are you experiencing so I can recommend the best doctor?'\n"
                "Do NOT book anything. Just ask."
            )

        elif phase == "suggest_doctors":
            # Query doctors based on the reason/issue
            if booking_reason:
                doctors = booking_service.get_doctors_by_department_keyword(booking_reason)
            else:
                doctors = booking_service.get_all_doctors()

            doc_lines = []
            for d in doctors:
                doc_lines.append(
                    f"- {d['name']} ({d['specialization']}) | {d['availability']}"
                )
            doc_text = "\n".join(doc_lines) if doc_lines else "No doctors found."

            system_msg = (
                "You are a hospital booking assistant.\n"
                f"The user's health concern: {booking_reason or 'not specified'}.\n\n"
                f"Here are the recommended doctors from our database:\n{doc_text}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. ONLY present doctors from the list above.\n"
                "2. Do NOT invent, guess, or suggest any other doctors (e.g., Dr. Lee, Dr. Patel) that are not in the list.\n"
                "3. If the list says 'No doctors found', politely inform the user we don't have a specialist for that.\n"
                "4. Ask the user: 'Which doctor would you like to book an appointment with?'\n"
                "5. Do NOT book anything yet."
            )

        elif phase == "select_slot":
            # Show available slots for the selected doctor
            slots = booking_service.get_available_slots(selected_doctor["id"], limit=10)
            slot_lines = []
            for i, s in enumerate(slots, 1):
                slot_lines.append(
                    f"  Slot {i}: {s['slot_date']} | {s['start_time']} - {s['end_time']}"
                )
            slot_text = "\n".join(slot_lines) if slot_lines else "No available slots."

            system_msg = (
                "You are a hospital booking assistant.\n"
                f"The user has chosen {selected_doctor['name']} ({selected_doctor['specialization']}).\n\n"
                f"Here are the available appointment slots:\n{slot_text}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. ONLY present slots exactly as listed above.\n"
                "2. Do NOT invent or confirm any times/slots that are not in the list above.\n"
                "3. If returning 'No available slots', politely inform the user.\n"
                "4. Ask the user: 'Which slot would you like to book? (e.g., Slot 1, Slot 2, etc.)'\n"
                "5. Do NOT book anything yet."
            )

        elif phase == "ask_name":
            system_msg = (
                "You are a hospital booking assistant.\n"
                f"The user has chosen {selected_doctor['name']} "
                f"and slot on {selected_slot.get('slot_date')} at {selected_slot.get('start_time')}.\n"
                "Ask the user: 'May I have your name to complete the booking?'\n"
                "Do NOT book anything yet."
            )

        elif phase == "confirm":
            system_msg = (
                "You are a hospital booking assistant.\n"
                "Show the user a booking summary and ask for confirmation:\n\n"
                "BOOKING SUMMARY:\n"
                f"- Doctor: {selected_doctor.get('name')} ({selected_doctor.get('specialization')})\n"
                f"- Date: {selected_slot.get('slot_date')}\n"
                f"- Time: {selected_slot.get('start_time')} - {selected_slot.get('end_time')}\n"
                f"- Patient Name: {patient_name}\n"
                f"- Reason: {booking_reason}\n\n"
                "Ask the user: 'Shall I confirm this booking? (Yes/No)'\n"
                "Do NOT book anything yet — just ask for confirmation."
            )

        elif phase == "book":
            # ── DETERMINISTIC BOOKING — no LLM involved ────────────
            print(f"[BOOKING DB] Attempting to book: doctor_id={selected_doctor.get('id')}, "
                  f"slot_id={selected_slot.get('id')}, patient={patient_name}, reason={booking_reason}")
            result = booking_service.book_appointment(
                doctor_id=selected_doctor["id"],
                slot_id=selected_slot["id"],
                patient_name=patient_name,
                reason=booking_reason,
            )
            print(f"[BOOKING DB] Result: {result}")

            if result.startswith("Success"):
                system_msg = (
                    "You are a hospital booking assistant.\n"
                    "The booking was SUCCESSFUL. Tell the user:\n\n"
                    f"- Doctor: {selected_doctor.get('name')}\n"
                    f"- Date: {selected_slot.get('slot_date')}\n"
                    f"- Time: {selected_slot.get('start_time')} - {selected_slot.get('end_time')}\n"
                    f"- Patient: {patient_name}\n"
                    f"- Reason: {booking_reason}\n\n"
                    "Confirm the booking is done and wish them well."
                )
            else:
                system_msg = (
                    "You are a hospital booking assistant.\n"
                    f"The booking FAILED with error: {result}\n"
                    "Apologize and ask the user to try again or choose a different slot."
                )

            # Reset booking state after booking attempt
            response = llm.invoke(
                [SystemMessage(content=system_msg)] + list(state["messages"])
            )
            return {
                "messages": [response],
                "booking_phase": "done",
            }

        else:
            # phase == "done" or unknown — general assistant
            system_msg = (
                "You are a hospital assistant. The user's previous booking is complete. "
                "Ask if there is anything else you can help with."
            )

    else:
        system_msg = "You are a general hospital assistant. Answer nicely and ask for clarification."

    # ── Generate response ───────────────────────────────────────────
    messages = [SystemMessage(content=system_msg)] + list(state["messages"])
    response = llm.invoke(messages)
    return {"messages": [response]}


# ══════════════════════════════════════════════════════════════════════
#  GRAPH DEFINITION
# ══════════════════════════════════════════════════════════════════════

from langgraph.checkpoint.memory import MemorySaver

def create_hospital_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("detect_intent", intent_detection_node)
    workflow.add_node("retrieve_context", rag_retrieval_node)
    workflow.add_node("extract_booking", booking_extraction_node)
    workflow.add_node("generate_response", response_generation_node)

    workflow.set_entry_point("detect_intent")
    workflow.add_edge("detect_intent", "retrieve_context")
    workflow.add_edge("retrieve_context", "extract_booking")
    workflow.add_edge("extract_booking", "generate_response")
    workflow.add_edge("generate_response", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# Singleton compiled application
hospital_agent_app = create_hospital_agent()
