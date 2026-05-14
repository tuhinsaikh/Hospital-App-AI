"""Run the navigation_graphs table migration."""
import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
postgres_url = os.getenv("POSTGRES_URL")

print(f"Connecting to: {postgres_url}")
try:
    with psycopg2.connect(postgres_url) as conn:
        with conn.cursor() as cursor:
            with open(Path(__file__).parent / "add_navigation_table.sql", "r") as f:
                sql = f.read()
                cursor.execute(sql)
            conn.commit()

            # Verify
            cursor.execute("SET search_path TO hospital, public;")
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'navigation_graphs' 
                ORDER BY ordinal_position;
            """)
            rows = cursor.fetchall()
            print("navigation_graphs table created successfully!")
            for r in rows:
                print(f"  {r[0]}: {r[1]}")

except Exception as e:
    print(f"Error: {e}")
