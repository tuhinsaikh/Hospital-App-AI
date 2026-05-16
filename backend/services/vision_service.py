import os
import json
import re
import base64
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI

class VisionService:
    def __init__(self):
        self.provider = os.getenv("VISION_PROVIDER", "local").lower()
        
    def _get_vision_llm(self, temperature=0.1):
        if self.provider == "gemini":
            # Requires GOOGLE_API_KEY to be set
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key or api_key == "your_gemini_api_key_here":
                raise ValueError("GOOGLE_API_KEY not set for Gemini Vision.")
            print(f"[VISION_SERVICE] Using Gemini Vision (gemini-1.5-flash)")
            return ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=temperature)
        else:
            # Default to local (Ollama)
            base_url = os.getenv("OLLAMA_BASE_URL") or "http://192.168.1.202:11434"
            model = os.getenv("OLLAMA_VISION_MODEL") or "gemma3:27b"
            print(f"[VISION_SERVICE] Using local Ollama Vision: model={model}, base_url={base_url}")
            return ChatOllama(base_url=base_url, model=model, temperature=temperature)

    def extract_floor_plan_from_image(self, file_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """
        Uses a Vision-Language Model to extract structured details about the floor plan
        from the provided image bytes.
        """
        llm = self._get_vision_llm()
        
        # Base64 encode the image
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        prompt_text = (
            "You are an expert Hospital Layout Architect. "
            "Please analyze this image of a hospital floor plan and extract a highly detailed textual description of it. "
            "List all the floors, departments, rooms, and prominent paths shown in the image. "
            "Structure your output cleanly so it can be used in a vector database for answering navigation questions."
        )
        
        # Construct the multimodal message
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                },
            ]
        )
        
        try:
            # Invoke the VLM
            print(f"[VISION_SERVICE] Sending image to VLM...")
            response = llm.invoke([message])
            print(f"[VISION_SERVICE] VLM response received. Length={len(response.content)}")
            print(f"[VISION_SERVICE] Response preview: {response.content[:300]}...")
            return response.content
        except Exception as e:
            print(f"[VISION_SERVICE] ERROR: {e}")
            raise Exception(f"Failed to process image with Vision model ({self.provider}): {str(e)}")

    def extract_navigation_graph_from_image(
        self, file_bytes: bytes, mime_type: str,
        image_width: int, image_height: int
    ) -> dict:
        """
        Uses Vision LLM to extract a structured navigation graph from the floor plan image.
        Coordinates are in actual image pixel space: (0,0) top-left to (width, height) bottom-right.

        The extraction is fully DYNAMIC — no hardcoded room types.
        The LLM identifies whatever locations exist in this specific floor plan.

        Returns: {
            "nodes": [{"id": "...", "label": "...", "x": int, "y": int, "type": "..."}, ...],
            "edges": [{"from": "...", "to": "..."}, ...]
        }
        """
        print(f"\n[VISION_SERVICE] Extracting navigation graph (image: {image_width}x{image_height})...")
        llm = self._get_vision_llm(temperature=0)

        base64_image = base64.b64encode(file_bytes).decode('utf-8')

        prompt_text = (
            "You are a spatial extraction engine for indoor hospital navigation.\n\n"
            "You are NOT describing the image.\n"
            "You are generating PRECISE navigation geometry.\n\n"
            "IMAGE SIZE:\n"
            f"- Width: {image_width}px\n"
            f"- Height: {image_height}px\n\n"
            "COORDINATE SYSTEM:\n"
            "- Origin (0,0) is TOP LEFT\n"
            "- X increases LEFT → RIGHT\n"
            "- Y increases TOP → BOTTOM\n\n"
            "GRID SYSTEM:\n"
            "- Divide the image into a virtual square grid.\n"
            "- Each grid cell is 50px × 50px.\n"
            "- Use this grid to reason about exact geometry and alignment.\n\n"
            "TASK:\n\n"
            "Analyze the hospital floor plan and generate a NAVIGATION GRAPH.\n\n"
            "You must identify:\n\n"
            "1. WALKABLE NODES\n"
            "2. CORRIDOR CENTERLINES\n"
            "3. ROOM DOORWAY CONNECTIONS\n"
            "4. JUNCTION TURN POINTS\n"
            "5. POLYLINE ROUTES\n\n"
            "CRITICAL GEOMETRY RULES:\n\n"
            "1. ALL coordinates must lie on walkable areas only.\n\n"
            "2. Room nodes:\n"
            "   - Place the node at the ROOM DOORWAY, NOT room center.\n"
            "   - Door nodes must align exactly with corridor edges.\n\n"
            "3. Corridor nodes:\n"
            "   - Place corridor nodes at corridor CENTERLINES.\n"
            "   - Use the middle of the hallway width.\n\n"
            "4. Junction nodes:\n"
            "   - Create nodes wherever hallways:\n"
            "     - intersect\n"
            "     - turn\n"
            "     - split\n"
            "     - connect to stairs/lifts\n\n"
            "5. Coordinate snapping:\n"
            "   - Snap coordinates to nearest 5px increment.\n"
            "   - Example:\n"
            "     GOOD: (250, 405)\n"
            "     BAD: (247, 403)\n\n"
            "6. Polyline generation:\n"
            "   - Every edge must contain a walkable polyline.\n"
            "   - Polylines must follow corridor shapes exactly.\n"
            "   - Use ONLY orthogonal movement:\n"
            "     - horizontal\n"
            "     - vertical\n"
            "   - Avoid diagonal segments unless clearly visible.\n\n"
            "7. Corridor following:\n"
            "   - Never draw paths through walls.\n"
            "   - Never cut across rooms.\n"
            "   - Never use straight-line shortcuts.\n\n"
            "8. Graph connectivity:\n"
            "   - EVERY room must connect to corridor network.\n"
            "   - No isolated nodes.\n\n"
            "9. Path bend points:\n"
            "   - Add bend points wherever hallway changes direction.\n\n"
            "10. Spatial precision:\n"
            "   - Maintain visual alignment with the image layout.\n"
            "   - Coordinate placement accuracy is more important than semantic labeling.\n\n"
            "NODE TYPES:\n"
            "- room_entry\n"
            "- corridor_junction\n"
            "- stair_entry\n"
            "- lift_entry\n"
            "- entrance\n"
            "- exit\n"
            "- unknown\n\n"
            "OUTPUT FORMAT:\n\n"
            "{\n"
            '  "nodes": [\n'
            '    {\n'
            '      "id": "female_ward_entry",\n'
            '      "label": "Female Ward",\n'
            '      "type": "room_entry",\n'
            '      "x": 450,\n'
            '      "y": 300\n'
            '    }\n'
            '  ],\n\n'
            '  "edges": [\n'
            '    {\n'
            '      "from": "corridor_junction_1",\n'
            '      "to": "female_ward_entry",\n'
            '      "polyline": [\n'
            '        {"x": 300, "y": 300},\n'
            '        {"x": 450, "y": 300}\n'
            '      ]\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
            "STRICT RULES:\n"
            "- Output ONLY JSON\n"
            "- No markdown\n"
            "- No explanations\n"
            "- No comments\n"
            "- No extra text"
        )

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                },
            ]
        )

        try:
            print(f"[VISION_SERVICE] Sending image to VLM for graph extraction...")
            response = llm.invoke([message])
            raw_text = response.content
            print(f"[VISION_SERVICE] VLM graph response received. Length={len(raw_text)}")
            print(f"[VISION_SERVICE] Raw response preview: {raw_text[:500]}...")

            # Parse JSON from the response (handle markdown code fences if present)
            graph_data = self._parse_graph_json(raw_text)

            # Validate the graph
            graph_data = self._validate_graph(graph_data, image_width, image_height)

            print(f"[VISION_SERVICE] Graph extraction complete: "
                  f"{len(graph_data['nodes'])} nodes, {len(graph_data['edges'])} edges")
            return graph_data

        except Exception as e:
            print(f"[VISION_SERVICE] Graph extraction ERROR: {e}")
            raise Exception(f"Failed to extract navigation graph: {str(e)}")

    def _parse_graph_json(self, raw_text: str) -> dict:
        """Parse JSON from VLM response, handling markdown code fences."""
        # Try direct JSON parse first
        text = raw_text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code fences: ```json ... ``` or ``` ... ```
        code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding the first { ... } block
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not parse JSON from VLM response: {text[:200]}...")

    def _validate_graph(self, graph: dict, img_width: int, img_height: int) -> dict:
        """Validate and clean the extracted navigation graph."""
        if "nodes" not in graph or "edges" not in graph:
            raise ValueError("Graph must have 'nodes' and 'edges' keys")

        # Build set of valid node IDs
        node_ids = set()
        valid_nodes = []
        for node in graph["nodes"]:
            if not all(k in node for k in ("id", "label", "x", "y")):
                print(f"[VISION_SERVICE] WARNING: Skipping node missing required fields: {node}")
                continue
            # Clamp coordinates to image bounds
            node["x"] = max(0, min(int(node["x"]), img_width))
            node["y"] = max(0, min(int(node["y"]), img_height))
            # Ensure type exists
            if "type" not in node:
                node["type"] = "room_entry"
            
            # Remove door property if it exists, since doors are now their own nodes
            if "door" in node:
                node.pop("door", None)
                
            node_ids.add(node["id"])
            valid_nodes.append(node)

        # Filter edges to only reference valid nodes
        valid_edges = []
        for edge in graph["edges"]:
            if edge.get("from") in node_ids and edge.get("to") in node_ids:
                # Support new 'polyline' schema or fallback to 'path'/'waypoints' for backwards compat during migration
                route_points = edge.get("polyline") or edge.get("path") or edge.get("waypoints")
                
                if isinstance(route_points, list):
                    cleaned_points = []
                    for point in route_points:
                        if isinstance(point, dict) and "x" in point and "y" in point:
                            cleaned_points.append({
                                "x": max(0, min(int(point["x"]), img_width)),
                                "y": max(0, min(int(point["y"]), img_height)),
                            })
                    if cleaned_points:
                        edge["polyline"] = cleaned_points
                    
                    # Clean up old fields
                    edge.pop("path", None)
                    edge.pop("waypoints", None)
                valid_edges.append(edge)
            else:
                print(f"[VISION_SERVICE] WARNING: Skipping edge with invalid node ref: {edge}")

        print(f"[VISION_SERVICE] Validation: {len(valid_nodes)}/{len(graph['nodes'])} nodes, "
              f"{len(valid_edges)}/{len(graph['edges'])} edges valid")

        return {"nodes": valid_nodes, "edges": valid_edges}

# Singleton instance
vision_service = VisionService()
