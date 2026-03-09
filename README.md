create vertual environment 
python -m venv .venv

 Activate the Virtual Environment
.\.venv\Scripts\Activate.ps1

Install the Dependencies
pip install -r backend\requirements.txt

 Run the Application
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
