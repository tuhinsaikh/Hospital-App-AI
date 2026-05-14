import os
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import json

from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Load env variables (GROQ_API_KEY, POSTGRES_URL)
from pathlib import Path
dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

# HTML Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
MAPS_DIR = STATIC_DIR / "maps"
DRAFTS_DIR = Path(__file__).parent / "tmp" / "floor_plan_drafts"

# Ensure static directories exist
MAPS_DIR.mkdir(parents=True, exist_ok=True)
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

# Import the LangGraph compiled agent and RAG service
from backend.agents.hospital_agent import hospital_agent_app
from backend.services.rag_service import rag_service
from backend.services.vision_service import vision_service
from backend.services.navigation_service import navigation_service

# --- Models ---
class ChatRequest(BaseModel):
    user_id: str
    message: str = ""

class ChatResponse(BaseModel):
    response: str
    intent: str = ""
    navigation_hints: dict | None = None

class UpdatePlanRequest(BaseModel):
    # Optional ID. If provided, updates existing rule. If None, makes new rule.
    location_id: str | None = None
    document: str

class NavigationPathRequest(BaseModel):
    source: str
    destination: str
    floor: int = 1

# --- App Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("GROQ_API_KEY"):
        print("WARNING: GROQ_API_KEY is not set. The LLM nodes will fail.")
    yield

# --- FastAPI Setup ---
app = FastAPI(title="Hospital AI Agent API", lifespan=lifespan)

# Mount static files for serving floor plan images
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_chat_ui():
    html_content = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)

@app.get("/navigate", response_class=HTMLResponse)
async def get_navigation_ui():
    """Full-page Google Maps-like indoor navigation UI."""
    html_content = (TEMPLATES_DIR / "navigation.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)

@app.get("/admin", response_class=HTMLResponse)
async def get_admin_ui():
    """Admin floor plan editor UI."""
    html_content = (TEMPLATES_DIR / "admin.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)

class SaveGraphRequest(BaseModel):
    floor: int = 1
    graph_data: dict
    update_vectors: bool = True
    draft_id: str | None = None

class SaveDraftRequest(BaseModel):
    draft_id: str
    floor: int = 1
    graph_data: dict


def _draft_path(draft_id: str) -> Path:
    """Return the JSON draft path for a UUID draft id."""
    try:
        clean_id = str(uuid.UUID(draft_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    return DRAFTS_DIR / f"{clean_id}.json"


def _load_floor_plan_draft(draft_id: str) -> dict | None:
    path = _draft_path(draft_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save_floor_plan_draft(draft: dict) -> dict:
    if not draft.get("draft_id"):
        draft["draft_id"] = str(uuid.uuid4())
    draft["updated_at"] = datetime.utcnow().isoformat() + "Z"
    path = _draft_path(draft["draft_id"])
    path.write_text(json.dumps(draft, indent=2), encoding="utf-8")
    return draft




def _graph_debug_snapshot(floor: int, graph_data: dict) -> dict:
    nodes_by_id = {node.get("id"): node for node in graph_data.get("nodes", [])}
    edges = []
    for idx, edge in enumerate(graph_data.get("edges", []), 1):
        from_node = nodes_by_id.get(edge.get("from"), {})
        to_node = nodes_by_id.get(edge.get("to"), {})
        from_door = from_node.get("door")
        to_door = to_node.get("door")
        route = []
        route.append({"kind": "node", "id": edge.get("from"), "x": from_node.get("x"), "y": from_node.get("y")})
        if from_door:
            route.append({"kind": "door", "id": f"{edge.get('from')}:door", **from_door})
        for point in edge.get("path") or edge.get("waypoints") or []:
            route.append({"kind": "bend", "x": point.get("x"), "y": point.get("y")})
        if to_door:
            route.append({"kind": "door", "id": f"{edge.get('to')}:door", **to_door})
        route.append({"kind": "node", "id": edge.get("to"), "x": to_node.get("x"), "y": to_node.get("y")})
        edges.append({
            "index": idx,
            "from": edge.get("from"),
            "to": edge.get("to"),
            "path": edge.get("path") or [],
            "expanded_route": route,
        })
    return {
        "floor": floor,
        "nodes": graph_data.get("nodes", []),
        "edges": edges,
        "counts": {
            "nodes": len(graph_data.get("nodes", [])),
            "edges": len(graph_data.get("edges", [])),
            "doors": len([node for node in graph_data.get("nodes", []) if node.get("door")]),
        },
    }

@app.post("/admin/save_graph")
async def admin_save_graph(request: SaveGraphRequest):
    """Save an edited navigation graph to the database."""
    print(f"\n[API /admin/save_graph] floor={request.floor}, "
          f"nodes={len(request.graph_data.get('nodes', []))}, "
          f"edges={len(request.graph_data.get('edges', []))}")
    try:
        draft = _load_floor_plan_draft(request.draft_id) if request.draft_id else None
        if request.draft_id and not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Get image metadata from the draft first, then fall back to existing DB data.
        entry = navigation_service.load_graph(request.floor)
        image_path = (draft or {}).get("image_path") or (entry["image_path"] if entry else "")
        image_width = (draft or {}).get("image_width") or (entry["image_width"] if entry else 0)
        image_height = (draft or {}).get("image_height") or (entry["image_height"] if entry else 0)

        navigation_service.save_graph(
            floor=request.floor,
            graph_data=request.graph_data,
            image_path=image_path,
            image_width=image_width,
            image_height=image_height,
        )

        if request.update_vectors and request.graph_data.get("nodes"):
            extracted_text = (draft or {}).get("extracted_text")
            # TASK 2: Use AI Embedding Pipeline to generate a rich, natural language summary
            # and insert it into the FAISS vector database.
            rag_service.generate_and_insert_graph_embedding(
                floor=request.floor, 
                graph_data=request.graph_data, 
                extracted_text=extracted_text
            )

        if draft:
            draft["status"] = "committed"
            draft["graph_data"] = request.graph_data
            _save_floor_plan_draft(draft)

        graph_log = _graph_debug_snapshot(request.floor, request.graph_data)
        print("[ADMIN GRAPH SAVE LOG]")
        print(json.dumps(graph_log, indent=2))

        return {
            "status": "success",
            "message": f"Graph saved for floor {request.floor}",
            "graph_log": graph_log,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/save_draft")
async def admin_save_draft(request: SaveDraftRequest):
    """Persist the current editor state to the upload draft JSON file."""
    draft = _load_floor_plan_draft(request.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft["floor"] = request.floor
    draft["graph_data"] = request.graph_data
    draft["status"] = "editing"
    _save_floor_plan_draft(draft)
    return {"status": "success", "message": "Draft updated"}

@app.get("/admin/floor_data")
async def admin_floor_data(floor: int = Query(1)):
    """Return existing graph data + image info for a floor."""
    entry = navigation_service.load_graph(floor)
    if not entry:
        raise HTTPException(status_code=404, detail=f"No data for floor {floor}")
    return {
        "floor": floor,
        "graph_data": entry["graph_data"],
        "image_path": entry["image_path"],
        "image_width": entry["image_width"],
        "image_height": entry["image_height"],
        "floor_name": entry["floor_name"],
    }


@app.post("/update_floor_plan")
async def update_floor_plan(
    file: UploadFile = File(None),
    document: str = Form(None),
    location_id: str = Form(None),
    floor_number: int = Form(1),
):
    print("\n" + "="*70)
    print("[API /update_floor_plan] >>> REQUEST RECEIVED (Streaming)")
    print(f"[API /update_floor_plan] file={file.filename if file else None}, document_len={len(document) if document else 0}, location_id={location_id}, floor={floor_number}")
    print("="*70)

    async def process_stream():
        try:
            if file:
                yield json.dumps({"step": 1, "status": "processing", "message": f"Reading image file: {file.filename}"}) + "\n"
                file_bytes = await file.read()
                
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(file_bytes))
                img_width, img_height = img.size
                yield json.dumps({"step": 2, "status": "processing", "message": f"Image dimensions: {img_width}x{img_height}"}) + "\n"

                yield json.dumps({"step": 3, "status": "processing", "message": "Extracting text description from image (Pass 1)..."}) + "\n"
                extracted_text = vision_service.extract_floor_plan_from_image(file_bytes, file.content_type)
                
                yield json.dumps({"step": 4, "status": "processing", "message": "Holding extracted text for final save..."}) + "\n"
                # TASK 1: Notice that we DO NOT save to PostgreSQL or the Vector DB here.
                # The data is kept strictly in a temporary JSON draft for admin review.
                doc_id = location_id or f"floor_{floor_number}_{uuid.uuid4().hex[:8]}"
                
                yield json.dumps({"step": 5, "status": "processing", "message": "Extracting navigation graph from image (Pass 2)..."}) + "\n"
                nav_graph = None
                try:
                    nav_graph = vision_service.extract_navigation_graph_from_image(
                        file_bytes, file.content_type, img_width, img_height
                    )
                except Exception as nav_err:
                    yield json.dumps({"step": 5, "status": "warning", "message": f"Graph extraction failed: {nav_err}"}) + "\n"
                    
                yield json.dumps({"step": 6, "status": "processing", "message": "Saving floor plan image..."}) + "\n"
                image_filename = f"floor_{floor_number}_{uuid.uuid4().hex[:8]}{Path(file.filename).suffix}"
                image_save_path = MAPS_DIR / image_filename
                with open(image_save_path, "wb") as img_file:
                    img_file.write(file_bytes)
                image_url = f"/static/maps/{image_filename}"
                
                yield json.dumps({"step": 7, "status": "processing", "message": "Saving editable draft..."}) + "\n"
                draft = _save_floor_plan_draft({
                    "draft_id": str(uuid.uuid4()),
                    "status": "editing",
                    "floor": floor_number,
                    "location_id": doc_id,
                    "extracted_text": extracted_text,
                    "graph_data": nav_graph or {"nodes": [], "edges": []},
                    "image_path": image_url,
                    "image_width": img_width,
                    "image_height": img_height,
                    "original_filename": file.filename,
                })
                    
                yield json.dumps({
                    "step": 8,
                    "status": "success", 
                    "message": "Floor plan draft is ready for editing.",
                    "location_id": doc_id,
                    "draft_id": draft["draft_id"],
                    "extracted_text": extracted_text,
                    "navigation_graph": draft["graph_data"],
                    "floor_plan_image": image_url,
                }) + "\n"
            elif document:
                yield json.dumps({"step": 1, "status": "processing", "message": "Received text document. Inserting..."}) + "\n"
                doc_id = rag_service.insert_document(document, location_id)
                yield json.dumps({
                    "step": 2,
                    "status": "success", 
                    "message": "Floor plan structured successfully.",
                    "location_id": doc_id
                }) + "\n"
            else:
                yield json.dumps({"status": "error", "message": "Must provide either 'file' (image) or 'document' (text)."}) + "\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield json.dumps({"status": "error", "message": str(e)}) + "\n"

    return StreamingResponse(process_stream(), media_type="application/x-ndjson")

@app.delete("/clear_floor_plan")
async def clear_floor_plan():
    print("\n" + "="*70)
    print("[API /clear_floor_plan] >>> REQUEST RECEIVED")
    print("="*70)
    try:
        print("[API /clear_floor_plan] STEP 1: Calling rag_service.clear_database()...")
        rag_service.clear_database()
        print("[API /clear_floor_plan] STEP 2: Database cleared successfully.")
        print("[API /clear_floor_plan] <<< SUCCESS")
        return {"status": "success", "message": "All floor plan data cleared successfully."}
    except Exception as e:
        print(f"[API /clear_floor_plan] <<< ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    print("\n" + "="*70)
    print(f"[API /chat] >>> REQUEST RECEIVED")
    print(f"[API /chat] user_id={request.user_id}, message='{request.message}'")
    print("="*70)
    try:
        # Only pass fields that must reset per-message.
        # Booking fields (booking_phase, selected_doctor, etc.) are managed
        # by the checkpointer and must NOT be overwritten here.
        initial_state = {
            "user_id": request.user_id,
            "messages": [HumanMessage(content=request.message)],
            "intent": "",
            "context": "",
        }
        print(f"[API /chat] STEP 1: Initial state prepared: user_id={request.user_id}, intent='', context=''")
        
        # 2. Invoke the compiled LangGraph workflow
        config = {"configurable": {"thread_id": request.user_id}}
        print(f"[API /chat] STEP 2: Invoking LangGraph workflow (thread_id={request.user_id})...")
        result = hospital_agent_app.invoke(initial_state, config=config)
        
        # 3. Extract the last message (which is the AIMessage generated by response node)
        final_message = result["messages"][-1].content
        intent = result.get("intent", "")
        navigation_hints = result.get("navigation_hints", None)
        
        print(f"[API /chat] STEP 3: Workflow complete.")
        print(f"[API /chat] Final intent={intent}, context_len={len(result.get('context', ''))}")
        print(f"[API /chat] Navigation hints={navigation_hints}")
        print(f"[API /chat] Final message: {final_message[:300]}...")
        print(f"[API /chat] <<< SUCCESS")
        
        return ChatResponse(
            response=final_message,
            intent=intent,
            navigation_hints=navigation_hints,
        )
        
    except Exception as e:
        print(f"[API /chat] <<< ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/navigation/path")
async def get_navigation_path(request: NavigationPathRequest):
    """
    Fast path calculation — reads graph from memory cache, no DB queries.
    Resolves source/destination names to graph nodes, runs Dijkstra,
    returns the polyline waypoints.
    """
    print("\n" + "="*70)
    print(f"[API /navigation/path] >>> REQUEST: source='{request.source}', dest='{request.destination}', floor={request.floor}")
    print("="*70)

    if not navigation_service.has_graph(request.floor):
        raise HTTPException(
            status_code=404,
            detail=f"No navigation graph found for floor {request.floor}. Please upload a floor plan first."
        )

    result = navigation_service.get_navigation_path(
        source_name=request.source,
        dest_name=request.destination,
        floor=request.floor,
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find a path from '{request.source}' to '{request.destination}'. "
                   f"Please check the location names."
        )

    print(f"[API /navigation/path] <<< SUCCESS: {len(result['path'])} waypoints")
    return result

@app.get("/navigation/locations")
async def get_navigation_locations(floor: int = Query(1)):
    """Returns all known location nodes for a floor (for autocomplete/debugging)."""
    entry = navigation_service.load_graph(floor)
    if not entry:
        raise HTTPException(status_code=404, detail=f"No navigation graph for floor {floor}")
    
    nodes = entry["graph_data"].get("nodes", [])
    return {
        "floor": floor,
        "locations": [{"id": n["id"], "label": n["label"], "type": n.get("type", "room"), "x": n.get("x", 0), "y": n.get("y", 0)} for n in nodes]
    }
