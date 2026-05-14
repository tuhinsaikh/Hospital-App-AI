/**
 * Admin Floor Plan Editor — Core Logic
 * Upload, process, render, edit, and save navigation graphs.
 */

// ── State ──────────────────────────────────────────
let graphData = { nodes: [], edges: [] };
let originalGraphData = null;
let floorPlanImage = null;
let floorImageUrl = '';
let currentFloor = 1;
let imgWidth = 0, imgHeight = 0;
let currentDraftId = null;
let draftSaveTimer = null;

// Canvas state
let canvas, ctx;
let scale = 1, offsetX = 0, offsetY = 0;
let mode = 'select'; // select, add-node, add-door, add-edge, delete
let selectedNodeId = null;
let selectedEdgeIdx = -1; // index into graphData.edges
let edgeStartNodeId = null;
let edgeWaypoints = []; // bend points being drawn for current edge
let doorTargetNodeId = null;
let draggingNode = null;
let draggingDoor = null;
let draggingWaypoint = null; // { edgeIdx, wpIdx }
let isPanning = false;
let panStart = { x: 0, y: 0 };
let lastMouse = { x: 0, y: 0 };

const NODE_RADIUS = 8;
const HIT_RADIUS = 14;
const EDGE_HIT_DIST = 10;
const WP_RADIUS = 5;
const WP_HIT_RADIUS = 10;
const DOOR_SIZE = 8;
const DOOR_HIT_RADIUS = 12;
const DRAFT_SAVE_DELAY = 700;

// Pending add-node click coords
let pendingNodeX = 0, pendingNodeY = 0;

// ── Init ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  canvas = document.getElementById('graphCanvas');
  ctx = canvas.getContext('2d');
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  setupDropZone();
  setupCanvasEvents();
  setupPropertyListeners();

  // Load existing graph if available
  loadExistingFloor();
});

function resizeCanvas() {
  const container = document.getElementById('canvasContainer');
  canvas.width = container.clientWidth;
  canvas.height = container.clientHeight;
  render();
}

// ── Drop Zone & File Handling ──────────────────────
function setupDropZone() {
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const uploadBtn = document.getElementById('uploadBtn');
  const filePreview = document.getElementById('filePreview');
  const fileName = document.getElementById('fileName');
  const fileRemove = document.getElementById('fileRemove');

  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) handleFile(fileInput.files[0]);
  });

  fileRemove.addEventListener('click', () => {
    fileInput.value = '';
    filePreview.classList.remove('visible');
    uploadBtn.disabled = true;
  });

  uploadBtn.addEventListener('click', uploadAndProcess);

  document.getElementById('floorSelect').addEventListener('change', e => {
    currentFloor = parseInt(e.target.value);
    currentDraftId = null;
    graphData = { nodes: [], edges: [] };
    originalGraphData = null;
    floorPlanImage = null;
    floorImageUrl = '';
    document.getElementById('emptyState').classList.remove('hidden');
    document.getElementById('graphInfo').classList.remove('visible');
    selectNode(null);
    loadExistingFloor();
    render();
  });
}

function handleFile(file) {
  if (!file.type.startsWith('image/')) { showToast('Please select an image file', 'error'); return; }
  document.getElementById('fileName').textContent = file.name;
  document.getElementById('filePreview').classList.add('visible');
  document.getElementById('uploadBtn').disabled = false;
}

// ── Upload & Streaming Processing ──────────────────
async function uploadAndProcess() {
  const fileInput = document.getElementById('fileInput');
  const file = fileInput.files[0];
  if (!file) return;

  const floor = document.getElementById('floorSelect').value;
  const btn = document.getElementById('uploadBtn');
  btn.disabled = true;

  // Show processing overlay
  const overlay = document.getElementById('processingOverlay');
  overlay.classList.add('visible');
  resetProcessingUI();

  const formData = new FormData();
  formData.append('file', file);
  formData.append('floor_number', floor);

  try {
    const response = await fetch('/update_floor_plan', { method: 'POST', body: formData });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line);
          handleProcessingStep(data);
        } catch (e) { /* skip malformed */ }
      }
    }
  } catch (err) {
    showToast('Upload failed: ' + err.message, 'error');
  }

  setTimeout(() => {
    overlay.classList.remove('visible');
    btn.disabled = false;
  }, 1200);
}

function resetProcessingUI() {
  document.querySelectorAll('.processing-step').forEach(el => {
    el.classList.remove('active', 'done', 'error');
  });
  setProgress(0);
}

function handleProcessingStep(data) {
  const step = data.step;
  const status = data.status;
  const totalSteps = 8;

  // Update step indicators
  document.querySelectorAll('.processing-step').forEach(el => {
    const s = parseInt(el.dataset.step);
    if (s < step) { el.classList.remove('active'); el.classList.add('done'); }
    else if (s === step) {
      el.classList.remove('done');
      el.classList.add(status === 'error' ? 'error' : status === 'warning' ? 'error' : 'active');
      if (status === 'success') { el.classList.remove('active'); el.classList.add('done'); }
    }
  });

  // Update progress ring
  const pct = Math.round((step / totalSteps) * 100);
  setProgress(status === 'success' ? 100 : pct);

  document.getElementById('processingSubtitle').textContent = data.message || '';

  // If final success, load the graph into the editor
  if (status === 'success' && data.navigation_graph) {
    graphData = JSON.parse(JSON.stringify(data.navigation_graph));
    originalGraphData = JSON.parse(JSON.stringify(data.navigation_graph));
    currentDraftId = data.draft_id || null;
    currentFloor = parseInt(document.getElementById('floorSelect').value);
    floorImageUrl = data.floor_plan_image || '';
    loadFloorImage(floorImageUrl);
    updateGraphInfo();
    document.getElementById('emptyState').classList.add('hidden');
  }
}

function setProgress(pct) {
  const circumference = 2 * Math.PI * 42;
  const offset = circumference - (pct / 100) * circumference;
  document.getElementById('progressRing').style.strokeDashoffset = offset;
  document.getElementById('progressPercent').textContent = pct + '%';
}

// ── Load Existing Floor ────────────────────────────
async function loadExistingFloor() {
  try {
    const res = await fetch(`/admin/floor_data?floor=${currentFloor}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.graph_data) {
      graphData = data.graph_data;
      originalGraphData = JSON.parse(JSON.stringify(data.graph_data));
      currentDraftId = null;
      floorImageUrl = data.image_path || '';
      imgWidth = data.image_width || 0;
      imgHeight = data.image_height || 0;
      if (floorImageUrl) loadFloorImage(floorImageUrl);
      updateGraphInfo();
      document.getElementById('emptyState').classList.add('hidden');
    }
  } catch (e) { /* no existing data */ }
}

function loadFloorImage(url) {
  const img = new Image();
  img.onload = () => {
    floorPlanImage = img;
    imgWidth = img.naturalWidth;
    imgHeight = img.naturalHeight;
    fitToView();
  };
  img.src = url;
}

// ── Canvas Rendering ───────────────────────────────
function render() {
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(offsetX, offsetY);
  ctx.scale(scale, scale);

  // Draw floor plan image
  if (floorPlanImage) {
    ctx.drawImage(floorPlanImage, 0, 0, imgWidth, imgHeight);
  }

  // Draw edges
  graphData.edges.forEach((edge, eIdx) => {
    const fromNode = graphData.nodes.find(n => n.id === edge.from);
    const toNode = graphData.nodes.find(n => n.id === edge.to);
    if (!fromNode || !toNode) return;

    const pts = getEdgePoints(edge, fromNode, toNode);
    const isSelected = eIdx === selectedEdgeIdx;

    // Draw path
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.strokeStyle = isSelected ? 'rgba(232, 121, 249, 0.85)' : 'rgba(59, 130, 246, 0.7)';
    ctx.lineWidth = (isSelected ? 3.5 : 2.5) / scale;
    ctx.stroke();

    // Draw waypoint handles if selected
    const routePoints = edgeRoute(edge);
    if (isSelected && routePoints.length) {
      routePoints.forEach(wp => {
        ctx.beginPath();
        ctx.arc(wp.x, wp.y, WP_RADIUS / scale, 0, Math.PI * 2);
        ctx.fillStyle = '#e879f9';
        ctx.fill();
        ctx.strokeStyle = '#0a0e1a';
        ctx.lineWidth = 1.5 / scale;
        ctx.stroke();
      });
    }
  });

  // Draw edge-building preview line
  if (mode === 'add-edge' && edgeStartNodeId) {
    const startNode = graphData.nodes.find(n => n.id === edgeStartNodeId);
    if (startNode) {
      const mp = screenToGraph(lastMouse.x, lastMouse.y);
      // Draw from start node through all waypoints to mouse
      const pts = [{ x: startNode.x, y: startNode.y }];
      const startDoor = nodeAnchor(startNode);
      if (startDoor.x !== startNode.x || startDoor.y !== startNode.y) pts.push(startDoor);
      pts.push(...edgeWaypoints, mp);
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      ctx.strokeStyle = 'rgba(34, 211, 238, 0.6)';
      ctx.lineWidth = 2.5 / scale;
      ctx.setLineDash([6 / scale, 4 / scale]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw existing waypoints
      edgeWaypoints.forEach(wp => {
        ctx.beginPath();
        ctx.arc(wp.x, wp.y, 4 / scale, 0, Math.PI * 2);
        ctx.fillStyle = '#22d3ee';
        ctx.fill();
      });
    }
  }

  // Draw nodes
  for (const node of graphData.nodes) {
    const isSelected = node.id === selectedNodeId;
    const isEdgeStart = node.id === edgeStartNodeId;
    const r = NODE_RADIUS / scale;

    // Glow for selected
    if (isSelected || isEdgeStart) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + 6 / scale, 0, Math.PI * 2);
      ctx.fillStyle = isEdgeStart ? 'rgba(34, 211, 238, 0.15)' : 'rgba(232, 121, 249, 0.15)';
      ctx.fill();
    }

    // Node fill
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
    const color = getNodeColor(node.type);
    ctx.fillStyle = isSelected ? '#e879f9' : isEdgeStart ? '#22d3ee' : color;
    ctx.fill();

    // Node border
    ctx.strokeStyle = '#0a0e1a';
    ctx.lineWidth = 1.5 / scale;
    ctx.stroke();

    if (node.door && Number.isFinite(Number(node.door.x)) && Number.isFinite(Number(node.door.y))) {
      const doorSize = DOOR_SIZE / scale;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(node.door.x - doorSize / 2, node.door.y - doorSize / 2, doorSize, doorSize);
      ctx.strokeStyle = isSelected ? '#e879f9' : getNodeColor(node.type);
      ctx.lineWidth = (isSelected ? 2 : 1.5) / scale;
      ctx.strokeRect(node.door.x - doorSize / 2, node.door.y - doorSize / 2, doorSize, doorSize);
    }

    // Label
    if (node.label && node.type !== 'junction') {
      ctx.font = `${Math.max(10, 11 / scale)}px Inter, sans-serif`;
      ctx.fillStyle = '#e2e8f0';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';

      // Background for label
      const textWidth = ctx.measureText(node.label).width;
      const pad = 3 / scale;
      ctx.fillStyle = 'rgba(10, 14, 26, 0.75)';
      ctx.fillRect(node.x - textWidth / 2 - pad, node.y + r + 3 / scale, textWidth + pad * 2, 14 / scale);

      ctx.fillStyle = '#e2e8f0';
      ctx.fillText(node.label, node.x, node.y + r + 4 / scale);
    }
  }

  ctx.restore();

  // Update status
  document.getElementById('statusZoom').textContent = `Zoom: ${Math.round(scale * 100)}%`;
}

function getNodeColor(type) {
  const colors = {
    entrance: '#34d399', corridor: '#60a5fa', junction: '#94a3b8',
    staircase: '#fbbf24', elevator: '#fbbf24', restroom: '#a78bfa',
    nurse_station: '#f87171', waiting_area: '#fb923c', room: '#3b82f6',
  };
  return colors[type] || colors.room;
}

function canNodeHaveDoor(node) {
  return node && !['corridor', 'junction'].includes(node.type || 'room');
}

function canNodeConnect(edgeNode) {
  return !canNodeHaveDoor(edgeNode) || !!edgeNode.door;
}

// ── Canvas Events ──────────────────────────────────
function setupCanvasEvents() {
  canvas.addEventListener('mousedown', onMouseDown);
  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('mouseup', onMouseUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', e => e.preventDefault());
}

function screenToGraph(sx, sy) {
  return { x: (sx - offsetX) / scale, y: (sy - offsetY) / scale };
}

function hitTestNode(gx, gy) {
  const hitR = HIT_RADIUS / scale;
  for (let i = graphData.nodes.length - 1; i >= 0; i--) {
    const n = graphData.nodes[i];
    const dx = n.x - gx, dy = n.y - gy;
    if (dx * dx + dy * dy <= hitR * hitR) return n;
  }
  return null;
}

function hitTestDoor(gx, gy) {
  const hitR = DOOR_HIT_RADIUS / scale;
  for (let i = graphData.nodes.length - 1; i >= 0; i--) {
    const n = graphData.nodes[i];
    if (!n.door) continue;
    const dx = n.door.x - gx, dy = n.door.y - gy;
    if (dx * dx + dy * dy <= hitR * hitR) return n;
  }
  return null;
}

function nodeAnchor(node) {
  if (node && node.door && Number.isFinite(Number(node.door.x)) && Number.isFinite(Number(node.door.y))) {
    return { x: Number(node.door.x), y: Number(node.door.y) };
  }
  return { x: node.x, y: node.y };
}

function edgeRoute(edge) {
  if (Array.isArray(edge.path)) return edge.path;
  if (Array.isArray(edge.waypoints)) return edge.waypoints;
  return [];
}

function setEdgeRoute(edge, route) {
  if (route.length) edge.path = route;
  else delete edge.path;
  delete edge.waypoints;
}

function getOrthogonalRoute(fromNode, toNode) {
  const start = nodeAnchor(fromNode);
  const end = nodeAnchor(toNode);
  if (start.x === end.x || start.y === end.y) return [];
  return [{ x: Math.round(end.x), y: Math.round(start.y) }];
}

function getEdgePoints(edge, fromNode, toNode) {
  const fromDoor = nodeAnchor(fromNode);
  const toDoor = nodeAnchor(toNode);
  const route = edgeRoute(edge);
  const pts = [{ x: fromNode.x, y: fromNode.y }];
  if (fromDoor.x !== fromNode.x || fromDoor.y !== fromNode.y) pts.push(fromDoor);
  route.forEach(wp => pts.push({ x: wp.x, y: wp.y }));
  if (route.length === 0 && fromDoor.x !== toDoor.x && fromDoor.y !== toDoor.y) {
    pts.push({ x: toDoor.x, y: fromDoor.y });
  }
  if (toDoor.x !== toNode.x || toDoor.y !== toNode.y) pts.push(toDoor);
  pts.push({ x: toNode.x, y: toNode.y });
  return pts;
}

function hitTestEdge(gx, gy) {
  const threshold = EDGE_HIT_DIST / scale;
  for (let i = 0; i < graphData.edges.length; i++) {
    const edge = graphData.edges[i];
    const a = graphData.nodes.find(n => n.id === edge.from);
    const b = graphData.nodes.find(n => n.id === edge.to);
    if (!a || !b) continue;
    const pts = getEdgePoints(edge, a, b);
    for (let j = 0; j < pts.length - 1; j++) {
      const dist = pointToSegmentDist(gx, gy, pts[j].x, pts[j].y, pts[j+1].x, pts[j+1].y);
      if (dist < threshold) return { edge, index: i };
    }
  }
  return null;
}

function hitTestWaypoint(gx, gy) {
  const hitR = WP_HIT_RADIUS / scale;
  for (let i = 0; i < graphData.edges.length; i++) {
    const edge = graphData.edges[i];
    const route = edgeRoute(edge);
    for (let j = 0; j < route.length; j++) {
      const wp = route[j];
      const dx = wp.x - gx, dy = wp.y - gy;
      if (dx * dx + dy * dy <= hitR * hitR) return { edgeIdx: i, wpIdx: j };
    }
  }
  return null;
}

function pointToSegmentDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - ax, py - ay);
  let t = ((px - ax) * dx + (py - ay) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function onMouseDown(e) {
  const rect = canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
  const gp = screenToGraph(sx, sy);

  // Middle-click or space+click = pan
  if (e.button === 1 || (e.button === 0 && e.altKey)) {
    isPanning = true;
    panStart = { x: e.clientX - offsetX, y: e.clientY - offsetY };
    document.getElementById('canvasContainer').classList.add('panning');
    return;
  }

  if (e.button !== 0) return;

  if (mode === 'select') {
    const doorNode = hitTestDoor(gp.x, gp.y);
    const node = hitTestNode(gp.x, gp.y);
    // Check if clicking a waypoint on the selected edge
    const wpHit = hitTestWaypoint(gp.x, gp.y);
    if (wpHit && wpHit.edgeIdx === selectedEdgeIdx) {
      draggingWaypoint = wpHit;
      selectedNodeId = null;
      document.getElementById('nodeProperties').classList.remove('visible');
    } else if (doorNode) {
      selectedEdgeIdx = -1;
      selectNode(doorNode.id);
      draggingDoor = doorNode;
    } else if (node) {
      selectedEdgeIdx = -1;
      selectNode(node.id);
      draggingNode = node;
    } else {
      // Check edge hit
      const edgeHit = hitTestEdge(gp.x, gp.y);
      if (edgeHit) {
        selectedEdgeIdx = edgeHit.index;
        selectNode(null);
      } else {
        selectedEdgeIdx = -1;
        selectNode(null);
      }
    }
  } else if (mode === 'add-node') {
    pendingNodeX = Math.round(gp.x);
    pendingNodeY = Math.round(gp.y);
    document.getElementById('newNodeLabel').value = '';
    document.getElementById('addNodeModal').classList.add('visible');
    document.getElementById('newNodeLabel').focus();
  } else if (mode === 'add-door') {
    const node = hitTestNode(gp.x, gp.y);
    if (!doorTargetNodeId) {
      if (!node) {
        showToast('Click a room/location node first', 'info');
      } else if (!canNodeHaveDoor(node)) {
        showToast('Corridors and junctions do not need doors', 'error');
      } else {
        doorTargetNodeId = node.id;
        selectNode(node.id);
        showToast('Now click the doorway/entry point', 'info');
      }
    } else {
      const target = graphData.nodes.find(n => n.id === doorTargetNodeId);
      if (target) {
        target.door = { x: Math.round(gp.x), y: Math.round(gp.y) };
        updatePropertyValues();
        scheduleDraftSave();
        showToast(`Door placed for ${target.label || target.id}`, 'success');
      }
      doorTargetNodeId = null;
      setMode('select');
    }
  } else if (mode === 'add-edge') {
    const node = hitTestNode(gp.x, gp.y);
    if (!edgeStartNodeId) {
      // Must click a node to start
      if (node) {
        if (!canNodeConnect(node)) {
          showToast('Add a door to this room before connecting an edge', 'error');
          render();
          return;
        }
        edgeStartNodeId = node.id;
        edgeWaypoints = [];
        showToast('Click empty space for bends, click target node to finish', 'info');
      }
    } else if (node && node.id !== edgeStartNodeId) {
      if (!canNodeConnect(node)) {
        showToast('Add a door to the target room before connecting an edge', 'error');
        render();
        return;
      }
      // Clicked target node — finish edge
      const exists = graphData.edges.some(e =>
        (e.from === edgeStartNodeId && e.to === node.id) ||
        (e.from === node.id && e.to === edgeStartNodeId)
      );
      if (!exists) {
        const newEdge = { from: edgeStartNodeId, to: node.id };
        if (edgeWaypoints.length > 0) {
          newEdge.path = edgeWaypoints.map(wp => ({ x: Math.round(wp.x), y: Math.round(wp.y) }));
        } else {
          const fromNode = graphData.nodes.find(n => n.id === edgeStartNodeId);
          const route = getOrthogonalRoute(fromNode, node);
          if (route.length) newEdge.path = route;
        }
        graphData.edges.push(newEdge);
        updateGraphInfo();
      }
      edgeStartNodeId = null;
      edgeWaypoints = [];
    } else if (!node) {
      // Clicked empty space — add bend/waypoint
      edgeWaypoints.push({ x: Math.round(gp.x), y: Math.round(gp.y) });
    }
  } else if (mode === 'delete') {
    const doorNode = hitTestDoor(gp.x, gp.y);
    if (doorNode) {
      delete doorNode.door;
      if (selectedNodeId === doorNode.id) updatePropertyValues();
      scheduleDraftSave();
      render();
      return;
    }
    const node = hitTestNode(gp.x, gp.y);
    if (node) {
      graphData.nodes = graphData.nodes.filter(n => n.id !== node.id);
      graphData.edges = graphData.edges.filter(e => e.from !== node.id && e.to !== node.id);
      if (selectedNodeId === node.id) selectNode(null);
      selectedEdgeIdx = -1;
      updateGraphInfo();
    } else {
      // Check waypoint first
      const wpHit = hitTestWaypoint(gp.x, gp.y);
      if (wpHit) {
        const edge = graphData.edges[wpHit.edgeIdx];
        const route = edgeRoute(edge).slice();
        route.splice(wpHit.wpIdx, 1);
        setEdgeRoute(edge, route);
        scheduleDraftSave();
      } else {
        const edgeHit = hitTestEdge(gp.x, gp.y);
        if (edgeHit) {
          graphData.edges.splice(edgeHit.index, 1);
          selectedEdgeIdx = -1;
          updateGraphInfo();
        }
      }
    }
  }

  render();
}

function onMouseMove(e) {
  const rect = canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
  lastMouse = { x: sx, y: sy };

  if (isPanning) {
    offsetX = e.clientX - panStart.x;
    offsetY = e.clientY - panStart.y;
    render();
    return;
  }

  if (draggingWaypoint) {
    const gp = screenToGraph(sx, sy);
    const edge = graphData.edges[draggingWaypoint.edgeIdx];
    if (edge) {
      const route = edgeRoute(edge).slice();
      route[draggingWaypoint.wpIdx] = { x: Math.round(gp.x), y: Math.round(gp.y) };
      setEdgeRoute(edge, route);
    }
    render();
    return;
  }

  if (draggingDoor) {
    const gp = screenToGraph(sx, sy);
    draggingDoor.door = { x: Math.round(gp.x), y: Math.round(gp.y) };
    updatePropertyValues();
    render();
    return;
  }

  if (draggingNode) {
    const gp = screenToGraph(sx, sy);
    draggingNode.x = Math.round(gp.x);
    draggingNode.y = Math.round(gp.y);
    updatePropertyValues();
    render();
    return;
  }

  // Update status bar with mouse coords
  const gp = screenToGraph(sx, sy);
  document.getElementById('statusMouse').textContent = `X: ${Math.round(gp.x)} Y: ${Math.round(gp.y)}`;

  // Redraw for edge preview line
  if (mode === 'add-edge' && edgeStartNodeId) render();
}

function onMouseUp() {
  if (isPanning) {
    isPanning = false;
    document.getElementById('canvasContainer').classList.remove('panning');
  }
  if (draggingNode || draggingDoor || draggingWaypoint) scheduleDraftSave();
  draggingNode = null;
  draggingDoor = null;
  draggingWaypoint = null;
}

function onWheel(e) {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;

  const zoomFactor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const newScale = Math.max(0.1, Math.min(10, scale * zoomFactor));

  // Zoom toward cursor
  offsetX = mx - (mx - offsetX) * (newScale / scale);
  offsetY = my - (my - offsetY) * (newScale / scale);
  scale = newScale;
  render();
}

// ── Node Selection & Properties ────────────────────
function selectNode(id) {
  selectedNodeId = id;
  const panel = document.getElementById('nodeProperties');
  if (!id) {
    panel.classList.remove('visible');
    render();
    return;
  }
  panel.classList.add('visible');
  updatePropertyValues();
  render();
}

function updatePropertyValues() {
  const node = graphData.nodes.find(n => n.id === selectedNodeId);
  if (!node) return;
  document.getElementById('propNodeId').textContent = node.id;
  document.getElementById('propLabel').value = node.label || '';
  document.getElementById('propType').value = node.type || 'room';
  document.getElementById('propX').value = node.x;
  document.getElementById('propY').value = node.y;
  document.getElementById('propDoorX').value = node.door ? node.door.x : '';
  document.getElementById('propDoorY').value = node.door ? node.door.y : '';
}

function setupPropertyListeners() {
  document.getElementById('propLabel').addEventListener('input', e => {
    const node = graphData.nodes.find(n => n.id === selectedNodeId);
    if (node) { node.label = e.target.value; render(); scheduleDraftSave(); }
  });
  document.getElementById('propType').addEventListener('change', e => {
    const node = graphData.nodes.find(n => n.id === selectedNodeId);
    if (node) { node.type = e.target.value; render(); scheduleDraftSave(); }
  });
  document.getElementById('propX').addEventListener('change', e => {
    const node = graphData.nodes.find(n => n.id === selectedNodeId);
    if (node) { node.x = parseInt(e.target.value) || 0; render(); scheduleDraftSave(); }
  });
  document.getElementById('propY').addEventListener('change', e => {
    const node = graphData.nodes.find(n => n.id === selectedNodeId);
    if (node) { node.y = parseInt(e.target.value) || 0; render(); scheduleDraftSave(); }
  });
  document.getElementById('propDoorX').addEventListener('change', updateSelectedDoor);
  document.getElementById('propDoorY').addEventListener('change', updateSelectedDoor);
}

function updateSelectedDoor() {
  const node = graphData.nodes.find(n => n.id === selectedNodeId);
  if (!node) return;
  const doorX = document.getElementById('propDoorX').value;
  const doorY = document.getElementById('propDoorY').value;
  if (doorX === '' || doorY === '') {
    delete node.door;
  } else {
    node.door = { x: parseInt(doorX) || 0, y: parseInt(doorY) || 0 };
  }
  render();
  scheduleDraftSave();
}

function startDoorForSelectedNode() {
  const node = graphData.nodes.find(n => n.id === selectedNodeId);
  if (!node) {
    showToast('Select a room/location node first', 'info');
    return;
  }
  if (!canNodeHaveDoor(node)) {
    showToast('Corridors and junctions do not need doors', 'error');
    return;
  }
  setMode('add-door');
  doorTargetNodeId = node.id;
  showToast('Click the doorway/entry point on the map', 'info');
}

function deleteSelectedNode() {
  if (!selectedNodeId) return;
  graphData.nodes = graphData.nodes.filter(n => n.id !== selectedNodeId);
  graphData.edges = graphData.edges.filter(e => e.from !== selectedNodeId && e.to !== selectedNodeId);
  selectNode(null);
  updateGraphInfo();
  render();
}

// ── Toolbar Modes ──────────────────────────────────
function setMode(newMode) {
  mode = newMode;
  edgeStartNodeId = null;
  edgeWaypoints = [];
  doorTargetNodeId = null;
  selectedEdgeIdx = -1;
  document.querySelectorAll('.tool-btn[data-mode]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === newMode);
  });
  const container = document.getElementById('canvasContainer');
  container.className = 'canvas-container mode-' + newMode;

  const hints = {
    'select': 'Click & drag nodes or waypoints. Click edges to select.',
    'add-node': 'Click on the image to place a node',
    'add-door': 'Click a room/location node, then click its doorway/entry point.',
    'add-edge': 'Click start node, optional bends, then end node. No bends creates a 90-degree route.',
    'delete': 'Click a node, door, edge, or waypoint to delete it'
  };
  document.getElementById('toolbarHint').textContent = hints[newMode] || '';
  document.getElementById('statusMode').textContent = 'Mode: ' + newMode.replace('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
  render();
}

// ── Add Node Modal ─────────────────────────────────
function cancelAddNode() {
  document.getElementById('addNodeModal').classList.remove('visible');
}

function confirmAddNode() {
  const label = document.getElementById('newNodeLabel').value.trim();
  const type = document.getElementById('newNodeType').value;
  if (!label) { showToast('Please enter a label', 'error'); return; }

  const id = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  // Ensure unique ID
  let uniqueId = id;
  let counter = 1;
  while (graphData.nodes.some(n => n.id === uniqueId)) {
    uniqueId = id + '_' + counter++;
  }

  graphData.nodes.push({ id: uniqueId, label, type, x: pendingNodeX, y: pendingNodeY });
  updateGraphInfo();
  document.getElementById('addNodeModal').classList.remove('visible');
  selectNode(uniqueId);
  render();
}

// Handle Enter key in add-node modal
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.getElementById('addNodeModal').classList.contains('visible')) {
    confirmAddNode();
  }
  if (e.key === 'Escape') {
    cancelAddNode();
    if (mode === 'add-edge') { edgeStartNodeId = null; edgeWaypoints = []; }
    if (mode === 'add-door') { doorTargetNodeId = null; }
    selectedEdgeIdx = -1;
    render();
  }
  // Delete key deletes selected node or edge
  if (e.key === 'Delete' && mode === 'select') {
    if (selectedNodeId) deleteSelectedNode();
    else if (selectedEdgeIdx >= 0) {
      graphData.edges.splice(selectedEdgeIdx, 1);
      selectedEdgeIdx = -1;
      updateGraphInfo();
      render();
    }
  }
});

// ── Zoom Controls ──────────────────────────────────
function zoomIn() {
  const cx = canvas.width / 2, cy = canvas.height / 2;
  const newScale = Math.min(10, scale * 1.3);
  offsetX = cx - (cx - offsetX) * (newScale / scale);
  offsetY = cy - (cy - offsetY) * (newScale / scale);
  scale = newScale;
  render();
}

function zoomOut() {
  const cx = canvas.width / 2, cy = canvas.height / 2;
  const newScale = Math.max(0.1, scale / 1.3);
  offsetX = cx - (cx - offsetX) * (newScale / scale);
  offsetY = cy - (cy - offsetY) * (newScale / scale);
  scale = newScale;
  render();
}

function fitToView() {
  if (!imgWidth || !imgHeight) return;
  const pad = 40;
  const scaleX = (canvas.width - pad * 2) / imgWidth;
  const scaleY = (canvas.height - pad * 2) / imgHeight;
  scale = Math.min(scaleX, scaleY);
  offsetX = (canvas.width - imgWidth * scale) / 2;
  offsetY = (canvas.height - imgHeight * scale) / 2;
  render();
}

// ── Graph Info ─────────────────────────────────────
function updateGraphInfo() {
  document.getElementById('statNodes').textContent = graphData.nodes.length;
  document.getElementById('statEdges').textContent = graphData.edges.length;
  document.getElementById('graphInfo').classList.add('visible');
  scheduleDraftSave();
}

// ── Save & Reset ───────────────────────────────────
function normalizeGraphForSave() {
  return {
    nodes: graphData.nodes.map(node => {
      const cleanNode = { ...node };
      if (cleanNode.door) {
        const doorX = Number(cleanNode.door.x);
        const doorY = Number(cleanNode.door.y);
        if (Number.isFinite(doorX) && Number.isFinite(doorY)) {
          cleanNode.door = { x: Math.round(doorX), y: Math.round(doorY) };
        } else {
          delete cleanNode.door;
        }
      }
      return cleanNode;
    }),
    edges: graphData.edges.map(edge => {
      const cleanEdge = { from: edge.from, to: edge.to };
      const route = edgeRoute(edge).map(wp => ({ x: Math.round(wp.x), y: Math.round(wp.y) }));
      if (route.length) cleanEdge.path = route;
      return cleanEdge;
    })
  };
}

function scheduleDraftSave() {
  if (!currentDraftId) return;
  clearTimeout(draftSaveTimer);
  draftSaveTimer = setTimeout(saveDraftNow, DRAFT_SAVE_DELAY);
}

async function saveDraftNow() {
  if (!currentDraftId) return;
  clearTimeout(draftSaveTimer);
  draftSaveTimer = null;
  try {
    await fetch('/admin/save_draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        draft_id: currentDraftId,
        floor: currentFloor,
        graph_data: normalizeGraphForSave()
      })
    });
  } catch (err) {
    console.warn('Draft save failed:', err);
  }
}

async function saveGraph() {
  const btn = document.getElementById('saveBtn');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    const graphToSave = normalizeGraphForSave();
    const res = await fetch('/admin/save_graph', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        floor: currentFloor,
        graph_data: graphToSave,
        update_vectors: true,
        draft_id: currentDraftId
      })
    });
    const data = await res.json();
    if (res.ok) {
      graphData = graphToSave;
      originalGraphData = JSON.parse(JSON.stringify(graphToSave));
      if (data.graph_log) {
        console.group('Saved navigation graph');
        console.log('Counts:', data.graph_log.counts);
        console.table(data.graph_log.nodes);
        console.table(data.graph_log.edges.map(edge => ({
          index: edge.index,
          from: edge.from,
          to: edge.to,
          bends: edge.path.length,
          expanded_route: edge.expanded_route.map(p => `${p.kind}:${p.id || ''}(${p.x},${p.y})`).join(' -> ')
        })));
        console.log('Full graph log:', data.graph_log);
        console.groupEnd();
      }
      showToast('Graph saved to database!', 'success');
    } else {
      showToast('Save failed: ' + (data.detail || data.message), 'error');
    }
  } catch (err) {
    showToast('Save failed: ' + err.message, 'error');
  }

  btn.disabled = false;
  btn.textContent = 'Save to Database';
}

function resetGraph() {
  if (!originalGraphData) return;
  graphData = JSON.parse(JSON.stringify(originalGraphData));
  selectNode(null);
  updateGraphInfo();
  render();
  showToast('Graph reset to AI extraction', 'info');
}

// ── Toast Notifications ────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span> ${message}`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toast-out 0.3s ease-in forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
