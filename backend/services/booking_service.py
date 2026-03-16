import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Optional
from datetime import date, time, timedelta

# Mapping of day names to Python weekday ints (0=Mon, 6=Sun)
DAY_NAME_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


def _serialize_slot(row: dict) -> dict:
    """Convert date/time objects to strings so they survive LangGraph state."""
    
    # Get the day name (e.g., "Monday")
    day_name = row["slot_date"].strftime("%A")
    
    return {
        "id": int(row["id"]),
        "slot_date": f"{row['slot_date']} ({day_name})",  # "2026-03-16 (Monday)"
        "start_time": str(row["start_time"])[:5],         # "10:00"
        "end_time": str(row["end_time"])[:5],             # "10:30"
    }


class BookingService:
    def __init__(self):
        self.postgres_url = os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/hospital")

    def get_connection(self):
        return psycopg2.connect(self.postgres_url, options="-c search_path=hospital,public")

    # ── Doctor Queries ──────────────────────────────────────────────

    def get_all_doctors(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT d.id, d.name, d.specialization,
                           d.availability_schedule AS availability,
                           dep.name AS department
                    FROM doctors d
                    JOIN departments dep ON d.department_id = dep.id
                    ORDER BY d.id
                """)
                return [dict(r) for r in cur.fetchall()]

    def get_doctors_by_department_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """Intelligently map a health issue to the correct department using the LLM."""
        
        # 1. Fetch available departments from the database
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM departments")
                departments = [r[0] for r in cur.fetchall()]
        
        if not departments:
            return []

        # 2. Use LLM to classify the medical issue into one of these departments
        from langchain_core.messages import SystemMessage, HumanMessage
        from pydantic import BaseModel, Field
        from langchain_groq import ChatGroq
        from langchain_ollama import ChatOllama
        import os
        
        class DeptClassification(BaseModel):
            department: str = Field(description=f"Must be exactly one of: {', '.join(departments)}")
            
        provider = os.getenv("LLM_PROVIDER", "groq").lower()
        if provider == "local":
            base_url = os.getenv("OLLAMA_BASE_URL") or "http://192.168.1.202:11434"
            model = os.getenv("OLLAMA_MODEL") or "llama3.1:8b"
            llm = ChatOllama(base_url=base_url, model=model, temperature=0)
        else:
            llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
            
        structured_llm = llm.with_structured_output(DeptClassification)
        
        system_msg = (
            "You are a medical triage assistant.\n"
            "Your job is to read a patient's health issue or symptom and map it "
            "to the most appropriate hospital department from the provided list.\n"
            f"AVAILABLE DEPARTMENTS: {', '.join(departments)}\n"
            "CRITICAL: If the issue does not clearly fit a specialist (or you are unsure), "
            "you MUST select 'General Medicine'. Do NOT invent new departments."
        )
        
        try:
            result = structured_llm.invoke([
                SystemMessage(content=system_msg),
                HumanMessage(content=f"Health Issue: {keyword}")
            ])
            dept = result.department
            if dept not in departments:
                dept = "General Medicine"
        except Exception as e:
            print(f"Dept classification error: {e}")
            dept = "General Medicine"
            
        print(f"[TRIAGE] Mapped issue '{keyword}' to department '{dept}'")

        # 3. Fetch doctors for the classified department
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT d.id, d.name, d.specialization,
                           d.availability_schedule AS availability,
                           dep.name AS department
                    FROM doctors d
                    JOIN departments dep ON d.department_id = dep.id
                    WHERE dep.name = %s
                    ORDER BY d.id
                """, (dept,))
                return [dict(r) for r in cur.fetchall()]

    def find_doctor_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT d.id, d.name, d.specialization,
                           d.availability_schedule AS availability,
                           dep.name AS department
                    FROM doctors d
                    JOIN departments dep ON d.department_id = dep.id
                    WHERE LOWER(d.name) LIKE %s
                    LIMIT 1
                """, (f"%{name.lower().strip()}%",))
                row = cur.fetchone()
                return dict(row) if row else None

    # ── Slot Queries ────────────────────────────────────────────────

    def get_available_slots(self, doctor_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Return next N available slots as serializable dicts."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, slot_date, start_time, end_time
                    FROM time_slots
                    WHERE doctor_id = %s
                      AND is_available = TRUE
                      AND slot_date >= CURRENT_DATE
                    ORDER BY slot_date, start_time
                    LIMIT %s
                """, (doctor_id, limit))
                return [_serialize_slot(r) for r in cur.fetchall()]

    def get_available_slots_filtered(self, doctor_id: int,
                                      preferred_day: Optional[str] = None,
                                      preferred_time: Optional[str] = None,
                                      limit: int = 10) -> List[Dict[str, Any]]:
        """
        Return available slots filtered by preferred day of week and/or time.
        preferred_day: e.g. "thursday"
        preferred_time: e.g. "10:00" or "10"
        """
        # Start with all available future slots
        all_slots_raw = []
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, slot_date, start_time, end_time
                    FROM time_slots
                    WHERE doctor_id = %s
                      AND is_available = TRUE
                      AND slot_date >= CURRENT_DATE
                    ORDER BY slot_date, start_time
                """, (doctor_id,))
                all_slots_raw = cur.fetchall()

        if not all_slots_raw:
            return []

        filtered = list(all_slots_raw)

        # Filter by day of week
        if preferred_day:
            day_lower = preferred_day.lower().strip()
            target_weekday = DAY_NAME_MAP.get(day_lower)
            if target_weekday is not None:
                filtered = [s for s in filtered if s["slot_date"].weekday() == target_weekday]

        # Filter by time (match start_time hour)
        if preferred_time:
            try:
                # Parse "10", "10:00", "10 am", etc.
                t = preferred_time.strip().lower().replace(" ", "")
                hour = None
                if "am" in t or "pm" in t:
                    is_pm = "pm" in t
                    t = t.replace("am", "").replace("pm", "").strip(":")
                    hour = int(t.split(":")[0])
                    if is_pm and hour != 12:
                        hour += 12
                    if not is_pm and hour == 12:
                        hour = 0
                else:
                    hour = int(t.split(":")[0])

                if hour is not None:
                    filtered = [s for s in filtered if s["start_time"].hour == hour]
            except (ValueError, IndexError):
                pass  # Can't parse time, skip filter

        # If filtering removed everything, return unfiltered (top N)
        if not filtered:
            return [_serialize_slot(r) for r in all_slots_raw[:limit]]

        return [_serialize_slot(r) for r in filtered[:limit]]

    # ── Booking ─────────────────────────────────────────────────────

    def book_appointment(self, doctor_id: int, slot_id: int,
                         patient_name: str, reason: str) -> str:
        """
        Book an appointment — explicit connection handling (no context managers).
        """
        conn = None
        cur = None
        try:
            conn = self.get_connection()
            conn.autocommit = False  # Explicit transaction control
            cur = conn.cursor(cursor_factory=RealDictCursor)

            print(f"[DB] Checking slot {slot_id}...")
            cur.execute("""
                SELECT id, slot_date, start_time, is_available
                FROM time_slots WHERE id = %s
            """, (int(slot_id),))
            slot = cur.fetchone()
            if not slot:
                return f"Error: Slot {slot_id} not found."
            print(f"[DB] Slot found: {dict(slot)}")
            if not slot["is_available"]:
                return "Error: This slot has already been booked."

            print(f"[DB] Marking slot {slot_id} unavailable...")
            cur.execute("UPDATE time_slots SET is_available = FALSE WHERE id = %s",
                        (int(slot_id),))
            print(f"[DB] UPDATE rowcount: {cur.rowcount}")

            print(f"[DB] Looking up patient '{patient_name}'...")
            cur.execute("SELECT id FROM patients WHERE LOWER(name) = %s LIMIT 1",
                        (patient_name.lower().strip(),))
            patient = cur.fetchone()
            if patient:
                patient_id = patient["id"]
                print(f"[DB] Found existing patient id={patient_id}")
            else:
                cur.execute("INSERT INTO patients (name) VALUES (%s) RETURNING id",
                            (patient_name,))
                patient_id = cur.fetchone()["id"]
                print(f"[DB] Created new patient id={patient_id}")

            appt_time = f"{slot['slot_date']} {slot['start_time']}"
            print(f"[DB] Inserting appointment: doctor={doctor_id}, patient={patient_id}, time={appt_time}")
            cur.execute("""
                INSERT INTO appointments
                    (doctor_id, patient_id, appointment_time, status, reason, slot_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (int(doctor_id), patient_id, appt_time, "Scheduled", reason, int(slot_id)))

            appt_id = cur.fetchone()["id"]
            print(f"[DB] Appointment created with id={appt_id}, committing...")
            conn.commit()
            print(f"[DB] COMMITTED successfully!")
            return f"Success: Appointment #{appt_id} booked!"

        except Exception as e:
            print(f"[DB] BOOKING ERROR: {e}")
            if conn:
                conn.rollback()
            return f"Error: {e}"
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()


booking_service = BookingService()
