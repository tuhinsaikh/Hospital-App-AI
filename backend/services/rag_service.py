import os
import uuid
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

class RAGService:
    def __init__(self):
        # Allow connecting to a real Qdrant instance via environment variable
        self.qdrant_url = os.getenv("QDRANT_URL", ":memory:")
        self.client = QdrantClient(location=self.qdrant_url)
        self.collection_name = "hospital_data"
        # Using a free, open-source local embedding model
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.setup_collection()

    def setup_collection(self):
        """Creates the Qdrant collection if it doesn't exist and seeds it."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                # all-MiniLM-L6-v2 uses 384 dimensions (OpenAI uses 1536)
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
            self._insert_example_data()

    def _insert_example_data(self):
        """Inserts example hospital location data into Qdrant."""
        documents = [
            "The X-ray department is located on Floor 2, Room 204 in the North Wing.",
            "The MRI scanner is situated on Floor 1, Room 105 in the Radiology department.",
            "The Emergency Room (ER) is located on the Ground Floor, entrance from the West lot.",
            "The Cafeteria is on the Ground Floor, near the main reception.",
            "The Maternity Ward is located on Floor 3, Rooms 301-350."
        ]
        
        points = []
        vectors = self.embeddings.embed_documents(documents)
        
        for doc, vector in zip(documents, vectors):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={"text": doc}
                )
            )
            
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    def insert_document(self, document: str, doc_id: str | None = None) -> str:
        """Dynamically inserts or updates a floor plan or location rule in Qdrant."""
        vector = self.embeddings.embed_query(document)
        
        # Use provided ID (for updates) or generate a new one
        point_id = doc_id if doc_id else str(uuid.uuid4())
        
        point = PointStruct(
            id=point_id,
            vector=vector,
            payload={"text": document}
        )
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
        
        return point_id

    def retrieve(self, query: str, top_k: int = 2) -> str:
        """Retrieves top_k context documents based on the query vector."""
        query_vector = self.embeddings.embed_query(query)
        
        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k
        ).points
        
        if not search_result:
            return ""
            
        contexts = [hit.payload["text"] for hit in search_result if hit.payload and "text" in hit.payload]
        return "\n".join(contexts)

# Singleton instance for the backend
rag_service = RAGService()
