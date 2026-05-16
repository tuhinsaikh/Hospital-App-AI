"""
Grid-Based Graph Extractor -- Step-by-step room/block extraction using grid overlay + VLM.

Workflow:
  Step 1: Load static image -> draw grid lines -> save debug image
  Step 2: Send gridded image to Gemma VLM -> get room/block bounding boxes
  Step 3: Convert each room/block -> single node with full dimensions

Usage:
  python -m backend.services.grid_graph_extractor
"""

import os
import io
import json
import re
import base64
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama


# ─────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────

# Grid cell size in pixels
GRID_SIZE = 50

# Static test image (change this to your floor plan path)
DEFAULT_IMAGE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "static", "maps", "floor_1_530880fd.jpg"
)

# Output directory for debug images
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "tmp", "grid_debug")


# ─────────────────────────────────────────────────────────────────────
#  STEP 1: Draw Grid Lines on Image
# ─────────────────────────────────────────────────────────────────────

def draw_grid_on_image(
    image_path: str,
    grid_size: int = GRID_SIZE,
    output_path: str | None = None,
) -> tuple[Image.Image, str]:
    """
    Load an image, draw a visible grid overlay, label grid coordinates,
    and save the result.

    Returns:
        (gridded_image, output_file_path)
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # Try to use a small font for labels; fallback to default
    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Colors
    line_color = (255, 0, 0, 128)       # Semi-transparent red
    label_color = (255, 0, 0)           # Red text
    major_line_color = (0, 0, 255)      # Blue for every 5th line (250px)

    # ── Vertical lines ──
    col = 0
    for x in range(0, w + 1, grid_size):
        is_major = (col % 5 == 0)
        color = major_line_color if is_major else line_color
        width = 2 if is_major else 1
        draw.line([(x, 0), (x, h)], fill=color, width=width)

        # Label at the top
        draw.text((x + 2, 2), str(x), fill=label_color, font=font)
        col += 1

    # ── Horizontal lines ──
    row = 0
    for y in range(0, h + 1, grid_size):
        is_major = (row % 5 == 0)
        color = major_line_color if is_major else line_color
        width = 2 if is_major else 1
        draw.line([(0, y), (w, y)], fill=color, width=width)

        # Label at the left edge
        draw.text((2, y + 2), str(y), fill=label_color, font=font)
        row += 1

    # ── Grid info ──
    cols_count = w // grid_size
    rows_count = h // grid_size
    info_text = f"Image: {w}x{h} | Grid: {grid_size}px | Cols: {cols_count} | Rows: {rows_count}"
    draw.text((10, h - 20), info_text, fill=(255, 255, 0), font=font)

    # Save
    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        basename = Path(image_path).stem
        output_path = os.path.join(OUTPUT_DIR, f"{basename}_grid.png")

    img.save(output_path)
    print(f"[GRID] Saved gridded image -> {output_path}")
    print(f"[GRID] Image size: {w}x{h}")
    print(f"[GRID] Grid cells: {cols_count} cols x {rows_count} rows")

    return img, output_path


# ─────────────────────────────────────────────────────────────────────
#  STEP 2: Use VLM to Extract Room/Block Bounding Boxes
# ─────────────────────────────────────────────────────────────────────

def _get_vlm(temperature: float = 0.0) -> ChatOllama:
    """Get the Gemma VLM instance from Ollama."""
    base_url = os.getenv("OLLAMA_BASE_URL") or "http://192.168.1.202:11434"
    model = os.getenv("OLLAMA_VISION_MODEL") or "gemma3:27b"
    print(f"[VLM] Using model={model}, base_url={base_url}")
    return ChatOllama(base_url=base_url, model=model, temperature=temperature)


def _image_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    """Convert a PIL Image to base64 string."""
    buffer = io.BytesIO()
    img.save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def extract_room_boundaries_with_vlm(
    gridded_image: Image.Image,
    grid_size: int = GRID_SIZE,
) -> list[dict]:
    """
    Send the gridded image to Gemma VLM and ask it to identify each room/block
    with its bounding box coordinates (using the grid lines as reference).

    Returns a list of room dicts:
    [
        {
            "id": "men_restroom",
            "label": "Men",
            "type": "room",
            "x_min": 50,   # left edge (grid-snapped)
            "y_min": 100,  # top edge (grid-snapped)
            "x_max": 200,  # right edge (grid-snapped)
            "y_max": 250,  # bottom edge (grid-snapped)
        },
        ...
    ]
    """
    w, h = gridded_image.size
    base64_img = _image_to_base64(gridded_image)

    prompt = (
        "You are a precise spatial geometry engine.\n\n"
        "I have overlaid a RED GRID on a hospital floor plan image.\n"
        f"- Grid cell size: {grid_size}px x {grid_size}px\n"
        f"- Image size: {w}px wide x {h}px tall\n"
        "- Grid numbers are labeled along the top (X) and left (Y) edges.\n"
        "- RED lines = minor grid (every 50px)\n"
        "- BLUE lines = major grid (every 250px)\n\n"
        "YOUR TASK:\n"
        "Identify EVERY room, block, corridor, and labeled area in this floor plan.\n"
        "For each one, provide its BOUNDING BOX using the grid coordinates.\n\n"
        "RULES:\n"
        f"1. All coordinates MUST be multiples of {grid_size} (snapped to grid).\n"
        "2. The bounding box must tightly enclose the WALLS of each room/block.\n"
        "3. Use the grid numbers visible in the image to determine exact positions.\n"
        "4. Include corridors and hallways as separate blocks.\n"
        "5. Include stairs, lobbies, waiting areas -- everything with a label or clear boundary.\n"
        "6. For type, use one of: room, corridor, staircase, lobby, nurse_station, restroom, waiting_area, store, unknown\n\n"
        "OUTPUT FORMAT (JSON array only, no markdown, no explanation):\n\n"
        "[\n"
        "  {\n"
        '    "id": "unique_snake_case_id",\n'
        '    "label": "Human Readable Name",\n'
        '    "type": "room",\n'
        f'    "x_min": 100,\n'
        f'    "y_min": 150,\n'
        f'    "x_max": 300,\n'
        f'    "y_max": 350\n'
        "  }\n"
        "]\n\n"
        "STRICT: Output ONLY the JSON array. No text before or after."
    )

    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_img}"},
            },
        ]
    )

    llm = _get_vlm(temperature=0.0)
    print(f"[VLM] Sending gridded image ({w}x{h}) for room boundary extraction...")
    response = llm.invoke([message])
    raw = response.content
    print(f"[VLM] Response length: {len(raw)}")
    print(f"[VLM] Response preview:\n{raw[:600]}")

    # Parse JSON
    rooms = _parse_room_json(raw)

    # Validate & snap to grid
    rooms = _validate_rooms(rooms, w, h, grid_size)

    print(f"[VLM] Extracted {len(rooms)} rooms/blocks")
    return rooms


def _parse_room_json(raw_text: str) -> list[dict]:
    """Parse the VLM response into a list of room dicts."""
    text = raw_text.strip()

    # Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "rooms" in result:
            return result["rooms"]
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown fences
    code_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if code_match:
        try:
            result = json.loads(code_match.group(1).strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Try finding [ ... ] block
    bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse room JSON from VLM response:\n{text[:300]}...")


def _validate_rooms(
    rooms: list[dict],
    img_w: int,
    img_h: int,
    grid_size: int,
) -> list[dict]:
    """Validate room bounding boxes: snap to grid, clamp to image bounds."""
    valid = []
    for room in rooms:
        required = {"id", "label", "x_min", "y_min", "x_max", "y_max"}
        if not required.issubset(room.keys()):
            print(f"[VALIDATE] Skipping room missing fields: {room}")
            continue

        # Snap to grid
        for key in ("x_min", "y_min", "x_max", "y_max"):
            val = int(room[key])
            snapped = round(val / grid_size) * grid_size
            room[key] = snapped

        # Clamp to image bounds
        room["x_min"] = max(0, min(room["x_min"], img_w))
        room["y_min"] = max(0, min(room["y_min"], img_h))
        room["x_max"] = max(0, min(room["x_max"], img_w))
        room["y_max"] = max(0, min(room["y_max"], img_h))

        # Ensure min < max
        if room["x_min"] >= room["x_max"] or room["y_min"] >= room["y_max"]:
            print(f"[VALIDATE] Skipping degenerate room: {room['id']} "
                  f"({room['x_min']},{room['y_min']}) -> ({room['x_max']},{room['y_max']})")
            continue

        # Default type
        if "type" not in room:
            room["type"] = "room"

        valid.append(room)

    return valid


# ─────────────────────────────────────────────────────────────────────
#  STEP 3: Convert Room Bounding Boxes -> Navigation Nodes
# ─────────────────────────────────────────────────────────────────────

def rooms_to_nodes(rooms: list[dict]) -> list[dict]:
    """
    Convert room bounding boxes into navigation nodes.
    Each room becomes ONE node positioned at the center of its bounding box,
    with full dimension metadata.

    Returns:
    [
        {
            "id": "men_restroom",
            "label": "Men",
            "type": "room",
            "x": 125,          # center X
            "y": 175,          # center Y
            "bbox": {
                "x_min": 50,
                "y_min": 100,
                "x_max": 200,
                "y_max": 250,
            },
            "width": 150,
            "height": 150,
        },
        ...
    ]
    """
    nodes = []
    for room in rooms:
        cx = (room["x_min"] + room["x_max"]) // 2
        cy = (room["y_min"] + room["y_max"]) // 2
        bw = room["x_max"] - room["x_min"]
        bh = room["y_max"] - room["y_min"]

        node = {
            "id": room["id"],
            "label": room["label"],
            "type": room.get("type", "room"),
            "x": cx,
            "y": cy,
            "bbox": {
                "x_min": room["x_min"],
                "y_min": room["y_min"],
                "x_max": room["x_max"],
                "y_max": room["y_max"],
            },
            "width": bw,
            "height": bh,
        }
        nodes.append(node)

    return nodes


# ─────────────────────────────────────────────────────────────────────
#  VISUALIZATION: Draw room boxes on the image for debugging
# ─────────────────────────────────────────────────────────────────────

def draw_rooms_on_image(
    image_path: str,
    rooms: list[dict],
    output_path: str | None = None,
) -> str:
    """
    Draw the extracted room bounding boxes on the original image
    so you can visually verify accuracy.
    """
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Color palette for different room types
    type_colors = {
        "room":          (0, 200, 0),       # Green
        "corridor":      (0, 150, 255),     # Blue
        "staircase":     (255, 165, 0),     # Orange
        "lobby":         (255, 0, 255),     # Magenta
        "nurse_station": (255, 50, 50),     # Red
        "restroom":      (0, 200, 200),     # Cyan
        "waiting_area":  (200, 200, 0),     # Yellow
        "store":         (128, 0, 255),     # Purple
        "unknown":       (128, 128, 128),   # Gray
    }

    for room in rooms:
        color = type_colors.get(room.get("type", "unknown"), (128, 128, 128))
        x_min = room["x_min"]
        y_min = room["y_min"]
        x_max = room["x_max"]
        y_max = room["y_max"]

        # Draw bounding box
        draw.rectangle([x_min, y_min, x_max, y_max], outline=color, width=3)

        # Draw center dot
        cx = (x_min + x_max) // 2
        cy = (y_min + y_max) // 2
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=color)

        # Label
        label = f"{room['label']} ({x_min},{y_min})-({x_max},{y_max})"
        draw.text((x_min + 4, y_min + 4), label, fill=color, font=font)

    # Save
    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        basename = Path(image_path).stem
        output_path = os.path.join(OUTPUT_DIR, f"{basename}_rooms.png")

    img.save(output_path)
    print(f"[VIZ] Saved room visualization → {output_path}")
    return output_path


# ─────────────────────────────────────────────────────────────────────
#  MAIN: Run the full pipeline
# ─────────────────────────────────────────────────────────────────────

def run_pipeline(image_path: str | None = None, grid_size: int = GRID_SIZE):
    """
    Run the full extraction pipeline:
      1. Draw grid → save debug image
      2. Send to VLM → get room bounding boxes
      3. Convert to nodes → save results
    """
    if image_path is None:
        image_path = DEFAULT_IMAGE_PATH

    image_path = os.path.abspath(image_path)
    print(f"\n{'='*70}")
    print(f"  GRID GRAPH EXTRACTOR — Pipeline Start")
    print(f"  Image: {image_path}")
    print(f"  Grid size: {grid_size}px")
    print(f"{'='*70}\n")

    # ── STEP 1: Grid Overlay ──
    print("─── STEP 1: Drawing grid overlay ───")
    gridded_img, grid_path = draw_grid_on_image(image_path, grid_size)
    print(f"    → Grid image saved: {grid_path}\n")

    # ── STEP 2: VLM Room Extraction ──
    print("─── STEP 2: Extracting rooms with VLM ───")
    rooms = extract_room_boundaries_with_vlm(gridded_img, grid_size)
    print(f"    → Found {len(rooms)} rooms/blocks\n")

    # ── STEP 3: Convert to Nodes ──
    print("─── STEP 3: Converting to navigation nodes ───")
    nodes = rooms_to_nodes(rooms)
    for n in nodes:
        print(f"    [{n['type']:15s}] {n['label']:25s} center=({n['x']:4d},{n['y']:4d}) "
              f"size={n['width']}×{n['height']}")

    # ── Visualize rooms on original image ──
    print("\n─── Visualization ───")
    viz_path = draw_rooms_on_image(image_path, rooms)
    print(f"    → Room visualization saved: {viz_path}")

    # ── Save JSON output ──
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    basename = Path(image_path).stem
    json_path = os.path.join(OUTPUT_DIR, f"{basename}_rooms.json")

    output = {
        "image_path": image_path,
        "image_width": gridded_img.size[0],
        "image_height": gridded_img.size[1],
        "grid_size": grid_size,
        "rooms": rooms,
        "nodes": nodes,
    }

    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"    → JSON results saved: {json_path}")

    print(f"\n{'='*70}")
    print(f"  Pipeline Complete!")
    print(f"  Grid image:  {grid_path}")
    print(f"  Room viz:    {viz_path}")
    print(f"  JSON output: {json_path}")
    print(f"{'='*70}\n")

    return output


# ─────────────────────────────────────────────────────────────────────
#  CLI Entry Point
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    img_path = sys.argv[1] if len(sys.argv) > 1 else None
    grid = int(sys.argv[2]) if len(sys.argv) > 2 else GRID_SIZE

    # Load env for Ollama config
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    run_pipeline(img_path, grid)
