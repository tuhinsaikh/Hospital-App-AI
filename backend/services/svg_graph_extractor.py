"""
SVG-Based Graph Extractor -- Parses SVG floor plans directly.

Since SVG is structured XML, we can extract room boundaries, labels, and
wall lines WITHOUT any VLM or OpenCV. The geometry is already precise.

Workflow:
  1. Parse SVG XML -> extract all shapes (rect, path, polygon, line, text)
  2. Identify rooms = enclosed shapes with associated text labels
  3. Convert each room -> navigation node with exact bounding box
  4. Optionally use VLM only for semantic classification (room type)

Usage:
  python -m backend.services.svg_graph_extractor path/to/floor.svg
"""

import os
import re
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Optional

# SVG namespace
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Register SVG namespace so we can search elements
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


# ---------------------------------------------------------------
#  Data Models
# ---------------------------------------------------------------

@dataclass
class BBox:
    """Axis-aligned bounding box."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2

    def contains_point(self, x: float, y: float, margin: float = 0) -> bool:
        return (self.x_min - margin <= x <= self.x_max + margin and
                self.y_min - margin <= y <= self.y_max + margin)

    def area(self) -> float:
        return self.width * self.height


@dataclass
class SVGShape:
    """A shape extracted from the SVG."""
    tag: str                    # rect, path, polygon, etc.
    bbox: BBox
    element_id: Optional[str] = None
    css_class: Optional[str] = None
    fill: Optional[str] = None
    stroke: Optional[str] = None
    raw_attribs: dict = field(default_factory=dict)


@dataclass
class SVGTextLabel:
    """A text label extracted from the SVG."""
    text: str
    x: float
    y: float
    font_size: float = 12.0


@dataclass
class Room:
    """A room/block extracted from the SVG with its label and geometry."""
    id: str
    label: str
    room_type: str
    bbox: BBox
    center_x: float
    center_y: float
    width: float
    height: float


# ---------------------------------------------------------------
#  SVG Parser
# ---------------------------------------------------------------

class SVGFloorPlanParser:
    """
    Parse an SVG floor plan and extract:
      - Room shapes (rects, paths, polygons)
      - Text labels
      - Wall lines
    """

    def __init__(self, svg_path: str):
        self.svg_path = svg_path
        self.tree = ET.parse(svg_path)
        self.root = self.tree.getroot()

        # Get SVG dimensions
        self.svg_width = self._parse_dimension(self.root.get("width", "0"))
        self.svg_height = self._parse_dimension(self.root.get("height", "0"))

        # Try viewBox if width/height aren't set
        viewbox = self.root.get("viewBox")
        if viewbox and (self.svg_width == 0 or self.svg_height == 0):
            parts = viewbox.split()
            if len(parts) == 4:
                self.svg_width = float(parts[2])
                self.svg_height = float(parts[3])

        print(f"[SVG] Loaded: {svg_path}")
        print(f"[SVG] Dimensions: {self.svg_width} x {self.svg_height}")

    @staticmethod
    def _parse_dimension(val: str) -> float:
        """Parse dimension string like '1400', '1400px', '100%'."""
        if not val:
            return 0.0
        # Remove units
        val = val.strip().replace("px", "").replace("pt", "").replace("mm", "").replace("cm", "")
        try:
            return float(val)
        except ValueError:
            return 0.0

    def _ns(self, tag: str) -> str:
        """Add SVG namespace to tag."""
        return f"{{{SVG_NS}}}{tag}"

    def _find_all(self, tag: str) -> list:
        """Find all elements with given tag (handles namespace)."""
        # Try with namespace
        results = self.root.iter(self._ns(tag))
        results_list = list(results)
        if not results_list:
            # Try without namespace
            results_list = list(self.root.iter(tag))
        return results_list

    # ---- Shape Extractors ----

    def extract_rects(self) -> list[SVGShape]:
        """Extract all <rect> elements."""
        shapes = []
        for elem in self._find_all("rect"):
            x = float(elem.get("x", 0))
            y = float(elem.get("y", 0))
            w = float(elem.get("width", 0))
            h = float(elem.get("height", 0))
            if w > 0 and h > 0:
                shapes.append(SVGShape(
                    tag="rect",
                    bbox=BBox(x, y, x + w, y + h),
                    element_id=elem.get("id"),
                    css_class=elem.get("class"),
                    fill=elem.get("fill") or elem.get("style", ""),
                    stroke=elem.get("stroke"),
                    raw_attribs=dict(elem.attrib),
                ))
        print(f"[SVG] Found {len(shapes)} <rect> elements")
        return shapes

    def extract_paths(self) -> list[SVGShape]:
        """Extract all <path> elements and compute their bounding boxes."""
        shapes = []
        for elem in self._find_all("path"):
            d = elem.get("d", "")
            bbox = self._path_bbox(d)
            if bbox and bbox.area() > 100:  # Skip tiny paths
                shapes.append(SVGShape(
                    tag="path",
                    bbox=bbox,
                    element_id=elem.get("id"),
                    css_class=elem.get("class"),
                    fill=elem.get("fill") or elem.get("style", ""),
                    stroke=elem.get("stroke"),
                    raw_attribs=dict(elem.attrib),
                ))
        print(f"[SVG] Found {len(shapes)} <path> elements (with area > 100)")
        return shapes

    def extract_polygons(self) -> list[SVGShape]:
        """Extract all <polygon> and <polyline> elements."""
        shapes = []
        for tag in ("polygon", "polyline"):
            for elem in self._find_all(tag):
                points_str = elem.get("points", "")
                points = self._parse_points(points_str)
                if len(points) >= 3:
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    shapes.append(SVGShape(
                        tag=tag,
                        bbox=BBox(min(xs), min(ys), max(xs), max(ys)),
                        element_id=elem.get("id"),
                        css_class=elem.get("class"),
                        fill=elem.get("fill"),
                        stroke=elem.get("stroke"),
                        raw_attribs=dict(elem.attrib),
                    ))
        print(f"[SVG] Found {len(shapes)} <polygon>/<polyline> elements")
        return shapes

    def extract_lines(self) -> list[tuple]:
        """Extract all <line> elements as (x1, y1, x2, y2) tuples."""
        lines = []
        for elem in self._find_all("line"):
            x1 = float(elem.get("x1", 0))
            y1 = float(elem.get("y1", 0))
            x2 = float(elem.get("x2", 0))
            y2 = float(elem.get("y2", 0))
            lines.append((x1, y1, x2, y2))
        print(f"[SVG] Found {len(lines)} <line> elements")
        return lines

    def extract_texts(self) -> list[SVGTextLabel]:
        """Extract all <text> elements with their positions."""
        raw_texts = []
        for elem in self._find_all("text"):
            # Get position
            x = float(elem.get("x", 0))
            y = float(elem.get("y", 0))

            # Get text content (may have nested <tspan> elements)
            text_parts = []
            if elem.text and elem.text.strip():
                text_parts.append(elem.text.strip())

            for child in elem:
                local_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if local_tag == "tspan":
                    if child.text and child.text.strip():
                        text_parts.append(child.text.strip())
                    # tspan may override position
                    if child.get("x"):
                        x = float(child.get("x"))
                    if child.get("y"):
                        y = float(child.get("y"))

            text = " ".join(text_parts)
            if text:
                # Parse font size
                font_size = 12.0
                style = elem.get("style", "")
                fs_match = re.search(r'font-size:\s*([\d.]+)', style)
                if fs_match:
                    font_size = float(fs_match.group(1))
                elif elem.get("font-size"):
                    font_size = float(elem.get("font-size", 12))

                raw_texts.append(SVGTextLabel(text=text, x=x, y=y, font_size=font_size))

        # Merge multi-line labels (same x position, close y values)
        texts = self._merge_multiline_texts(raw_texts)

        print(f"[SVG] Found {len(raw_texts)} raw text elements -> merged to {len(texts)} labels")
        return texts

    @staticmethod
    def _merge_multiline_texts(
        texts: list[SVGTextLabel],
        x_tolerance: float = 5.0,
        y_max_gap: float = 25.0,
    ) -> list[SVGTextLabel]:
        """
        Merge text labels that are at the same X position and close Y values.
        This handles multi-line labels like:
          <text x="700" y="415">NURSES'</text>
          <text x="700" y="435">STATION</text>
        -> merged to "NURSES' STATION" at (700, 415)
        """
        if not texts:
            return []

        # Sort by x then y
        sorted_texts = sorted(texts, key=lambda t: (t.x, t.y))
        merged = []
        i = 0

        while i < len(sorted_texts):
            current = sorted_texts[i]
            group_texts = [current.text]
            group_y_min = current.y

            # Look ahead for texts at same x, close y
            j = i + 1
            while j < len(sorted_texts):
                nxt = sorted_texts[j]
                if (abs(nxt.x - current.x) <= x_tolerance and
                        nxt.y - sorted_texts[j - 1].y <= y_max_gap):
                    group_texts.append(nxt.text)
                    j += 1
                else:
                    break

            merged_text = " ".join(group_texts)
            merged.append(SVGTextLabel(
                text=merged_text,
                x=current.x,
                y=group_y_min,
                font_size=current.font_size,
            ))
            i = j

        return merged

    # ---- Geometry Helpers ----

    @staticmethod
    def _parse_points(points_str: str) -> list[tuple]:
        """Parse SVG points string: '100,200 300,400' -> [(100,200), (300,400)]."""
        points = []
        pairs = re.findall(r'([\d.eE+-]+)[,\s]+([\d.eE+-]+)', points_str)
        for x_str, y_str in pairs:
            points.append((float(x_str), float(y_str)))
        return points

    @staticmethod
    def _path_bbox(d: str) -> Optional[BBox]:
        """
        Compute approximate bounding box from SVG path 'd' attribute.
        Handles M, L, H, V, Z commands (absolute). For curves, uses control points.
        """
        if not d:
            return None

        xs, ys = [], []
        # Extract all numbers from the path
        numbers = re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', d)

        if len(numbers) < 2:
            return None

        # Simple approach: pair up numbers as x,y coordinates
        i = 0
        while i + 1 < len(numbers):
            try:
                xs.append(float(numbers[i]))
                ys.append(float(numbers[i + 1]))
            except (ValueError, IndexError):
                pass
            i += 2

        if not xs or not ys:
            return None

        return BBox(min(xs), min(ys), max(xs), max(ys))

    # ---- Room Detection ----

    def extract_all_shapes(self) -> list[SVGShape]:
        """Extract all shapes from the SVG, filtering out outer borders."""
        shapes = []
        shapes.extend(self.extract_rects())
        shapes.extend(self.extract_paths())
        shapes.extend(self.extract_polygons())

        # Filter out shapes that are too large (likely outer boundary/border)
        # A room shouldn't cover more than 60% of the total image area
        total_area = self.svg_width * self.svg_height
        if total_area > 0:
            before = len(shapes)
            shapes = [s for s in shapes if s.bbox.area() < total_area * 0.6]
            filtered = before - len(shapes)
            if filtered > 0:
                print(f"[SVG] Filtered {filtered} oversized shapes (likely outer borders)")

        return shapes

    def match_labels_to_shapes(
        self,
        shapes: list[SVGShape],
        texts: list[SVGTextLabel],
        margin: float = 20.0,
    ) -> list[Room]:
        """
        Match text labels to their containing shapes.
        A text belongs to a shape if the text position is inside the shape's bbox.
        """
        rooms = []
        used_shapes = set()
        used_texts = set()

        for ti, text in enumerate(texts):
            best_shape = None
            best_area = float("inf")

            for si, shape in enumerate(shapes):
                if si in used_shapes:
                    continue
                # Check if text is inside shape bbox
                if shape.bbox.contains_point(text.x, text.y, margin=margin):
                    area = shape.bbox.area()
                    # Prefer smallest containing shape (most specific room)
                    if area < best_area:
                        best_shape = (si, shape)
                        best_area = area

            if best_shape:
                si, shape = best_shape
                used_shapes.add(si)
                used_texts.add(ti)

                room_id = self._make_id(text.text)
                room_type = self._classify_room(text.text, shape)

                rooms.append(Room(
                    id=room_id,
                    label=text.text,
                    room_type=room_type,
                    bbox=shape.bbox,
                    center_x=shape.bbox.center_x,
                    center_y=shape.bbox.center_y,
                    width=shape.bbox.width,
                    height=shape.bbox.height,
                ))

        # Report unmatched
        unmatched_texts = [texts[i] for i in range(len(texts)) if i not in used_texts]
        if unmatched_texts:
            print(f"[SVG] WARNING: {len(unmatched_texts)} texts not matched to shapes:")
            for t in unmatched_texts:
                print(f"       '{t.text}' at ({t.x}, {t.y})")

        unmatched_shapes = [shapes[i] for i in range(len(shapes)) if i not in used_shapes]
        if unmatched_shapes:
            print(f"[SVG] {len(unmatched_shapes)} shapes without labels (walls, borders, etc.)")

        return rooms

    @staticmethod
    def _make_id(label: str) -> str:
        """Convert label to snake_case id."""
        clean = re.sub(r'[^a-zA-Z0-9\s]', '', label)
        clean = re.sub(r'\s+', '_', clean.strip())
        return clean.lower()

    @staticmethod
    def _classify_room(label: str, shape: SVGShape) -> str:
        """Classify room type from label text."""
        label_lower = label.lower()

        type_keywords = {
            "corridor": ["corridor", "hall", "hallway", "passage"],
            "staircase": ["stair", "dn", "up", "steps"],
            "lobby": ["lobby", "foyer", "entrance"],
            "nurse_station": ["nurse", "nursing"],
            "restroom": ["men", "women", "toilet", "restroom", "bath", "wc", "lavatory"],
            "waiting_area": ["waiting", "wait"],
            "store": ["store", "storage"],
            "reception": ["reception", "front desk"],
            "ward": ["ward"],
            "ot": ["o.t", "operation", "surgery", "surgical"],
            "lab": ["lab", "x-ray", "x ray", "darkroom", "imaging"],
            "office": ["office", "doctor room"],
            "lift": ["lift", "elevator"],
        }

        for room_type, keywords in type_keywords.items():
            for kw in keywords:
                if kw in label_lower:
                    return room_type

        return "room"


# ---------------------------------------------------------------
#  Room -> Node Converter
# ---------------------------------------------------------------

def rooms_to_graph_nodes(rooms: list[Room], grid_snap: int = 0) -> list[dict]:
    """
    Convert rooms to navigation graph nodes.
    Each room = 1 node at its center, with full bbox metadata.

    Args:
        rooms: List of Room objects
        grid_snap: If > 0, snap center coordinates to this grid size
    """
    nodes = []
    for room in rooms:
        cx = room.center_x
        cy = room.center_y

        if grid_snap > 0:
            cx = round(cx / grid_snap) * grid_snap
            cy = round(cy / grid_snap) * grid_snap

        nodes.append({
            "id": room.id,
            "label": room.label,
            "type": room.room_type,
            "x": int(cx),
            "y": int(cy),
            "bbox": {
                "x_min": int(room.bbox.x_min),
                "y_min": int(room.bbox.y_min),
                "x_max": int(room.bbox.x_max),
                "y_max": int(room.bbox.y_max),
            },
            "width": int(room.width),
            "height": int(room.height),
        })

    return nodes


# ---------------------------------------------------------------
#  Main Pipeline
# ---------------------------------------------------------------

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "tmp", "svg_debug")


def run_svg_pipeline(svg_path: str, grid_snap: int = 50) -> dict:
    """
    Full SVG extraction pipeline:
      1. Parse SVG -> get shapes + texts
      2. Match labels to shapes -> rooms
      3. Convert to navigation nodes
    """
    svg_path = os.path.abspath(svg_path)
    print(f"\n{'='*70}")
    print(f"  SVG GRAPH EXTRACTOR -- Pipeline")
    print(f"  File: {svg_path}")
    print(f"{'='*70}\n")

    parser = SVGFloorPlanParser(svg_path)

    # Step 1: Extract shapes and text
    print("\n--- Step 1: Extract SVG elements ---")
    shapes = parser.extract_all_shapes()
    texts = parser.extract_texts()
    lines = parser.extract_lines()

    print(f"\n  Summary:")
    print(f"    Shapes: {len(shapes)}")
    print(f"    Texts:  {len(texts)}")
    print(f"    Lines:  {len(lines)}")

    # Step 2: Match labels to shapes
    print("\n--- Step 2: Match labels to shapes ---")
    rooms = parser.match_labels_to_shapes(shapes, texts)

    print(f"\n  Matched {len(rooms)} rooms:")
    for r in rooms:
        print(f"    [{r.room_type:15s}] {r.label:25s} "
              f"bbox=({int(r.bbox.x_min)},{int(r.bbox.y_min)})-"
              f"({int(r.bbox.x_max)},{int(r.bbox.y_max)}) "
              f"size={int(r.width)}x{int(r.height)}")

    # Step 3: Convert to nodes
    print(f"\n--- Step 3: Convert to nodes (grid_snap={grid_snap}) ---")
    nodes = rooms_to_graph_nodes(rooms, grid_snap)

    for n in nodes:
        print(f"    [{n['type']:15s}] {n['label']:25s} center=({n['x']},{n['y']})")

    # Save output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    basename = Path(svg_path).stem
    json_path = os.path.join(OUTPUT_DIR, f"{basename}_rooms.json")

    output = {
        "svg_path": svg_path,
        "svg_width": parser.svg_width,
        "svg_height": parser.svg_height,
        "rooms": [asdict(r) for r in rooms],
        "nodes": nodes,
        "stats": {
            "total_shapes": len(shapes),
            "total_texts": len(texts),
            "total_lines": len(lines),
            "matched_rooms": len(rooms),
        }
    }

    with open(json_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved: {json_path}")

    print(f"\n{'='*70}")
    print(f"  Done! {len(rooms)} rooms extracted with EXACT coordinates.")
    print(f"{'='*70}\n")

    return output


# ---------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m backend.services.svg_graph_extractor <path/to/floor.svg> [grid_snap]")
        print("\nNo SVG provided. Creating a sample SVG for testing...\n")

        # Create a sample SVG that mimics the hospital floor plan
        sample_dir = os.path.join(os.path.dirname(__file__), "..", "tmp", "svg_debug")
        os.makedirs(sample_dir, exist_ok=True)
        sample_svg = os.path.join(sample_dir, "sample_floor.svg")

        svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="963" viewBox="0 0 1400 963">
  <!-- Rooms as rects with fill colors -->
  <rect x="30" y="120" width="180" height="150" fill="#CCE5FF" stroke="black" stroke-width="2" id="men_restroom"/>
  <rect x="250" y="120" width="200" height="150" fill="#CCE5FF" stroke="black" stroke-width="2" id="women_restroom"/>
  <rect x="30" y="270" width="450" height="30" fill="#FFFFCC" stroke="black" stroke-width="1" id="corridor"/>
  <rect x="200" y="300" width="150" height="100" fill="#E8F5E9" stroke="black" stroke-width="2" id="sterilizer"/>
  <rect x="200" y="400" width="100" height="60" fill="#E8F5E9" stroke="black" stroke-width="2" id="scrub"/>
  <rect x="50" y="370" width="150" height="100" fill="#E8F5E9" stroke="black" stroke-width="2" id="delivery_rm"/>
  <rect x="350" y="320" width="200" height="130" fill="#FFF3E0" stroke="black" stroke-width="2" id="prenatal"/>
  <rect x="580" y="170" width="80" height="100" fill="#F3E5F5" stroke="black" stroke-width="2" id="staircase_dn"/>
  <rect x="580" y="270" width="120" height="60" fill="#FCE4EC" stroke="black" stroke-width="2" id="lobby"/>
  <rect x="770" y="230" width="200" height="120" fill="#E8F5E9" stroke="black" stroke-width="2" id="nurses_room"/>
  <rect x="620" y="370" width="160" height="100" fill="#FFEBEE" stroke="black" stroke-width="2" id="nurses_station_c"/>
  <rect x="1050" y="320" width="200" height="100" fill="#FFEBEE" stroke="black" stroke-width="2" id="nurses_station_r"/>
  <rect x="300" y="470" width="120" height="100" fill="#E8F5E9" stroke="black" stroke-width="2" id="aseptic"/>
  <rect x="420" y="470" width="150" height="80" fill="#FFFFCC" stroke="black" stroke-width="1" id="clean_corridor"/>
  <rect x="280" y="490" width="100" height="80" fill="#FFEBEE" stroke="black" stroke-width="2" id="nurses_station_l"/>
  <rect x="100" y="570" width="120" height="50" fill="#E8F5E9" stroke="black" stroke-width="2" id="store"/>
  <rect x="100" y="620" width="200" height="100" fill="#E8F5E9" stroke="black" stroke-width="2" id="recovery_rm"/>
  <rect x="380" y="570" width="180" height="80" fill="#E8F5E9" stroke="black" stroke-width="2" id="paediatrics"/>
  <rect x="580" y="580" width="200" height="200" fill="#FFF9C4" stroke="black" stroke-width="2" id="waiting"/>
  <rect x="780" y="350" width="450" height="430" fill="#BBDEFB" stroke="black" stroke-width="2" id="female_ward"/>

  <!-- Room labels as text -->
  <text x="80" y="200" font-size="14" font-family="Arial">MEN</text>
  <text x="310" y="200" font-size="14" font-family="Arial">WOMEN</text>
  <text x="180" y="290" font-size="12" font-family="Arial">CORRIDOR</text>
  <text x="230" y="360" font-size="12" font-family="Arial">STERILIZER</text>
  <text x="220" y="435" font-size="12" font-family="Arial">SCRUB</text>
  <text x="80" y="425" font-size="12" font-family="Arial">DELIVERY RM</text>
  <text x="380" y="400" font-size="12" font-family="Arial">PRE-NATAL / LABOUR RM</text>
  <text x="590" y="220" font-size="12" font-family="Arial">DN</text>
  <text x="600" y="305" font-size="14" font-family="Arial">LOBBY</text>
  <text x="810" y="300" font-size="12" font-family="Arial">NURSES ROOM</text>
  <text x="650" y="430" font-size="12" font-family="Arial">NURSES STATION</text>
  <text x="1080" y="380" font-size="12" font-family="Arial">NURSES STATION</text>
  <text x="320" y="530" font-size="12" font-family="Arial">ASEPTIC</text>
  <text x="440" y="520" font-size="12" font-family="Arial">CLEAN CORRIDOR</text>
  <text x="290" y="540" font-size="10" font-family="Arial">NURSES STATION</text>
  <text x="120" y="600" font-size="12" font-family="Arial">STORE</text>
  <text x="150" y="680" font-size="12" font-family="Arial">RECOVERY RM</text>
  <text x="420" y="620" font-size="12" font-family="Arial">PAEDIATRICS</text>
  <text x="640" y="690" font-size="14" font-family="Arial">WAITING</text>
  <text x="950" y="580" font-size="16" font-family="Arial">FEMALE WARD</text>
</svg>'''

        with open(sample_svg, "w") as f:
            f.write(svg_content)
        print(f"Created sample SVG: {sample_svg}\n")

        run_svg_pipeline(sample_svg)
    else:
        svg_file = sys.argv[1]
        grid = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        run_svg_pipeline(svg_file, grid)
