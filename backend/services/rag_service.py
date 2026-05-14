import os
import uuid
import json
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

def _get_llm(temperature=0):
    """Factory method to return the configured LLM."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "local":
        base_url = os.getenv("OLLAMA_BASE_URL") or "http://192.168.1.202:11434"
        model = os.getenv("OLLAMA_MODEL") or "llama3.1:8b"
        return ChatOllama(base_url=base_url, model=model, temperature=temperature)
    else:
        return ChatGroq(model="llama-3.1-8b-instant", temperature=temperature)

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

    def generate_and_insert_graph_embedding(self, floor: int, graph_data: dict, extracted_text: str | None = None) -> list[str]:
        """
        Uses an LLM to translate raw JSON graph data into a rich natural language
        description, then embeds and inserts it into the Vector Database.
        """
        print(f"\n[RAG_SERVICE] Generating rich AI description for floor {floor} graph...")
        llm = _get_llm(temperature=0)
        
        # Create a condensed version of the graph data for the LLM prompt to save tokens
        condensed_nodes = []
        for n in graph_data.get("nodes", []):
            condensed_nodes.append({
                "id": n.get("id"),
                "label": n.get("label"),
                "type": n.get("type")
            })
            
        condensed_edges = []
        for e in graph_data.get("edges", []):
            condensed_edges.append({
                "from": e.get("from"),
                "to": e.get("to")
            })

        system_prompt = (
            "You are a routing assistant. Your task is to take the provided JSON data "
            "representing a hospital floor plan and generate a detailed, highly descriptive "
            "paragraph in natural language. This text will be embedded into a vector database "
            "for semantic RAG search, so include natural synonyms and clearly state the relationships "
            "and connected paths between locations.\n"
            "Format the output as clear sentences without any markdown formatting or code blocks."
        )
        
        user_prompt = (
            f"Floor Number: {floor}\n"
            f"Vision Extracted Summary: {extracted_text or 'N/A'}\n"
            f"Graph Nodes (Locations): {json.dumps(condensed_nodes)}\n"
            f"Graph Edges (Connections): {json.dumps(condensed_edges)}\n\n"
            "Generate the descriptive text now."
        )
        
        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            rich_description = response.content
            print(f"[RAG_SERVICE] Successfully generated rich description. Length: {len(rich_description)}")
            
            # Combine the base description and the rich description just to be thorough
            final_text = f"Hospital floor {floor} navigation graph.\n\n"
            final_text += f"Rich Description:\n{rich_description}\n\n"
            if extracted_text:
                final_text += f"Vision Summary:\n{extracted_text}\n"
            
            # Insert the newly generated descriptive text
            return self.insert_document(final_text, base_id=f"floor_{floor}_graph")
        except Exception as e:
            print(f"[RAG_SERVICE] WARNING: Failed to generate rich description with LLM. Error: {e}")
            # Fallback to a basic string representation if LLM fails
            fallback_text = f"Hospital floor {floor} navigation graph.\nNodes: {json.dumps(condensed_nodes)}\nEdges: {json.dumps(condensed_edges)}"
            return self.insert_document(fallback_text, base_id=f"floor_{floor}_graph")

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
