import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
postgres_url = os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/hospital")

print(f"Connecting to: {postgres_url}")
try:
    with psycopg2.connect(postgres_url) as conn:
        with conn.cursor() as cursor:
            with open(Path(__file__).parent / "update_schema.sql", "r") as f:
                sql = f.read()
                cursor.execute(sql)
            conn.commit()
            
            # Verify
            cursor.execute("SET search_path TO hospital, public;")
            cursor.execute("SELECT count(*) FROM time_slots;")
            count = cursor.fetchone()[0]
            print(f"Successfully created time_slots table with {count} slots!")
            
            cursor.execute("SELECT DISTINCT doctor_id, slot_date FROM time_slots ORDER BY doctor_id, slot_date LIMIT 20;")
            rows = cursor.fetchall()
            for r in rows:
                print(f"  Doctor {r[0]}: {r[1]}")
                
except Exception as e:
    print(f"Error: {e}")
