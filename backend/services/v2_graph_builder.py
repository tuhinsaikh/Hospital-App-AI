import math
from dataclasses import dataclass
from typing import Iterable, Optional


def _dist(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _polyline_length(points: list[dict]) -> float:
    if len(points) < 2:
        return 0.0
    return sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def _grid_key(x: float, y: float, cell: float) -> tuple[int, int]:
    return (int(math.floor(x / cell)), int(math.floor(y / cell)))


def _clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else 1.0 if t > 1.0 else t


def project_point_to_segment(p: dict, a: dict, b: dict) -> tuple[dict, float]:
    """
    Return (projection_point, t) where t in [0,1] is the param along segment a->b.
    """
    ax, ay = a["x"], a["y"]
    bx, by = b["x"], b["y"]
    px, py = p["x"], p["y"]
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return {"x": ax, "y": ay}, 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / denom
    t = _clamp01(t)
    return {"x": ax + t * dx, "y": ay + t * dy}, t


def _segment_bbox(a: dict, b: dict) -> tuple[float, float, float, float]:
    minx = min(a["x"], b["x"])
    maxx = max(a["x"], b["x"])
    miny = min(a["y"], b["y"])
    maxy = max(a["y"], b["y"])
    return minx, miny, maxx, maxy


def _bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float], pad: float = 0.0) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (ax2 + pad < bx1 or bx2 + pad < ax1 or ay2 + pad < by1 or by2 + pad < ay1)


def _cross(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


def segment_intersection(a: dict, b: dict, c: dict, d: dict) -> Optional[dict]:
    """
    Proper segment intersection (including endpoint touches). Returns intersection point or None.
    """
    r = {"x": b["x"] - a["x"], "y": b["y"] - a["y"]}
    s = {"x": d["x"] - c["x"], "y": d["y"] - c["y"]}
    rxs = _cross(r["x"], r["y"], s["x"], s["y"])
    q_p = {"x": c["x"] - a["x"], "y": c["y"] - a["y"]}
    qpxr = _cross(q_p["x"], q_p["y"], r["x"], r["y"])

    if abs(rxs) < 1e-9:
        # Parallel or collinear: ignore (we rely on snapping for near-duplicates)
        return None

    t = _cross(q_p["x"], q_p["y"], s["x"], s["y"]) / rxs
    u = qpxr / rxs
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return {"x": a["x"] + t * r["x"], "y": a["y"] + t * r["y"]}
    return None


@dataclass(frozen=True)
class _NodeRef:
    node_id: str
    x: float
    y: float


def ensure_dual_store(graph_data: dict) -> dict:
    """
    Normalize incoming graph_data into schema_version=2 dual-store shape.
    Accepts:
      - v1-only: {nodes, edges}
      - dual-store: {schema_version:2, v1:{...}, v2:{...}}
    """
    if not isinstance(graph_data, dict):
        graph_data = {"nodes": [], "edges": []}

    if graph_data.get("schema_version") == 2 and isinstance(graph_data.get("v1"), dict):
        out = graph_data
        out.setdefault("v2", {})
        v2 = out["v2"]
        v2.setdefault("rooms", [])
        v2.setdefault("doors", [])
        v2.setdefault("walkable_paths", [])
        v2.setdefault("junctions", [])
        v2.setdefault("graph", {"nodes": [], "edges": []})
        v2.setdefault("meta", {"tolerances": {}, "sources": {}})
        return out

    # v1-only
    v1 = {"nodes": graph_data.get("nodes", []) or [], "edges": graph_data.get("edges", []) or []}
    return {
        "schema_version": 2,
        "v1": v1,
        "v2": {
            "rooms": [],
            "doors": [],
            "walkable_paths": [],
            "junctions": [],
            "graph": {"nodes": [], "edges": []},
            "meta": {"tolerances": {"snap_eps_px": 12, "min_segment_len_px": 6, "grid_cell_px": 64}, "sources": {}},
        },
    }


def derive_v2_from_v1(v1: dict) -> dict:
    """
    Best-effort conversion to v2 authoring entities from the legacy editor model.
    Rooms come from non-corridor/junction nodes. Doors come from node.door (single) or node.doors (list).
    Walkable paths come from edges where both endpoints are corridor/junction nodes.
    """
    nodes = v1.get("nodes", []) or []
    edges = v1.get("edges", []) or []
    nodes_by_id = {n.get("id"): n for n in nodes if isinstance(n, dict) and n.get("id")}

    rooms = []
    doors = []
    walkable_paths = []

    for n in nodes:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        ntype = (n.get("type") or "room").lower()
        if ntype in ("corridor", "junction"):
            continue
        room_id = n["id"]
        label = n.get("label", room_id)
        rooms.append({
            "id": room_id,
            "label": label,
            "type": n.get("type", "room"),
            "x": int(n.get("x", 0)),
            "y": int(n.get("y", 0)),
            "door_ids": [],
            "meta": {"source": "v1"},
        })

        door_list = []
        if isinstance(n.get("doors"), list):
            door_list = [d for d in n["doors"] if isinstance(d, dict)]
        elif isinstance(n.get("door"), dict):
            door_list = [n["door"]]

        for idx, d in enumerate(door_list, 1):
            if "x" not in d or "y" not in d:
                continue
            door_id = f"door_{room_id}_{idx}"
            doors.append({
                "id": door_id,
                "room_id": room_id,
                "x": int(d["x"]),
                "y": int(d["y"]),
                "connected_to": None,
                "meta": {"source": "v1"},
            })
            rooms[-1]["door_ids"].append(door_id)

    for e in edges:
        if not isinstance(e, dict):
            continue
        a = nodes_by_id.get(e.get("from"))
        b = nodes_by_id.get(e.get("to"))
        if not a or not b:
            continue
        ta = (a.get("type") or "").lower()
        tb = (b.get("type") or "").lower()
        # Prefer corridor/junction-to-corridor/junction as canonical walkable paths,
        # but also accept corridor/junction <-> room edges for backwards compatibility.
        if not ((ta in ("corridor", "junction") and tb in ("corridor", "junction")) or (ta in ("corridor", "junction") or tb in ("corridor", "junction"))):
            continue
        pts = e.get("path") or e.get("waypoints") or []
        if not isinstance(pts, list):
            pts = []
        def anchor(n: dict) -> dict:
            door = n.get("door")
            if isinstance(door, dict) and "x" in door and "y" in door:
                return {"x": int(door["x"]), "y": int(door["y"])}
            return {"x": int(n.get("x", 0)), "y": int(n.get("y", 0))}

        # Build a full polyline including endpoints (prefer room door anchors when present)
        poly = [anchor(a), *[{"x": int(p["x"]), "y": int(p["y"])} for p in pts if isinstance(p, dict) and "x" in p and "y" in p], anchor(b)]
        if len(poly) >= 2 and _polyline_length(poly) > 0:
            walkable_paths.append({
                "id": f"path_{len(walkable_paths) + 1}",
                "points": poly,
                "meta": {"source": "v1_edge"},
            })

    return {
        "rooms": rooms,
        "doors": doors,
        "walkable_paths": walkable_paths,
        "junctions": [],
        "graph": {"nodes": [], "edges": []},
        "meta": {"tolerances": {"snap_eps_px": 12, "min_segment_len_px": 6, "grid_cell_px": 64}, "sources": {"derived_from": "v1"}},
    }


def derive_v1_from_v2(v2: dict) -> dict:
    """
    Best-effort conversion from v2 authoring entities to a minimal v1 view.
    This is used for backward compatibility (logs/embeddings/UI that still expects nodes/edges).

    Design choice: only rooms become v1 nodes; edges are omitted.
    Doors are represented as node.door (first) and node.doors (all).
    """
    rooms = v2.get("rooms") or []
    doors = v2.get("doors") or []
    doors_by_room: dict[str, list[dict]] = {}
    for d in doors:
        if not isinstance(d, dict) or not d.get("room_id"):
            continue
        doors_by_room.setdefault(d["room_id"], []).append(d)

    nodes = []
    for r in rooms:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        rid = r["id"]
        rdoors = doors_by_room.get(rid, [])
        node = {
            "id": rid,
            "label": r.get("label") or rid,
            "type": r.get("type") or "room",
            "x": int(r.get("x", 0) or 0),
            "y": int(r.get("y", 0) or 0),
        }
        if rdoors:
            node["doors"] = [{"x": int(d.get("x", 0) or 0), "y": int(d.get("y", 0) or 0)} for d in rdoors]
            node["door"] = node["doors"][0]
        nodes.append(node)

    return {"nodes": nodes, "edges": []}


def build_topology(v2: dict) -> dict:
    """
    Build v2.graph from v2.walkable_paths (polylines). Automatically creates intersection nodes and splits segments.
    Also attaches doors to nearest segment/node.
    """
    tol = (v2.get("meta") or {}).get("tolerances") or {}
    snap_eps = float(tol.get("snap_eps_px", 12))
    min_seg_len = float(tol.get("min_segment_len_px", 6))
    cell = float(tol.get("grid_cell_px", max(32.0, snap_eps * 4)))

    walkable_paths = v2.get("walkable_paths") or []
    doors = v2.get("doors") or []

    # 1) Collect raw segments from polylines
    segments = []  # each: {path_id, i, a, b}
    for wp in walkable_paths:
        pts = wp.get("points") or []
        if not isinstance(pts, list) or len(pts) < 2:
            continue
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            if not (isinstance(a, dict) and isinstance(b, dict) and "x" in a and "y" in a and "x" in b and "y" in b):
                continue
            if _dist(a, b) < min_seg_len:
                continue
            segments.append({
                "path_id": wp.get("id") or "path",
                "a": {"x": float(a["x"]), "y": float(a["y"])},
                "b": {"x": float(b["x"]), "y": float(b["y"])},
            })

    # Early exit
    if not segments:
        v2["graph"] = {"nodes": [], "edges": []}
        return v2

    # 2) Spatial index segments by bbox grid cell
    seg_cells: dict[tuple[int, int], list[int]] = {}
    seg_bboxes = []
    for idx, s in enumerate(segments):
        bb = _segment_bbox(s["a"], s["b"])
        seg_bboxes.append(bb)
        x1, y1, x2, y2 = bb
        gx1, gy1 = _grid_key(x1 - snap_eps, y1 - snap_eps, cell)
        gx2, gy2 = _grid_key(x2 + snap_eps, y2 + snap_eps, cell)
        for gx in range(gx1, gx2 + 1):
            for gy in range(gy1, gy2 + 1):
                seg_cells.setdefault((gx, gy), []).append(idx)

    # 3) Find intersection points per segment
    splits: list[list[dict]] = [[] for _ in segments]  # points to split at (including endpoints later)
    for cell_key, idxs in seg_cells.items():
        if len(idxs) < 2:
            continue
        for i in range(len(idxs)):
            si = idxs[i]
            for j in range(i + 1, len(idxs)):
                sj = idxs[j]
                if si == sj:
                    continue
                if not _bbox_intersects(seg_bboxes[si], seg_bboxes[sj], pad=snap_eps):
                    continue
                a, b = segments[si]["a"], segments[si]["b"]
                c, d = segments[sj]["a"], segments[sj]["b"]
                ip = segment_intersection(a, b, c, d)
                if ip is None:
                    continue
                splits[si].append(ip)
                splits[sj].append(ip)

    # 4) Build snapped unique points registry for nodes
    point_grid: dict[tuple[int, int], list[_NodeRef]] = {}
    nodes: list[dict] = []
    nodes_by_id: dict[str, dict] = {}

    def get_or_create_node(pt: dict, kind: str) -> str:
        key = _grid_key(pt["x"], pt["y"], snap_eps)
        for gx in (key[0] - 1, key[0], key[0] + 1):
            for gy in (key[1] - 1, key[1], key[1] + 1):
                for ref in point_grid.get((gx, gy), []):
                    if math.hypot(ref.x - pt["x"], ref.y - pt["y"]) <= snap_eps:
                        return ref.node_id
        node_id = f"n{len(nodes) + 1}"
        node = {"id": node_id, "x": int(round(pt["x"])), "y": int(round(pt["y"])), "kind": kind}
        nodes.append(node)
        nodes_by_id[node_id] = node
        point_grid.setdefault(key, []).append(_NodeRef(node_id=node_id, x=pt["x"], y=pt["y"]))
        return node_id

    # 5) Split each original segment at intersections (plus endpoints), produce edges
    edges: list[dict] = []

    for idx, s in enumerate(segments):
        a = s["a"]
        b = s["b"]
        pts = [a, b, *splits[idx]]

        # De-dup close points on this segment
        uniq = []
        for p in pts:
            if not uniq:
                uniq.append(p)
                continue
            if all(math.hypot(p["x"] - q["x"], p["y"] - q["y"]) > snap_eps for q in uniq):
                uniq.append(p)

        # Sort points along segment by projection t
        ax, ay = a["x"], a["y"]
        bx, by = b["x"], b["y"]
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy or 1.0
        uniq.sort(key=lambda p: ((p["x"] - ax) * dx + (p["y"] - ay) * dy) / denom)

        for i in range(len(uniq) - 1):
            p1 = uniq[i]
            p2 = uniq[i + 1]
            if _dist(p1, p2) < min_seg_len:
                continue
            n1 = get_or_create_node(p1, kind="path_vertex")
            n2 = get_or_create_node(p2, kind="path_vertex")
            # Always use canonical node coordinates for polyline endpoints (important for stitching).
            np1 = nodes_by_id[n1]
            np2 = nodes_by_id[n2]
            edge_poly = [{"x": int(np1["x"]), "y": int(np1["y"])}, {"x": int(np2["x"]), "y": int(np2["y"])}]
            edges.append({
                "id": f"e{len(edges) + 1}",
                "from": n1,
                "to": n2,
                "weight": float(_polyline_length(edge_poly)),
                "polyline": edge_poly,
                "meta": {"path_id": s["path_id"]},
            })

    # 6) Attach doors to nearest segment/node
    # Build spatial index for edges by bbox grid
    edge_cells: dict[tuple[int, int], list[int]] = {}
    edge_bboxes = []
    for ei, e in enumerate(edges):
        p1, p2 = e["polyline"][0], e["polyline"][1]
        bb = _segment_bbox(p1, p2)
        edge_bboxes.append(bb)
        x1, y1, x2, y2 = bb
        gx1, gy1 = _grid_key(x1 - snap_eps, y1 - snap_eps, cell)
        gx2, gy2 = _grid_key(x2 + snap_eps, y2 + snap_eps, cell)
        for gx in range(gx1, gx2 + 1):
            for gy in range(gy1, gy2 + 1):
                edge_cells.setdefault((gx, gy), []).append(ei)

    # nodes_by_id already filled during node creation; add any later-added nodes below.

    def insert_node_and_split_edge(edge_idx: int, pt: dict) -> str:
        edge = edges[edge_idx]
        from_id = edge["from"]
        to_id = edge["to"]
        new_node_id = get_or_create_node({"x": float(pt["x"]), "y": float(pt["y"])}, kind="door_attach")
        if new_node_id not in nodes_by_id:
            nodes_by_id[new_node_id] = next(n for n in nodes if n["id"] == new_node_id)
        # Replace edge with two edges (keep IDs stable-ish by appending)
        p_from = {"x": nodes_by_id[from_id]["x"], "y": nodes_by_id[from_id]["y"]}
        p_mid = {"x": nodes_by_id[new_node_id]["x"], "y": nodes_by_id[new_node_id]["y"]}
        p_to = {"x": nodes_by_id[to_id]["x"], "y": nodes_by_id[to_id]["y"]}
        # Mark original edge inactive by zeroing weight; keep for debug but not used
        edge["weight"] = 0.0
        edge["meta"]["inactive"] = True
        edges.append({
            "id": f"e{len(edges) + 1}",
            "from": from_id,
            "to": new_node_id,
            "weight": float(_polyline_length([p_from, p_mid])),
            "polyline": [p_from, p_mid],
            "meta": {"split_from": edge["id"]},
        })
        edges.append({
            "id": f"e{len(edges) + 1}",
            "from": new_node_id,
            "to": to_id,
            "weight": float(_polyline_length([p_mid, p_to])),
            "polyline": [p_mid, p_to],
            "meta": {"split_from": edge["id"]},
        })
        return new_node_id

    for d in doors:
        if not isinstance(d, dict) or "x" not in d or "y" not in d or not d.get("id"):
            continue
        door_pt = {"x": float(d["x"]), "y": float(d["y"])}
        key = _grid_key(door_pt["x"], door_pt["y"], cell)
        cand = set()
        for gx in (key[0] - 1, key[0], key[0] + 1):
            for gy in (key[1] - 1, key[1], key[1] + 1):
                cand.update(edge_cells.get((gx, gy), []))
        best = None
        best_proj = None
        best_dist = float("inf")
        best_t = 0.0
        for ei in cand:
            e = edges[ei]
            if e.get("meta", {}).get("inactive"):
                continue
            p1, p2 = e["polyline"][0], e["polyline"][1]
            proj, t = project_point_to_segment(door_pt, p1, p2)
            dist = _dist(door_pt, proj)
            if dist < best_dist:
                best_dist = dist
                best = ei
                best_proj = proj
                best_t = t
        if best is None or best_proj is None:
            continue

        # Decide attach to nearest endpoint node if close enough
        edge = edges[best]
        from_node = nodes_by_id[edge["from"]]
        to_node = nodes_by_id[edge["to"]]
        attach_id = None
        if math.hypot(from_node["x"] - best_proj["x"], from_node["y"] - best_proj["y"]) <= snap_eps:
            attach_id = edge["from"]
        elif math.hypot(to_node["x"] - best_proj["x"], to_node["y"] - best_proj["y"]) <= snap_eps:
            attach_id = edge["to"]
        else:
            attach_id = insert_node_and_split_edge(best, best_proj)

        door_node_id = f"door:{d['id']}"
        # Create door node itself
        if door_node_id not in nodes_by_id:
            nodes.append({"id": door_node_id, "x": int(round(door_pt["x"])), "y": int(round(door_pt["y"])), "kind": "door"})
            nodes_by_id[door_node_id] = nodes[-1]

        # Edge from door to attach point
        attach_node = nodes_by_id[attach_id]
        door_edge_poly = [{"x": nodes_by_id[door_node_id]["x"], "y": nodes_by_id[door_node_id]["y"]}, {"x": attach_node["x"], "y": attach_node["y"]}]
        edges.append({
            "id": f"e{len(edges) + 1}",
            "from": door_node_id,
            "to": attach_id,
            "weight": float(_polyline_length(door_edge_poly)),
            "polyline": door_edge_poly,
            "meta": {"kind": "door_attach", "door_id": d["id"]},
        })
        d["connected_to"] = {"kind": "graph_node", "id": attach_id, "distance": float(best_dist), "t": float(best_t)}

    # Filter out inactive edges for runtime graph
    runtime_edges = [e for e in edges if not e.get("meta", {}).get("inactive")]
    v2["graph"] = {"nodes": nodes, "edges": runtime_edges}
    return v2
