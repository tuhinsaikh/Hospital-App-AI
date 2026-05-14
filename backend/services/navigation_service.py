"""
Navigation Service — Graph storage, in-memory cache, Dijkstra pathfinding, fuzzy matching.

Performance-first design:
- Graph loaded into memory on startup (no DB hit on path requests)
- Dijkstra on ~50-200 nodes completes in < 1ms
- Fuzzy matching uses difflib (stdlib) on small label lists — instant
"""
import os
import math
import heapq
import json
import difflib
import re
from typing import Optional
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor


def node_anchor(node: dict) -> dict:
    """Use a room door as the walkable anchor when present."""
    door = node.get("door")
    if isinstance(door, dict) and "x" in door and "y" in door:
        return {"x": door["x"], "y": door["y"]}
    return {"x": node["x"], "y": node["y"]}


def node_center(node: dict) -> dict:
    return {"x": node["x"], "y": node["y"]}


def same_point(a: dict, b: dict) -> bool:
    return a.get("x") == b.get("x") and a.get("y") == b.get("y")


def edge_route_points(edge: dict, nodes: dict, reverse: bool = False) -> list[dict]:
    """Return the route geometry for an edge, including door anchors and bends."""
    from_node = nodes[edge["from"]]
    to_node = nodes[edge["to"]]
    middle = edge.get("path")
    if middle is None:
        middle = edge.get("waypoints", [])

    points = [node_anchor(from_node), *middle, node_anchor(to_node)]
    if reverse:
        points = list(reversed(points))

    # If no explicit bends exist, prefer an L-shaped indoor route over a diagonal.
    if len(points) == 2 and points[0]["x"] != points[1]["x"] and points[0]["y"] != points[1]["y"]:
        start, end = points
        points = [start, {"x": end["x"], "y": start["y"]}, end]
    return points


def route_waypoint(point: dict, wp_id: str, label: str = "", wp_type: str = "waypoint") -> dict:
    return {
        "id": wp_id,
        "x": point["x"],
        "y": point["y"],
        "label": label,
        "type": wp_type,
    }


def normalize_location_text(value: str) -> str:
    text = (value or "").lower().strip()
    text = text.replace("women's", "women").replace("men's", "men")
    text = re.sub(r"\btoilets?\b|\bbathrooms?\b|\bwashrooms?\b", "restroom", text)
    text = re.sub(r"\bword\b", "ward", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def route_distance(points: list[dict]) -> float:
    return sum(
        math.hypot(points[i + 1]["x"] - points[i]["x"], points[i + 1]["y"] - points[i]["y"])
        for i in range(len(points) - 1)
    )


class NavigationService:
    def __init__(self):
        self.postgres_url = os.getenv(
            "POSTGRES_URL",
            "postgresql://postgres:postgres@localhost:5432/hospital"
        )
        # In-memory cache: floor_number -> {graph_data, image_path, image_width, image_height, floor_name}
        self._graph_cache: dict[int, dict] = {}
        self._load_all_graphs()

    def get_connection(self):
        return psycopg2.connect(
            self.postgres_url, options="-c search_path=hospital,public"
        )

    # ── Cache Management ────────────────────────────────────────────

    def _load_all_graphs(self):
        """Load all floor graphs into memory on startup."""
        print("[NAV_SERVICE] Loading all navigation graphs into memory...")
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT floor_number, floor_name, graph_data,
                               image_path, image_width, image_height
                        FROM navigation_graphs
                        ORDER BY floor_number
                    """)
                    rows = cur.fetchall()
                    for row in rows:
                        floor = row["floor_number"]
                        graph_data = row["graph_data"]
                        # psycopg2 auto-parses JSONB to dict
                        if isinstance(graph_data, str):
                            graph_data = json.loads(graph_data)
                        self._graph_cache[floor] = {
                            "graph_data": graph_data,
                            "image_path": row["image_path"],
                            "image_width": row["image_width"],
                            "image_height": row["image_height"],
                            "floor_name": row["floor_name"],
                        }
                    print(f"[NAV_SERVICE] Loaded {len(self._graph_cache)} floor graph(s) into cache")
        except Exception as e:
            print(f"[NAV_SERVICE] WARNING: Could not load graphs on startup: {e}")

    # ── Save / Load ─────────────────────────────────────────────────

    def save_graph(
        self,
        floor: int,
        graph_data: dict,
        image_path: str,
        image_width: int,
        image_height: int,
        floor_name: str = None,
    ):
        """Save extracted navigation graph to DB AND update in-memory cache."""
        if not floor_name:
            floor_name = f"Floor {floor}"

        print(f"[NAV_SERVICE] Saving graph for floor {floor}: "
              f"{len(graph_data.get('nodes', []))} nodes, "
              f"{len(graph_data.get('edges', []))} edges")

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Upsert: insert or update if floor already exists
                    cur.execute("""
                        INSERT INTO navigation_graphs
                            (floor_number, floor_name, graph_data, image_path, image_width, image_height, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (floor_number)
                        DO UPDATE SET
                            floor_name = EXCLUDED.floor_name,
                            graph_data = EXCLUDED.graph_data,
                            image_path = EXCLUDED.image_path,
                            image_width = EXCLUDED.image_width,
                            image_height = EXCLUDED.image_height,
                            updated_at = NOW()
                    """, (
                        floor,
                        floor_name,
                        json.dumps(graph_data),
                        image_path,
                        image_width,
                        image_height,
                    ))
                conn.commit()
            print(f"[NAV_SERVICE] Graph saved to DB for floor {floor}")
        except Exception as e:
            print(f"[NAV_SERVICE] ERROR saving graph: {e}")
            raise

        # Update in-memory cache immediately
        self._graph_cache[floor] = {
            "graph_data": graph_data,
            "image_path": image_path,
            "image_width": image_width,
            "image_height": image_height,
            "floor_name": floor_name,
        }
        print(f"[NAV_SERVICE] In-memory cache updated for floor {floor}")

    def load_graph(self, floor: int = 1) -> Optional[dict]:
        """Read from memory cache (falls back to DB if cache miss)."""
        if floor in self._graph_cache:
            return self._graph_cache[floor]

        # Cache miss — try DB
        print(f"[NAV_SERVICE] Cache miss for floor {floor}, loading from DB...")
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT floor_number, floor_name, graph_data,
                               image_path, image_width, image_height
                        FROM navigation_graphs
                        WHERE floor_number = %s
                    """, (floor,))
                    row = cur.fetchone()
                    if row:
                        graph_data = row["graph_data"]
                        if isinstance(graph_data, str):
                            graph_data = json.loads(graph_data)
                        entry = {
                            "graph_data": graph_data,
                            "image_path": row["image_path"],
                            "image_width": row["image_width"],
                            "image_height": row["image_height"],
                            "floor_name": row["floor_name"],
                        }
                        self._graph_cache[floor] = entry
                        return entry
        except Exception as e:
            print(f"[NAV_SERVICE] ERROR loading graph from DB: {e}")

        return None

    def get_floor_info(self, floor: int = 1) -> Optional[dict]:
        """Returns image_path, image_width, image_height, floor_name from cache."""
        entry = self.load_graph(floor)
        if entry:
            return {
                "image_path": entry["image_path"],
                "image_width": entry["image_width"],
                "image_height": entry["image_height"],
                "floor_name": entry["floor_name"],
            }
        return None

    def has_graph(self, floor: int = 1) -> bool:
        """Check if a navigation graph exists for the given floor."""
        return self.load_graph(floor) is not None

    # ── Fuzzy Location Matching ─────────────────────────────────────

    def resolve_location(self, name: str, graph_data: dict) -> Optional[str]:
        """
        Fuzzy-match user's text (e.g., 'staircase') to a node ID.
        Matches against both node labels and IDs.
        Returns the best-matching node ID, or None if no match.
        """
        if not name or not graph_data.get("nodes"):
            return None

        name_lower = normalize_location_text(name)
        nodes = graph_data["nodes"]

        # 1. Exact match on ID
        for node in nodes:
            if normalize_location_text(node["id"]) == name_lower:
                return node["id"]

        # 2. Exact match on label
        for node in nodes:
            if normalize_location_text(node["label"]) == name_lower:
                return node["id"]

        # 3. Substring match on label
        for node in nodes:
            label_norm = normalize_location_text(node.get("label", ""))
            if label_norm and (name_lower in label_norm or label_norm in name_lower):
                return node["id"]

        # 4. Substring match on ID
        for node in nodes:
            id_norm = normalize_location_text(node["id"])
            if name_lower in id_norm or id_norm in name_lower:
                return node["id"]

        # 5. Fuzzy match using difflib on labels (ignore empty labels)
        valid_nodes = [n for n in nodes if n["label"].strip()]
        labels = [normalize_location_text(node["label"]) for node in valid_nodes]
        matches = difflib.get_close_matches(name_lower, labels, n=1, cutoff=0.4)
        if matches:
            matched_label = matches[0]
            for node in valid_nodes:
                if normalize_location_text(node["label"]) == matched_label:
                    return node["id"]

        # 6. Fuzzy match on IDs (ignore junctions if possible)
        valid_nodes_ids = [n for n in nodes if n.get("type") != "junction"]
        ids = [normalize_location_text(node["id"]) for node in valid_nodes_ids]
        matches = difflib.get_close_matches(name_lower, ids, n=1, cutoff=0.4)
        if matches:
            matched_id = matches[0]
            for node in valid_nodes_ids:
                if normalize_location_text(node["id"]) == matched_id:
                    return node["id"]

        # 6. Fuzzy match on IDs
        ids = [normalize_location_text(node["id"]) for node in nodes]
        matches = difflib.get_close_matches(name_lower, ids, n=1, cutoff=0.5)
        if matches:
            matched_id = matches[0]
            for node in nodes:
                if normalize_location_text(node["id"]) == matched_id:
                    return node["id"]

        print(f"[NAV_SERVICE] Could not resolve location: '{name}'")
        return None

    # ── Dijkstra Pathfinding ────────────────────────────────────────

    def find_path(
        self, source_id: str, dest_id: str, graph_data: dict
    ) -> Optional[list[dict]]:
        """
        Dijkstra shortest path. Edge weight = Euclidean pixel distance between nodes.
        Returns ordered waypoints: [{"id", "x", "y", "label", "type"}, ...] or None.
        """
        nodes = {n["id"]: n for n in graph_data["nodes"]}
        if source_id not in nodes or dest_id not in nodes:
            print(f"[NAV_SERVICE] Source '{source_id}' or dest '{dest_id}' not in graph")
            return None

        # Build adjacency list using the same route geometry that is drawn.
        adj = defaultdict(list)
        edge_lookup = {}  # (from, to) -> {edge, reverse}
        for edge in graph_data["edges"]:
            from_id, to_id = edge["from"], edge["to"]
            if from_id in nodes and to_id in nodes:
                dist = route_distance(edge_route_points(edge, nodes))
                adj[from_id].append((to_id, dist))
                adj[to_id].append((from_id, dist))  # Bidirectional
                edge_lookup[(from_id, to_id)] = {"edge": edge, "reverse": False}
                edge_lookup[(to_id, from_id)] = {"edge": edge, "reverse": True}

        # Dijkstra
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
            print(f"[NAV_SERVICE] No path found from '{source_id}' to '{dest_id}'")
            return None

        path_ids = []
        current = dest_id
        while current is not None:
            path_ids.append(current)
            current = prev[current]
        path_ids.reverse()

        # Convert to drawable route:
        # node center -> node door -> edge bends -> next door -> next node center.
        waypoints = []
        for i, nid in enumerate(path_ids):
            node = nodes[nid]
            center = node_center(node)
            if not waypoints or not same_point(waypoints[-1], center):
                waypoints.append({
                    "id": node["id"],
                    "x": center["x"],
                    "y": center["y"],
                    "label": node["label"],
                    "type": node.get("type", "room"),
                    "door": node.get("door"),
                })

            if i < len(path_ids) - 1:
                next_id = path_ids[i + 1]
                next_node = nodes[next_id]
                edge_info = edge_lookup.get((nid, next_id))
                if edge_info:
                    anchor = node_anchor(node)
                    if not same_point(center, anchor):
                        waypoints.append(route_waypoint(
                            anchor,
                            f"door_{nid}",
                            f"{node['label']} entry" if node.get("label") else "",
                            "door",
                        ))

                    points = edge_route_points(edge_info["edge"], nodes, reverse=edge_info["reverse"])
                    for wp in points[1:-1]:
                        waypoints.append(route_waypoint(wp, f"wp_{nid}_{next_id}"))

                    next_anchor = node_anchor(next_node)
                    next_center = node_center(next_node)
                    if not same_point(next_anchor, next_center):
                        waypoints.append(route_waypoint(
                            next_anchor,
                            f"door_{next_id}",
                            f"{next_node['label']} entry" if next_node.get("label") else "",
                            "door",
                        ))

        print(f"[NAV_SERVICE] Path found: {' -> '.join(wp['label'] for wp in waypoints if wp['label'])}")
        return waypoints

    # ── High-Level API ──────────────────────────────────────────────

    def get_navigation_path(
        self, source_name: str, dest_name: str, floor: int = 1
    ) -> Optional[dict]:
        """
        Full pipeline: resolve names → find path → return response dict.
        All from in-memory cache — no DB hit.
        """
        entry = self.load_graph(floor)
        if not entry:
            print(f"[NAV_SERVICE] No navigation graph found for floor {floor}")
            return None

        graph_data = entry["graph_data"]

        # Resolve locations
        source_id = self.resolve_location(source_name, graph_data)
        if not source_id:
            print(f"[NAV_SERVICE] Could not resolve source: '{source_name}'")
            return None

        dest_id = self.resolve_location(dest_name, graph_data)
        if not dest_id:
            print(f"[NAV_SERVICE] Could not resolve destination: '{dest_name}'")
            return None

        print(f"[NAV_SERVICE] Resolved: '{source_name}' -> {source_id}, '{dest_name}' -> {dest_id}")

        # Find path
        waypoints = self.find_path(source_id, dest_id, graph_data)
        if not waypoints:
            return None

        # Build response
        nodes_map = {n["id"]: n for n in graph_data["nodes"]}
        return {
            "source": waypoints[0],
            "destination": waypoints[-1],
            "path": waypoints,
            "floor": floor,
            "floor_name": entry["floor_name"],
            "background_image": entry["image_path"],
            "image_width": entry["image_width"],
            "image_height": entry["image_height"],
        }


# Singleton instance — preloads graphs into memory on import
navigation_service = NavigationService()
