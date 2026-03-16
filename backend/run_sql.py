import psycopg2
import os

from dotenv import load_dotenv

load_dotenv()
postgres_url = os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/hospital")

print(f"Connecting to: {postgres_url}")
try:
    with psycopg2.connect(postgres_url) as conn:
        with conn.cursor() as cursor:
            with open("appointment_dummy_data.sql", "r") as f:
                sql = f.read()
                cursor.execute(sql)
            conn.commit()
    print("Successfully ran appointment_dummy_data.sql against the database")
except Exception as e:
    print(f"Error executing SQL: {e}")
