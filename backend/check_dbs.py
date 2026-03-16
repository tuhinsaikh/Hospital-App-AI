import psycopg2

def check_db(db_name):
    try:
        conn = psycopg2.connect(f'postgresql://postgres:password@localhost:5432/{db_name}')
        cursor = conn.cursor()
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = [r[0] for r in cursor.fetchall()]
        print(f"[{db_name}] tables: {tables}")
    except Exception as e:
        print(f"[{db_name}] error: {e}")

check_db('hospital')
check_db('postgres')
