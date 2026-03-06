import os
import uuid
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres.vectorstores import PGVector
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class RAGService:
    def __init__(self):
        self.postgres_url = os.getenv(
            "POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/hospital"
        )
        self.collection_name = "hospital_data"
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " ", ""],
        )
        self.vector_store = PGVector(
            embeddings=self.embeddings,
            collection_name=self.collection_name,
            connection=self.postgres_url,
            use_jsonb=True,
        )
        self.vector_store.create_tables_if_not_exists()
        self.vector_store.create_collection()

    def insert_document(self, document: str, base_id: str | None = None) -> list[str]:
        """Splits and inserts a document into the vector store."""
        chunks = self.text_splitter.split_text(document)
        docs_to_insert = []
        point_ids = []
        for idx, chunk in enumerate(chunks):
            point_id = f"{base_id}-{idx}" if base_id else str(uuid.uuid4())
            point_ids.append(point_id)
            docs_to_insert.append(Document(page_content=chunk, metadata={"id": point_id}))
        self.vector_store.add_documents(docs_to_insert, ids=point_ids)
        return point_ids

    def clear_database(self):
        """Clears and recreates the vector collection."""
        self.vector_store.delete_collection()
        self.vector_store.create_collection()

    def retrieve(self, query: str, top_k: int = 2) -> str:
        """Returns top_k relevant context chunks for a query."""
        results = self.vector_store.similarity_search(query, k=top_k)
        if not results:
            return ""
        return "\n".join(doc.page_content for doc in results)


# Singleton
rag_service = RAGService()
