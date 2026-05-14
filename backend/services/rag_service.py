import os
import uuid
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

class RAGService:
    def __init__(self):
        # Using a free, open-source local embedding model
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        # Initialize text splitter for large documents
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        
        # Initialize the FAISS logic (lazily created upon first document insertion)
        self.vector_store = None
        print("[RAG_SERVICE] FAISS vector store initialized (lazy).")

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
            
        print(f"[RAG_SERVICE insert_document] Adding {len(docs_to_insert)} documents to FAISS...")
        if self.vector_store is None:
            self.vector_store = FAISS.from_documents(docs_to_insert, self.embeddings)
        else:
            self.vector_store.add_documents(docs_to_insert)
        print(f"[RAG_SERVICE insert_document] Done. IDs={point_ids}")
        return point_ids

    def clear_database(self):
        """Clears all data by resetting the vector store."""
        print(f"\n[RAG_SERVICE clear_database] Resetting FAISS vector store...")
        self.vector_store = None
        print(f"[RAG_SERVICE clear_database] Done.")

    def retrieve(self, query: str, top_k: int = 2) -> str:
        """Retrieves top_k context documents based on the query vector."""
        print(f"\n[RAG_SERVICE retrieve] Query='{query}', top_k={top_k}")
        
        if self.vector_store is None:
            print("[RAG_SERVICE retrieve] Vector store is empty! No results found.")
            return ""
            
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
