import os
import uuid
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langchain_postgres.vectorstores import PGVector
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

class RAGService:
    def __init__(self):
        # Allow connecting to a real PostgreSQL instance via environment variable
        self.postgres_url = os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/hospital")
        self.collection_name = "hospital_data"
        # Using a free, open-source local embedding model
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        # Initialize text splitter for large documents
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        
        # Initialize the PGVector logic
        self.vector_store = PGVector(
            embeddings=self.embeddings,
            collection_name=self.collection_name,
            connection=self.postgres_url,
            use_jsonb=True,
        )
        # Ensure tables and collection exist, especially if previously dropped
        self.vector_store.create_tables_if_not_exists()
        self.vector_store.create_collection()

    def insert_document(self, document: str, base_id: str | None = None) -> list[str]:
        """Dynamically inserts a large floor plan, splitting it into vector chunks."""
        point_ids = []
        docs_to_insert = []
        
        # Split the large document into smaller chunks via LangChain
        chunks = self.text_splitter.split_text(document)
        
        for idx, chunk in enumerate(chunks):
            # If doc_id is provided, append index to keep IDs unique per chunk
            point_id = f"{base_id}-{idx}" if base_id else str(uuid.uuid4())
            point_ids.append(point_id)
            
            docs_to_insert.append(Document(
                page_content=chunk,
                metadata={"id": point_id}
            ))
            
        self.vector_store.add_documents(docs_to_insert, ids=point_ids)
        return point_ids

    def clear_database(self):
        """Clears all data by dropping the specific collection."""
        self.vector_store.delete_collection()
        self.vector_store.create_collection()

    def retrieve(self, query: str, top_k: int = 2) -> str:
        """Retrieves top_k context documents based on the query vector."""
        search_result = self.vector_store.similarity_search(query, k=top_k)
        
        if not search_result:
            return ""
            
        contexts = [doc.page_content for doc in search_result]
        return "\n".join(contexts)

# Singleton instance for the backend
rag_service = RAGService()
