import os
import json
import re
import base64
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.services.cv_service import cv_service

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
            "You are analyzing a hospital floor plan image.\n\n"
            f"IMAGE DIMENSIONS: {image_width} pixels wide × {image_height} pixels tall.\n\n"
            "TASK: Identify EVERY distinct location visible in this floor plan — this includes "
            "but is not limited to: rooms, departments, offices, corridors, junctions, "
            "staircases, elevators, entrances, exits, waiting areas, nurse stations, "
            "restrooms, or ANY other labeled or identifiable area.\n\n"
            "Every hospital is different. Do NOT assume which rooms exist — extract "
            "ONLY what you can actually see in this specific image.\n\n"
            "For each location:\n"
            "1. Assign a unique snake_case ID based on its name\n"
            "2. Provide its human-readable label exactly as shown in the image\n"
            "3. Estimate its CENTER position as pixel coordinates where:\n"
            f"   - (0, 0) = top-left corner of the image\n"
            f"   - ({image_width}, {image_height}) = bottom-right corner\n"
            "   Scale positions proportionally to the actual image dimensions.\n"
            "4. Assign a type that best describes it (e.g., 'room', 'corridor', "
            "'junction', 'staircase', 'elevator', 'entrance', 'restroom', "
            "'nurse_station', 'waiting_area', or any other appropriate type)\n"
            "5. When a room or department has a visible door/opening, include an optional "
            '"door": {"x": pixel_x, "y": pixel_y} coordinate at that doorway. '
            "Use the door point for walkable routing, not the room center.\n\n"
            "Then identify which locations are directly connected (share a door, "
            "hallway, or walkable path between them).\n\n"
            "IMPORTANT: \n"
            "- Also add corridor junction nodes where hallways intersect — these are critical for accurate pathfinding.\n"
            "- CRITICAL: The graph MUST be fully connected. Ensure EVERY room is connected to a corridor or junction. Do NOT leave any nodes isolated without edges.\n"
            "- Use the exact node IDs in the 'from' and 'to' fields of the edges.\n\n"
            "For each edge, include a 'path' array when the walking route is not a straight "
            "door-to-door segment. The path array is ordered bend points along corridors and "
            "should use 90-degree/L-shaped turns where the corridor does. Example: "
            '{"from": "room_a", "to": "junction_1", "path": [{"x": 220, "y": 310}, {"x": 360, "y": 310}]}.\n\n'
            "Output ONLY valid JSON (no markdown, no code fences, no explanation) with this exact schema:\n"
            "{\n"
            '  "nodes": [\n'
            '    {"id": "main_entrance", "label": "Main Entrance", "x": 150, "y": 400, "type": "entrance", "door": {"x": 150, "y": 430}},\n'
            '    {"id": "corridor_1", "label": "Main Corridor", "x": 300, "y": 400, "type": "corridor"},\n'
            "    ...\n"
            "  ],\n"
            '  "edges": [\n'
            '    {"from": "main_entrance", "to": "corridor_1", "path": [{"x": 150, "y": 430}, {"x": 300, "y": 430}]},\n'
            "    ...\n"
            "  ]\n"
            "}"
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

    def extract_hybrid_navigation_graph(
        self, file_bytes: bytes, mime_type: str,
        image_width: int, image_height: int
    ) -> dict:
        """
        Uses OpenCV for deterministic geometry and VLM only for labels.
        """
        print(f"\n[VISION_SERVICE] Extracting HYBRID navigation graph (image: {image_width}x{image_height})...")
        
        # Phase 1: CV Geometry
        regions = cv_service.extract_room_geometry(file_bytes, image_width, image_height)
        
        # Phase 2: VLM Labels
        llm = self._get_vision_llm(temperature=0)
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        prompt_text = (
            "You are analyzing a hospital floor plan image.\n"
            "TASK: List EVERY distinct room name or label visible in this image.\n"
            "For each label, describe its approximate position using ONLY these grid sections:\n"
            "'top-left', 'top-center', 'top-right', 'middle-left', 'center', 'middle-right', 'bottom-left', 'bottom-center', 'bottom-right'.\n\n"
            "Output ONLY valid JSON representing an array of objects:\n"
            "[\n"
            "  {\"label\": \"MEN\", \"position\": \"bottom-left\"},\n"
            "  {\"label\": \"FEMALE WARD\", \"position\": \"middle-right\"}\n"
            "]"
        )
        
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
            ]
        )
        
        try:
            print("[VISION_SERVICE] Sending image to VLM for labels...")
            response = llm.invoke([message])
            raw_text = response.content
            print(f"[VISION_SERVICE] VLM labels response: {raw_text[:200]}...")
            
            # Parse labels array
            labels_data = []
            try:
                # Same JSON parsing logic but for array
                text = raw_text.strip()
                code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
                if code_block_match:
                    text = code_block_match.group(1).strip()
                else:
                    bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
                    if bracket_match:
                        text = bracket_match.group(0)
                labels_data = json.loads(text)
            except Exception as e:
                print(f"[VISION_SERVICE] Could not parse labels JSON: {e}")
                labels_data = []
                
            # Phase 3: Proximity Matching
            nodes = []
            used_regions = set()
            
            # Group regions by position
            regions_by_pos = {}
            for r in regions:
                pos = r["grid_position"]
                if pos not in regions_by_pos:
                    regions_by_pos[pos] = []
                regions_by_pos[pos].append(r)
                
            # Match labels to regions
            for label_obj in labels_data:
                label_text = label_obj.get("label", "Unknown")
                pos = label_obj.get("position", "center")
                
                # Sanitize ID
                node_id = re.sub(r'[^a-z0-9]', '_', label_text.lower().strip())
                
                # Find matching region
                matched_region = None
                if pos in regions_by_pos and regions_by_pos[pos]:
                    # For simplicity, pick the first available region in that section
                    # that hasn't been used, or just pop it
                    for r in regions_by_pos[pos]:
                        if r["id"] not in used_regions:
                            matched_region = r
                            used_regions.add(r["id"])
                            break
                            
                if matched_region:
                    nodes.append({
                        "id": node_id,
                        "label": label_text,
                        "x": matched_region["x"],
                        "y": matched_region["y"],
                        "type": "room"
                    })
                else:
                    # If no region found, just place it randomly or skip it
                    # Let's place it at center
                    nodes.append({
                        "id": node_id,
                        "label": label_text,
                        "x": image_width // 2,
                        "y": image_height // 2,
                        "type": "room"
                    })
                    
            # Add any unmatched regions as "Unknown" rooms
            unmatched_count = 0
            for r in regions:
                if r["id"] not in used_regions:
                    nodes.append({
                        "id": f"unknown_{unmatched_count}",
                        "label": "Unknown Area",
                        "x": r["x"],
                        "y": r["y"],
                        "type": "room"
                    })
                    unmatched_count += 1
                    
            # Generate edges: Connect everything to a central corridor node for simplicity in V1
            corridor_id = "main_corridor"
            nodes.append({
                "id": corridor_id,
                "label": "Main Corridor",
                "x": image_width // 2,
                "y": image_height // 2,
                "type": "corridor"
            })
            
            edges = []
            for n in nodes:
                if n["id"] != corridor_id:
                    edges.append({
                        "from": n["id"],
                        "to": corridor_id,
                        "path": [{"x": n["x"], "y": n["y"]}, {"x": image_width // 2, "y": image_height // 2}]
                    })
                    
            return self._validate_graph({"nodes": nodes, "edges": edges}, image_width, image_height)
            
        except Exception as e:
            print(f"[VISION_SERVICE] Hybrid graph extraction ERROR: {e}")
            raise Exception(f"Failed to extract hybrid navigation graph: {str(e)}")

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
                node["type"] = "room"
            if isinstance(node.get("door"), dict) and "x" in node["door"] and "y" in node["door"]:
                node["door"]["x"] = max(0, min(int(node["door"]["x"]), img_width))
                node["door"]["y"] = max(0, min(int(node["door"]["y"]), img_height))
            elif "door" in node:
                node.pop("door", None)
            node_ids.add(node["id"])
            valid_nodes.append(node)

        # Filter edges to only reference valid nodes
        valid_edges = []
        for edge in graph["edges"]:
            if edge.get("from") in node_ids and edge.get("to") in node_ids:
                route_points = edge.get("path")
                if route_points is None:
                    route_points = edge.get("waypoints")
                if isinstance(route_points, list):
                    cleaned_points = []
                    for point in route_points:
                        if isinstance(point, dict) and "x" in point and "y" in point:
                            cleaned_points.append({
                                "x": max(0, min(int(point["x"]), img_width)),
                                "y": max(0, min(int(point["y"]), img_height)),
                            })
                    if cleaned_points:
                        edge["path"] = cleaned_points
                    edge.pop("waypoints", None)
                valid_edges.append(edge)
            else:
                print(f"[VISION_SERVICE] WARNING: Skipping edge with invalid node ref: {edge}")

        print(f"[VISION_SERVICE] Validation: {len(valid_nodes)}/{len(graph['nodes'])} nodes, "
              f"{len(valid_edges)}/{len(graph['edges'])} edges valid")

        return {"nodes": valid_nodes, "edges": valid_edges}

# Singleton instance
vision_service = VisionService()
