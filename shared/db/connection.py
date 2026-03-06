import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# We assume standard PostgreSQL connection for the platform's internal state.
# For dynamic adapters to external HMS, we will build dynamic engines later.

load_dotenv()

DATABASE_URL = os.getenv("POSTGRES_URL", "postgresql://user:password@localhost/hospital_app")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
