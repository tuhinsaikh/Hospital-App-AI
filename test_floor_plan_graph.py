"""
Floor Plan -> Graph Data -> Pathfinding -- Standalone Test Script
=============================================================

This script demonstrates the FULL pipeline:
  1. Define structured graph data (nodes + edges) from a floor plan image
  2. Visualize the graph overlaid on the floor plan
  3. Run Dijkstra pathfinding between any two rooms
  4. Draw the shortest path on the image
  5. Validate the graph (check disconnected nodes, out-of-bound coords)

No database needed -- everything runs in memory.

Usage:
    python test_floor_plan_graph.py
"""

import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import math
import heapq
import json
from collections import defaultdict
from pathlib import Path

# ─── Check for optional visualization dependency ────────────────────────────
try:
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[WARNING] matplotlib not installed. Visualization disabled.")
    print("         Install it with: pip install matplotlib")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  STEP 1: Define the Graph Data                                          ║
# ║                                                                          ║
# ║  This is what the VisionService generates from the floor plan image.     ║
# ║  You can also create this JSON manually for 100% accuracy.               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

FLOOR_PLAN_IMAGE = Path(__file__).parent / "backend" / "static" / "maps" / "floor_1_a555eca0.jpg"

# Image dimensions (the actual pixel size of your floor plan image)
IMAGE_WIDTH = 1280
IMAGE_HEIGHT = 870

GRAPH_DATA = {
    "nodes": [
        # ── Restrooms (top-left area) ──
        {"id": "men_restroom",       "label": "Men",                   "x": 80,   "y": 180, "type": "restroom", "door": {"x": 165, "y": 270}},
        {"id": "women_restroom",     "label": "Women",                 "x": 300,  "y": 180, "type": "restroom", "door": {"x": 300, "y": 270}},

        # ── Corridor & Junctions (the walkable paths) ──
        {"id": "corridor_top",       "label": "Corridor",              "x": 300,  "y": 270, "type": "corridor"},
        {"id": "junction_center",    "label": "",                      "x": 530,  "y": 270, "type": "junction"},
        {"id": "junction_south",     "label": "",                      "x": 530,  "y": 430, "type": "junction"},
        {"id": "junction_bottom",    "label": "",                      "x": 530,  "y": 640, "type": "junction"},

        # ── Left wing (delivery, sterilizer, etc.) ──
        {"id": "sterilizer",         "label": "Sterilizer",            "x": 250,  "y": 360, "type": "room", "door": {"x": 300, "y": 360}},
        {"id": "delivery_rm",        "label": "Delivery RM",           "x": 80,   "y": 430, "type": "room", "door": {"x": 165, "y": 430}},
        {"id": "scrub",              "label": "Scrub",                 "x": 250,  "y": 430, "type": "room", "door": {"x": 300, "y": 430}},
        {"id": "prenatal_labour_rm", "label": "Pre-Natal / Labour RM", "x": 400,  "y": 400, "type": "room", "door": {"x": 440, "y": 430}},

        # ── Central area ──
        {"id": "lobby",              "label": "Lobby",                 "x": 630,  "y": 270, "type": "room", "door": {"x": 580, "y": 270}},
        {"id": "staircase_dn",       "label": "DN (Stairs Down)",      "x": 580,  "y": 150, "type": "staircase"},
        {"id": "staircase_up",       "label": "UP (Stairs Up)",        "x": 530,  "y": 210, "type": "staircase"},
        {"id": "nurses_station_1",   "label": "Nurses' Station (Central)", "x": 630, "y": 430, "type": "nurse_station", "door": {"x": 580, "y": 430}},

        # ── Left-lower area ──
        {"id": "aseptic",            "label": "Aseptic",               "x": 320,  "y": 510, "type": "room", "door": {"x": 320, "y": 550}},
        {"id": "nurses_station_left","label": "Nurses' Station (Left)","x": 260,  "y": 530, "type": "nurse_station", "door": {"x": 300, "y": 550}},
        {"id": "clean_corridor",     "label": "Clean Corridor",        "x": 440,  "y": 510, "type": "corridor"},
        {"id": "store",              "label": "Store",                 "x": 120,  "y": 590, "type": "room", "door": {"x": 180, "y": 590}},
        {"id": "recovery_rm",        "label": "Recovery RM",           "x": 160,  "y": 660, "type": "room", "door": {"x": 180, "y": 620}},
        {"id": "paediatrics",        "label": "Paediatrics",           "x": 430,  "y": 610, "type": "room", "door": {"x": 440, "y": 570}},

        # ── Right wing ──
        {"id": "nurses_room",        "label": "Nurses' Room",          "x": 870,  "y": 240, "type": "room", "door": {"x": 780, "y": 270}},
        {"id": "nurses_station_2",   "label": "Nurses' Station (Right)","x": 1050, "y": 370, "type": "nurse_station", "door": {"x": 960, "y": 370}},
        {"id": "female_ward",        "label": "Female Ward",           "x": 950,  "y": 500, "type": "room", "door": {"x": 950, "y": 430}},
        {"id": "waiting",            "label": "Waiting",               "x": 650,  "y": 640, "type": "waiting_area", "door": {"x": 580, "y": 640}},
    ],
    "edges": [
        # ── Top corridor connections ──
        {"from": "men_restroom",       "to": "corridor_top"},
        {"from": "women_restroom",     "to": "corridor_top"},
        {"from": "corridor_top",       "to": "junction_center"},
        {"from": "junction_center",    "to": "lobby"},
        {"from": "junction_center",    "to": "staircase_up"},
        {"from": "staircase_up",       "to": "staircase_dn"},
        {"from": "lobby",             "to": "staircase_dn"},

        # ── Left wing ──
        {"from": "corridor_top",       "to": "sterilizer"},
        {"from": "sterilizer",         "to": "delivery_rm"},
        {"from": "sterilizer",         "to": "scrub"},
        {"from": "scrub",              "to": "prenatal_labour_rm"},
        {"from": "prenatal_labour_rm", "to": "clean_corridor"},

        # ── Central vertical corridor ──
        {"from": "junction_center",    "to": "junction_south"},
        {"from": "junction_south",     "to": "nurses_station_1"},
        {"from": "junction_south",     "to": "junction_bottom"},

        # ── Lower-left connections ──
        {"from": "scrub",              "to": "aseptic"},
        {"from": "aseptic",            "to": "nurses_station_left"},
        {"from": "aseptic",            "to": "clean_corridor"},
        {"from": "clean_corridor",     "to": "paediatrics"},
        {"from": "nurses_station_left","to": "store"},
        {"from": "store",              "to": "recovery_rm"},

        # ── Right wing connections ──
        {"from": "lobby",              "to": "nurses_room"},
        {"from": "nurses_room",        "to": "nurses_station_2"},
        {"from": "nurses_station_2",   "to": "female_ward"},
        {"from": "nurses_station_1",   "to": "waiting"},
        {"from": "junction_bottom",    "to": "waiting"},
        {"from": "waiting",            "to": "female_ward"},

        # ── Cross connections ──
        {"from": "nurses_station_1",   "to": "clean_corridor"},
    ]
}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  STEP 2: Graph Validation                                               ║
# ║                                                                          ║
# ║  Check for common problems in the graph data.                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def validate_graph(graph_data: dict, img_width: int, img_height: int) -> dict:
    """
    Validate the graph data and return a report.
    
    Checks:
    1. All nodes have required fields (id, label, x, y)
    2. No duplicate node IDs
    3. All coordinates are within image bounds
    4. All edges reference valid node IDs
    5. No duplicate edges
    6. Graph is fully connected (every node reachable from every other)
    """
    report = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "stats": {}
    }

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    
    # --- Check 1: Required fields ---
    for i, node in enumerate(nodes):
        for field in ("id", "label", "x", "y"):
            if field not in node:
                report["errors"].append(f"Node {i} missing required field '{field}': {node}")
                report["valid"] = False

    # --- Check 2: Duplicate IDs ---
    node_ids = [n["id"] for n in nodes if "id" in n]
    seen = set()
    for nid in node_ids:
        if nid in seen:
            report["errors"].append(f"Duplicate node ID: '{nid}'")
            report["valid"] = False
        seen.add(nid)
    
    # --- Check 3: Coordinate bounds ---
    for node in nodes:
        x, y = node.get("x", 0), node.get("y", 0)
        if x < 0 or x > img_width or y < 0 or y > img_height:
            report["warnings"].append(
                f"Node '{node['id']}' coordinates ({x}, {y}) outside image bounds "
                f"({img_width}x{img_height})"
            )
        door = node.get("door")
        if door:
            dx, dy = door.get("x", 0), door.get("y", 0)
            if dx < 0 or dx > img_width or dy < 0 or dy > img_height:
                report["warnings"].append(
                    f"Node '{node['id']}' door coordinates ({dx}, {dy}) outside image bounds "
                    f"({img_width}x{img_height})"
                )
    
    # --- Check 4: Edge references ---
    valid_ids = set(node_ids)
    for edge in edges:
        for key in ("from", "to"):
            if edge.get(key) not in valid_ids:
                report["errors"].append(
                    f"Edge references non-existent node '{edge.get(key)}': {edge}"
                )
                report["valid"] = False
    
    # --- Check 5: Duplicate edges ---
    edge_set = set()
    for edge in edges:
        pair = tuple(sorted([edge.get("from", ""), edge.get("to", "")]))
        if pair in edge_set:
            report["warnings"].append(f"Duplicate edge: {edge}")
        edge_set.add(pair)
    
    # --- Check 6: Connectivity (BFS) ---
    adj = defaultdict(set)
    for edge in edges:
        adj[edge["from"]].add(edge["to"])
        adj[edge["to"]].add(edge["from"])
    
    if valid_ids:
        start = next(iter(valid_ids))
        visited = set()
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            for neighbor in adj[node]:
                if neighbor not in visited:
                    queue.append(neighbor)
        
        disconnected = valid_ids - visited
        if disconnected:
            report["errors"].append(
                f"Disconnected nodes (unreachable): {disconnected}"
            )
            report["valid"] = False
    
    # --- Stats ---
    report["stats"] = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "rooms": len([n for n in nodes if n.get("type") not in ("junction", "corridor")]),
        "junctions": len([n for n in nodes if n.get("type") == "junction"]),
        "corridors": len([n for n in nodes if n.get("type") == "corridor"]),
    }
    
    return report


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  STEP 3: Dijkstra Pathfinding (same logic as NavigationService)          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def find_shortest_path(graph_data: dict, source_id: str, dest_id: str) -> list[dict] | None:
    """
    Dijkstra shortest path. Edge weight = length of the drawable route between node anchors.
    Returns ordered waypoints anchored at doors when present.
    """
    nodes = {n["id"]: n for n in graph_data["nodes"]}
    
    if source_id not in nodes:
        print(f"  [ERROR] Source '{source_id}' not found in graph")
        return None
    if dest_id not in nodes:
        print(f"  [ERROR] Destination '{dest_id}' not found in graph")
        return None

    # Build adjacency list with door-aware route weights
    adj = defaultdict(list)
    for edge in graph_data["edges"]:
        from_id, to_id = edge["from"], edge["to"]
        if from_id in nodes and to_id in nodes:
            dist = route_distance(edge_points(edge, nodes))
            adj[from_id].append((to_id, dist))
            adj[to_id].append((from_id, dist))  # Bidirectional

    # Dijkstra's algorithm
    dist_map = {nid: float("inf") for nid in nodes}
    dist_map[source_id] = 0
    prev = {nid: None for nid in nodes}
    visited = set()
    heap = [(0, source_id)]

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u == dest_id:
            break
        for v, w in adj[u]:
            if v not in visited:
                new_dist = d + w
                if new_dist < dist_map[v]:
                    dist_map[v] = new_dist
                    prev[v] = u
                    heapq.heappush(heap, (new_dist, v))

    # Reconstruct path
    if dist_map[dest_id] == float("inf"):
        print(f"  [ERROR] No path found from '{source_id}' to '{dest_id}'")
        return None

    path_ids = []
    current = dest_id
    while current is not None:
        path_ids.append(current)
        current = prev[current]
    path_ids.reverse()

    route_points = build_route_points(path_ids, nodes, graph_data["edges"])

    # Convert to waypoints. x/y are now the navigation anchor, not always the center.
    waypoints = []
    for nid in path_ids:
        node = nodes[nid]
        anchor = node_anchor(node)
        waypoints.append({
            "id": node["id"],
            "x": anchor["x"],
            "y": anchor["y"],
            "center_x": node["x"],
            "center_y": node["y"],
            "label": node["label"],
            "type": node.get("type", "room"),
            "door": node.get("door"),
        })

    if waypoints:
        waypoints[0]["route_points"] = route_points

    return waypoints


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  STEP 4: Visualization                                                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# Color scheme for different node types
NODE_COLORS = {
    "room":          "#3B82F6",  # Blue
    "corridor":      "#8B5CF6",  # Purple
    "junction":      "#6B7280",  # Gray
    "entrance":      "#10B981",  # Green
    "staircase":     "#F59E0B",  # Amber
    "restroom":      "#06B6D4",  # Cyan
    "nurse_station": "#EF4444",  # Red
    "waiting_area":  "#F97316",  # Orange
}


def node_anchor(node: dict) -> dict:
    """Use a node door when available; otherwise use the node's walkable point."""
    door = node.get("door")
    if isinstance(door, dict) and "x" in door and "y" in door:
        return {"x": door["x"], "y": door["y"]}
    return {"x": node["x"], "y": node["y"]}


def edge_points(edge: dict, nodes: dict, reverse: bool = False) -> list[dict]:
    """
    Return drawable/navigation points for one edge.

    Edges may define explicit corridor geometry:
      {"from": "a", "to": "b", "path": [{"x": 10, "y": 20}, ...]}

    Without explicit geometry, the edge becomes an orthogonal route between
    door/walkable anchors, which looks closer to indoor map routing than a
    center-to-center diagonal.
    """
    from_node = nodes[edge["from"]]
    to_node = nodes[edge["to"]]
    start = node_anchor(from_node)
    end = node_anchor(to_node)
    middle = edge.get("path", [])

    points = [start, *middle, end]
    if reverse:
        points = list(reversed(points))

    if len(points) == 2 and points[0]["x"] != points[1]["x"] and points[0]["y"] != points[1]["y"]:
        start, end = points
        corner = {"x": end["x"], "y": start["y"]}
        points = [start, corner, end]

    return points


def route_distance(points: list[dict]) -> float:
    """Total pixel length of a polyline route."""
    return sum(
        math.hypot(points[i + 1]["x"] - points[i]["x"], points[i + 1]["y"] - points[i]["y"])
        for i in range(len(points) - 1)
    )


def build_edge_lookup(edges: list[dict]) -> dict[tuple[str, str], dict]:
    """Map directed and reverse node pairs to each edge plus its direction."""
    lookup = {}
    for edge in edges:
        lookup[(edge["from"], edge["to"])] = {"edge": edge, "reverse": False}
        lookup[(edge["to"], edge["from"])] = {"edge": edge, "reverse": True}
    return lookup


def build_route_points(path_ids: list[str], nodes: dict, edges: list[dict]) -> list[dict]:
    """Expand a node path into door-to-door/corridor route points."""
    lookup = build_edge_lookup(edges)
    route = []
    for i in range(len(path_ids) - 1):
        edge_info = lookup[(path_ids[i], path_ids[i + 1])]
        points = edge_points(edge_info["edge"], nodes, reverse=edge_info["reverse"])
        if route and points and route[-1] == points[0]:
            route.extend(points[1:])
        else:
            route.extend(points)
    return route


def visualize_graph(graph_data: dict, image_path: str = None, path_waypoints: list = None,
                    title: str = "Floor Plan Navigation Graph"):
    """
    Visualize the navigation graph, optionally overlaid on the floor plan image.
    If path_waypoints is provided, highlight the shortest path.
    """
    if not HAS_MATPLOTLIB:
        print("[SKIP] Visualization skipped (matplotlib not available)")
        return

    fig, ax = plt.subplots(1, 1, figsize=(16, 10))
    
    # Load floor plan image as background
    if image_path and Path(image_path).exists():
        img = mpimg.imread(str(image_path))
        ax.imshow(img, extent=[0, IMAGE_WIDTH, IMAGE_HEIGHT, 0])
        ax.set_xlim(0, IMAGE_WIDTH)
        ax.set_ylim(IMAGE_HEIGHT, 0)  # Flip Y-axis (image coordinates)
    else:
        ax.set_xlim(0, IMAGE_WIDTH)
        ax.set_ylim(IMAGE_HEIGHT, 0)
        ax.set_facecolor("#1a1a2e")
        print(f"[VIZ] Image not found at '{image_path}', drawing on blank canvas")

    nodes = {n["id"]: n for n in graph_data["nodes"]}

    # Draw edges (gray lines)
    for edge in graph_data["edges"]:
        from_node = nodes.get(edge["from"])
        to_node = nodes.get(edge["to"])
        if from_node and to_node:
            points = edge_points(edge, nodes)
            ax.plot(
                [point["x"] for point in points],
                [point["y"] for point in points],
                color="#9CA3AF", linewidth=1.5, alpha=0.6, zorder=1
            )

    # Draw path (if provided) — thick colored line
    if path_waypoints and len(path_waypoints) > 1:
        route_points = path_waypoints[0].get("route_points") or path_waypoints
        path_x = [point["x"] for point in route_points]
        path_y = [point["y"] for point in route_points]
        ax.plot(path_x, path_y, color="#22D3EE", linewidth=4, alpha=0.9,
                zorder=3, label="Shortest Path")
        # Arrow markers along the path
        for i in range(len(route_points) - 1):
            dx = path_x[i+1] - path_x[i]
            dy = path_y[i+1] - path_y[i]
            if dx == 0 and dy == 0:
                continue
            ax.annotate("", xy=(path_x[i+1], path_y[i+1]),
                        xytext=(path_x[i], path_y[i]),
                        arrowprops=dict(arrowstyle="->", color="#22D3EE",
                                       lw=2.5), zorder=4)

    # Draw nodes
    for node in graph_data["nodes"]:
        color = NODE_COLORS.get(node.get("type", "room"), "#3B82F6")
        size = 60 if node.get("type") == "junction" else 100
        
        ax.scatter(node["x"], node["y"], c=color, s=size, zorder=5,
                   edgecolors="white", linewidths=1.5)

        if node.get("door"):
            ax.scatter(node["door"]["x"], node["door"]["y"], c="#FFFFFF", s=45,
                       zorder=6, edgecolors=color, linewidths=1.5, marker="s")
        
        # Label (skip empty labels for junctions)
        if node["label"]:
            ax.annotate(
                node["label"],
                (node["x"], node["y"]),
                textcoords="offset points",
                xytext=(0, -14),
                ha="center", va="top",
                fontsize=7, fontweight="bold",
                color="white",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=color, alpha=0.85),
                zorder=6
            )

    # Highlight path endpoints
    if path_waypoints:
        start = path_waypoints[0]
        end = path_waypoints[-1]
        ax.scatter(start["x"], start["y"], c="#22C55E", s=200, zorder=7,
                   edgecolors="white", linewidths=2, marker="*", label=f"Start: {start['label']}")
        ax.scatter(end["x"], end["y"], c="#EF4444", s=200, zorder=7,
                   edgecolors="white", linewidths=2, marker="*", label=f"End: {end['label']}")
        ax.legend(loc="upper right", fontsize=9, framealpha=0.9)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    ax.set_xlabel("X (pixels from left)", fontsize=10)
    ax.set_ylabel("Y (pixels from top)", fontsize=10)
    ax.grid(True, alpha=0.15)
    
    plt.tight_layout()
    
    # Save and show
    output_dir = Path(__file__).parent
    output_path = output_dir / "graph_visualization.png"
    plt.savefig(str(output_path), dpi=150, bbox_inches="tight")
    print(f"\n  [SAVED] Visualization saved to: {output_path}")
    plt.show()


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  STEP 5: Run Everything                                                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def main():
    print("=" * 70)
    print("  FLOOR PLAN -> GRAPH DATA -> PATHFINDING  --  Test Script")
    print("=" * 70)

    # ── A) Show the graph data structure ────────────────────────────
    print(f"\n[DATA] GRAPH DATA SUMMARY")
    print(f"   Image: {FLOOR_PLAN_IMAGE}")
    print(f"   Image size: {IMAGE_WIDTH} x {IMAGE_HEIGHT} px")
    print(f"   Nodes: {len(GRAPH_DATA['nodes'])}")
    print(f"   Edges: {len(GRAPH_DATA['edges'])}")
    print()

    print("   NODES:")
    print(f"   {'ID':<25} {'Label':<30} {'X':>5} {'Y':>5}  {'Type':<15}")
    print(f"   {'-'*25} {'-'*30} {'-'*5} {'-'*5}  {'-'*15}")
    for node in GRAPH_DATA["nodes"]:
        print(f"   {node['id']:<25} {node['label']:<30} {node['x']:>5} {node['y']:>5}  {node.get('type', 'room'):<15}")

    print(f"\n   EDGES:")
    for edge in GRAPH_DATA["edges"]:
        nodes_map = {n["id"]: n["label"] or n["id"] for n in GRAPH_DATA["nodes"]}
        from_label = nodes_map.get(edge["from"], edge["from"])
        to_label = nodes_map.get(edge["to"], edge["to"])
        print(f"   {from_label:<30} <-> {to_label}")

    # ── B) Validate the graph ──────────────────────────────────────
    print(f"\n{'-' * 70}")
    print("[VALIDATE] VALIDATING GRAPH...")
    report = validate_graph(GRAPH_DATA, IMAGE_WIDTH, IMAGE_HEIGHT)
    
    if report["valid"]:
        print("   [OK] Graph is VALID!")
    else:
        print("   [FAIL] Graph has ERRORS:")
    
    for error in report["errors"]:
        print(f"   [ERROR] {error}")
    for warning in report["warnings"]:
        print(f"   [WARN] {warning}")
    
    stats = report["stats"]
    print(f"\n   Stats: {stats['total_nodes']} nodes ({stats['rooms']} rooms, "
          f"{stats['junctions']} junctions, {stats['corridors']} corridors), "
          f"{stats['total_edges']} edges")

    # ── C) Test pathfinding ────────────────────────────────────────
    print(f"\n{'-' * 70}")
    print("[PATH] PATHFINDING TESTS\n")
    
    test_cases = [
        ("lobby", "delivery_rm", "Lobby -> Delivery RM"),
        ("men_restroom", "female_ward", "Men's Restroom -> Female Ward"),
        ("waiting", "sterilizer", "Waiting -> Sterilizer"),
        ("recovery_rm", "nurses_room", "Recovery RM -> Nurses' Room"),
        ("staircase_dn", "paediatrics", "Stairs Down -> Paediatrics"),
    ]
    
    all_paths = []
    for source, dest, description in test_cases:
        print(f"  [TEST] {description}")
        waypoints = find_shortest_path(GRAPH_DATA, source, dest)
        if waypoints:
            path_str = " -> ".join(
                wp["label"] if wp["label"] else f"[{wp['id']}]"
                for wp in waypoints
            )
            total_dist = route_distance(waypoints[0].get("route_points", waypoints))
            print(f"     [OK] Path: {path_str}")
            print(f"     [INFO] Distance: {total_dist:.0f} px  |  Nodes: {len(waypoints)}  |  Route points: {len(waypoints[0].get('route_points', waypoints))}")
            all_paths.append(waypoints)
        else:
            print(f"     [FAIL] No path found!")
        print()

    # ── D) Save graph data as JSON (for later use) ─────────────────
    output_json = Path(__file__).parent / "graph_data_floor1.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({
            "floor_number": 1,
            "floor_name": "Second Floor Plan",
            "image_width": IMAGE_WIDTH,
            "image_height": IMAGE_HEIGHT,
            "graph_data": GRAPH_DATA
        }, f, indent=2)
    print(f"{'-' * 70}")
    print(f"[SAVE] Graph data saved to: {output_json}")

    # ── E) Visualize ───────────────────────────────────────────────
    print(f"\n{'-' * 70}")
    print("[VIZ] VISUALIZING GRAPH ON FLOOR PLAN...\n")

    # Visualize full graph (no path highlighted)
    visualize_graph(
        GRAPH_DATA,
        image_path=str(FLOOR_PLAN_IMAGE),
        title="Floor Plan — All Nodes & Edges"
    )

    # Visualize with a specific path
    if all_paths:
        # Use the first test case path for visualization
        visualize_graph(
            GRAPH_DATA,
            image_path=str(FLOOR_PLAN_IMAGE),
            path_waypoints=all_paths[0],
            title=f"Shortest Path: {test_cases[0][2]}"
        )


if __name__ == "__main__":
    main()
