# Hospital AI Agent API

## Setup and Startup Instructions

Follow these step-by-step instructions to set up and run the application locally.

### 1. Create and Activate Virtual Environment
First, create a virtual environment in the root directory and activate it:
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
Install the required packages from the backend directory:
```bash
pip install -r backend\requirements.txt
```

### 3. Configure Environment Variables
Copy the sample environment file and configure it:
```bash
copy backend\.env.example backend\.env
```
Open `backend\.env` in your editor and provide the necessary API keys and database credentials, primarily:
- `GROQ_API_KEY`
- `POSTGRES_URL` (e.g., `postgresql://postgres:postgres@localhost:5432/hospital`)

### 4. Database Initialization
Ensure your PostgreSQL database is running and matches the `POSTGRES_URL` you configured. Then, run the schema migrations and dummy data population scripts:
```bash
cd backend
python run_migration.py
python run_sql.py
cd ..
```

### 5. Run the Application
Finally, start the FastAPI application using Uvicorn:
```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

You can now access the chat UI in your browser:
`http://127.0.0.1:8000/`
