import sys
from langchain_postgres import PGVector
with open("pgvector_help_utf8.txt", 'w', encoding='utf-8') as f:
    sys.stdout = f
    help(PGVector)
