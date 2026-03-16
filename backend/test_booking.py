"""Direct test of book_appointment to isolate the DB issue."""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

from services.booking_service import booking_service

# 1. Get a doctor
doc = booking_service.find_doctor_by_name("Robert Brown")
print(f"Doctor: {doc}")

# 2. Get an available slot
slots = booking_service.get_available_slots(doc["id"], limit=3)
print(f"Slots: {slots}")

if not slots:
    print("No available slots!")
    exit()

slot = slots[0]
print(f"Using slot: {slot}")

# 3. Try to book
result = booking_service.book_appointment(
    doctor_id=doc["id"],
    slot_id=slot["id"],
    patient_name="Test Patient",
    reason="Test booking"
)
print(f"\nResult: {result}")

# 4. Verify by querying
import psycopg2
from psycopg2.extras import RealDictCursor
conn = psycopg2.connect(os.getenv("POSTGRES_URL"), options="-c search_path=hospital,public")
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute("SELECT * FROM appointments ORDER BY id DESC LIMIT 3")
print(f"\nLatest appointments: {cur.fetchall()}")

cur.execute(f"SELECT * FROM time_slots WHERE id = {slot['id']}")
print(f"Slot after booking: {cur.fetchone()}")

cur.close()
conn.close()
