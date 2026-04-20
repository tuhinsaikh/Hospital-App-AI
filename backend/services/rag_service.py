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
        print(f"[RAG_SERVICE] Connecting to PostgreSQL: {self.postgres_url[:50]}...")
        self.vector_store = PGVector(
            embeddings=self.embeddings,
            collection_name=self.collection_name,
            connection=self.postgres_url,
            use_jsonb=True,
        )
        # Ensure tables and collection exist, especially if previously dropped
        self.vector_store.create_tables_if_not_exists()
        self.vector_store.create_collection()
        print(f"[RAG_SERVICE] PGVector initialized. Collection='{self.collection_name}'")

    def insert_document(self, document: str, base_id: str | None = None) -> list[str]:
        """Dynamically inserts a large floor plan, splitting it into vector chunks."""
        print(f"\n[RAG_SERVICE insert_document] Document length={len(document)}, base_id={base_id}")
        point_ids = []
        docs_to_insert = []
        
        # Split the large document into smaller chunks via LangChain
        chunks = self.text_splitter.split_text(document)
        print(f"[RAG_SERVICE insert_document] Split into {len(chunks)} chunks (chunk_size=300, overlap=50)")
        
        for idx, chunk in enumerate(chunks):
            # If doc_id is provided, append index to keep IDs unique per chunk
            point_id = f"{base_id}-{idx}" if base_id else str(uuid.uuid4())
            point_ids.append(point_id)
            print(f"[RAG_SERVICE insert_document] Chunk {idx}: id={point_id}, len={len(chunk)}, preview='{chunk[:80]}...'")
            
            docs_to_insert.append(Document(
                page_content=chunk,
                metadata={"id": point_id}
            ))
            
        print(f"[RAG_SERVICE insert_document] Adding {len(docs_to_insert)} documents to PGVector...")
        self.vector_store.add_documents(docs_to_insert, ids=point_ids)
        print(f"[RAG_SERVICE insert_document] Done. IDs={point_ids}")
        return point_ids

    def clear_database(self):
        """Clears all data by dropping the specific collection."""
        print(f"\n[RAG_SERVICE clear_database] Dropping collection '{self.collection_name}'...")
        self.vector_store.delete_collection()
        print(f"[RAG_SERVICE clear_database] Recreating collection '{self.collection_name}'...")
        self.vector_store.create_collection()
        print(f"[RAG_SERVICE clear_database] Done.")

    def retrieve(self, query: str, top_k: int = 2) -> str:
        """Retrieves top_k context documents based on the query vector."""
        print(f"\n[RAG_SERVICE retrieve] Query='{query}', top_k={top_k}")
        search_result = self.vector_store.similarity_search(query, k=top_k)
        
        if not search_result:
            print(f"[RAG_SERVICE retrieve] No results found!")
            return ""
        
        print(f"[RAG_SERVICE retrieve] Found {len(search_result)} results:")
        for i, doc in enumerate(search_result):
            print(f"[RAG_SERVICE retrieve]   Result {i+1}: '{doc.page_content[:100]}...' (metadata={doc.metadata})")
            
        contexts = [doc.page_content for doc in search_result]
        combined = "\n".join(contexts)
        print(f"[RAG_SERVICE retrieve] Combined context length={len(combined)}")
        return combined

# Singleton instance for the backend
rag_service = RAGService()
