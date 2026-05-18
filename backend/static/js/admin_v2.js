/**
 * Admin Floor Plan Editor (V2) — Door + Walkable Polyline Authoring
 * - Rooms are metadata entities (not routing nodes)
 * - Doors are anchors
 * - Walkable paths are polylines; backend derives topology + routing graph
 */

let floorPlanImage = null;
let floorImageUrl = '';
let currentFloor = 1;
let imgWidth = 0, imgHeight = 0;
let currentDraftId = null;
let draftSaveTimer = null;
let selectedUploadFile = null;

// Authoring state (V2)
let v2 = {
  rooms: [],
  doors: [],
  walkable_paths: [],
  junctions: [],
  graph: { nodes: [], edges: [] },
  meta: { tolerances: { snap_eps_px: 12, min_segment_len_px: 6, grid_cell_px: 64 }, sources: {} }
};

// Canvas state
let canvas, ctx;
let scale = 1, offsetX = 0, offsetY = 0;
let mode = 'select'; // select, add-room, add-door, draw-path, edit-path, delete
let selected = { kind: null, id: null, pathId: null, pointIdx: -1 };
let isPanning = false;
let panStart = { x: 0, y: 0 };
let lastMouse = { x: 0, y: 0 };
let draggingRoomId = null;
let draggingDoorId = null;
let draggingPathPoint = null; // { pathId, pointIdx }

// Draw-path state
let activePathId = null;
let drawing = false;
const DRAW_MIN_DIST = 10;

const ROOM_R = 9;
const DOOR_SIZE = 8;
const HIT_R = 14;
const POINT_R = 5;
const DRAFT_SAVE_DELAY = 700;

document.addEventListener('DOMContentLoaded', () => {
  canvas = document.getElementById('graphCanvas');
  ctx = canvas.getContext('2d');
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  setupDropZone();
  setupCanvasEvents();
  setupToolbar();

  loadExistingFloor();
});

function resizeCanvas() {
  const container = document.getElementById('canvasContainer');
  canvas.width = container.clientWidth;
  canvas.height = container.clientHeight;
  render();
}

function setMode(newMode) {
  mode = newMode;
  drawing = false;
  activePathId = null;
  selected = { kind: null, id: null, pathId: null, pointIdx: -1 };
  draggingRoomId = null;
  draggingDoorId = null;
  draggingPathPoint = null;
  document.querySelectorAll('.tool-btn[data-mode]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === newMode);
  });
  const container = document.getElementById('canvasContainer');
  container.className = 'canvas-container mode-' + newMode;

  const hints = {
    'select': 'Select & drag rooms/doors/points. Click path to select.',
    'add-room': 'Click on the image to place a room',
    'add-door': 'Click a room, then click to place a door (multiple allowed)',
    'draw-path': 'Click to start a path, click to add points, double-click to finish',
    'edit-path': 'Click a path point to drag; click path to select',
    'delete': 'Click a room, door, path, or point to delete'
  };
  document.getElementById('toolbarHint').textContent = hints[newMode] || '';
  render();
}

function setupToolbar() {
  // Mode buttons in HTML call setMode()
  setMode('select');
}

// --- Upload / load ---
function setupDropZone() {
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const uploadBtn = document.getElementById('uploadBtn');
  const filePreview = document.getElementById('filePreview');

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

  document.getElementById('fileRemove').addEventListener('click', () => {
    fileInput.value = '';
    selectedUploadFile = null;
    filePreview.classList.remove('visible');
    uploadBtn.disabled = true;
  });

  document.getElementById('floorSelect').addEventListener('change', e => {
    currentFloor = parseInt(e.target.value);
    currentDraftId = null;
    v2 = freshV2();
    floorPlanImage = null;
    floorImageUrl = '';
    document.getElementById('emptyState').classList.remove('hidden');
    document.getElementById('graphInfo').classList.remove('visible');
    loadExistingFloor();
    render();
  });

  uploadBtn.addEventListener('click', uploadAndProcess);
}

function handleFile(file) {
  if (!file.type.startsWith('image/')) { showToast('Please select an image file', 'error'); return; }
  selectedUploadFile = file;
  document.getElementById('fileName').textContent = file.name;
  document.getElementById('filePreview').classList.add('visible');
  document.getElementById('uploadBtn').disabled = false;
}

function freshV2() {
  return {
    rooms: [], doors: [], walkable_paths: [], junctions: [], graph: { nodes: [], edges: [] },
    meta: { tolerances: { snap_eps_px: 12, min_segment_len_px: 6, grid_cell_px: 64 }, sources: {} }
  };
}

async function uploadAndProcess() {
  const fileInput = document.getElementById('fileInput');
  const file = fileInput.files[0] || selectedUploadFile;
  if (!file) {
    showToast('Select or drop an image first', 'info');
    return;
  }
  const floorNumber = parseInt(document.getElementById('floorSelect').value);
  const extraction_method = document.getElementById('methodSelect').value;

  const formData = new FormData();
  formData.append('file', file);
  formData.append('floor_number', floorNumber);
  formData.append('extraction_method', extraction_method);

  showProcessing(true);
  setProgress(0);

  try {
    const response = await fetch('/update_floor_plan', { method: 'POST', body: formData });
    if (!response.ok) throw new Error('Upload failed');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        const data = JSON.parse(line);
        onStreamUpdate(data);
      }
    }
  } catch (err) {
    showToast('Upload failed: ' + err.message, 'error');
  } finally {
    showProcessing(false);
  }
}

function onStreamUpdate(data) {
  const status = data.status || '';
  const step = data.step || 0;
  const pct = Math.min(100, Math.max(0, (step / 8) * 100));
  setProgress(status === 'success' ? 100 : pct);
  document.getElementById('processingSubtitle').textContent = data.message || '';

  if (status === 'success' && data.navigation_graph) {
    currentDraftId = data.draft_id || null;
    currentFloor = parseInt(document.getElementById('floorSelect').value);
    floorImageUrl = data.floor_plan_image || '';
    loadFloorImage(floorImageUrl);
    loadGraphData(data.navigation_graph);
    updateGraphInfo();
    document.getElementById('emptyState').classList.add('hidden');
  }
}

async function loadExistingFloor() {
  try {
    const res = await fetch(`/admin/floor_data?floor=${currentFloor}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.graph_data) {
      currentDraftId = null;
      floorImageUrl = data.image_path || '';
      imgWidth = data.image_width || 0;
      imgHeight = data.image_height || 0;
      if (floorImageUrl) loadFloorImage(floorImageUrl);
      loadGraphData(data.graph_data);
      updateGraphInfo();
      document.getElementById('emptyState').classList.add('hidden');
    }
  } catch (e) { /* no existing */ }
}

function loadGraphData(graphData) {
  // Accept schema v2 dual-store or v2-only
  if (graphData && graphData.schema_version === 2 && graphData.v2) {
    v2 = JSON.parse(JSON.stringify(graphData.v2));
  } else if (graphData && graphData.rooms && graphData.walkable_paths) {
    v2 = JSON.parse(JSON.stringify(graphData));
  } else {
    v2 = freshV2();
  }
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

function updateGraphInfo() {
  document.getElementById('statNodes').textContent = v2.rooms.length + v2.doors.length;
  document.getElementById('statEdges').textContent = v2.walkable_paths.length;
  document.getElementById('graphInfo').classList.add('visible');
  scheduleDraftSave();
}

// --- Save ---
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
        graph_data: { schema_version: 2, v1: { nodes: [], edges: [] }, v2 }
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
    const res = await fetch('/admin/save_graph', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        floor: currentFloor,
        graph_data: { schema_version: 2, v1: { nodes: [], edges: [] }, v2 },
        update_vectors: true,
        draft_id: currentDraftId
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.message || 'Save failed');
    showToast('Saved!', 'success');
  } catch (err) {
    showToast('Save failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save to Database';
  }
}

// --- Canvas interaction ---
function setupCanvasEvents() {
  const container = document.getElementById('canvasContainer');
  container.addEventListener('mousedown', onMouseDown);
  container.addEventListener('mousemove', onMouseMove);
  container.addEventListener('mouseup', onMouseUp);
  container.addEventListener('mouseleave', onMouseUp);
  container.addEventListener('wheel', onWheel, { passive: false });
  container.addEventListener('dblclick', onDoubleClick);

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      drawing = false;
      activePathId = null;
      render();
    }
    if (e.key === 'Delete' && mode === 'select') {
      deleteSelection();
    }
  });
}

function screenToGraph(sx, sy) {
  return { x: (sx - offsetX) / scale, y: (sy - offsetY) / scale };
}

function graphToScreen(gx, gy) {
  return { x: gx * scale + offsetX, y: gy * scale + offsetY };
}

function hitRoom(gx, gy) {
  for (const r of v2.rooms) {
    const dx = gx - (r.x || 0), dy = gy - (r.y || 0);
    if (dx * dx + dy * dy <= (HIT_R / scale) * (HIT_R / scale)) return r;
  }
  return null;
}

function hitDoor(gx, gy) {
  const hit = HIT_R / scale;
  for (const d of v2.doors) {
    if (Math.abs(gx - d.x) <= hit && Math.abs(gy - d.y) <= hit) return d;
  }
  return null;
}

function hitPathPoint(gx, gy) {
  const hit = (HIT_R / scale);
  for (const p of v2.walkable_paths) {
    const pts = p.points || [];
    for (let i = 0; i < pts.length; i++) {
      const pt = pts[i];
      const dx = gx - pt.x, dy = gy - pt.y;
      if (dx * dx + dy * dy <= hit * hit) return { pathId: p.id, pointIdx: i };
    }
  }
  return null;
}

function hitPathSegment(gx, gy) {
  const threshold = 10 / scale;
  for (const p of v2.walkable_paths) {
    const pts = p.points || [];
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1];
      const dist = pointToSegmentDist(gx, gy, a.x, a.y, b.x, b.y);
      if (dist < threshold) return p;
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
  lastMouse = { x: sx, y: sy };
  const gp = screenToGraph(sx, sy);

  // Pan: middle click or alt+click
  if (e.button === 1 || (e.button === 0 && e.altKey)) {
    isPanning = true;
    panStart = { x: e.clientX - offsetX, y: e.clientY - offsetY };
    document.getElementById('canvasContainer').classList.add('panning');
    return;
  }

  if (e.button !== 0) return;

  if (mode === 'add-room') {
    openRoomModal(Math.round(gp.x), Math.round(gp.y));
    return;
  }

  if (mode === 'add-door') {
    const room = hitRoom(gp.x, gp.y);
    if (room) {
      selected = { kind: 'room', id: room.id, pathId: null, pointIdx: -1 };
      showToast('Now click where the door is', 'info');
      render();
      return;
    }
    if (selected.kind === 'room' && selected.id) {
      const doorId = `door_${selected.id}_${Date.now()}`;
      v2.doors.push({ id: doorId, room_id: selected.id, x: Math.round(gp.x), y: Math.round(gp.y), connected_to: null, meta: { source: 'manual' } });
      const r = v2.rooms.find(rr => rr.id === selected.id);
      if (r) {
        if (!Array.isArray(r.door_ids)) r.door_ids = [];
        r.door_ids.push(doorId);
      }
      scheduleDraftSave();
      updateGraphInfo();
      showToast('Door added', 'success');
      render();
    }
    return;
  }

  if (mode === 'draw-path') {
    if (!drawing) {
      const pathId = `path_${Date.now()}`;
      v2.walkable_paths.push({ id: pathId, points: [{ x: Math.round(gp.x), y: Math.round(gp.y) }], meta: { source: 'manual' } });
      activePathId = pathId;
      drawing = true;
      scheduleDraftSave();
      updateGraphInfo();
      render();
      return;
    }
    const path = v2.walkable_paths.find(p => p.id === activePathId);
    if (!path) return;
    const last = path.points[path.points.length - 1];
    const d = Math.hypot(last.x - gp.x, last.y - gp.y);
    if (d >= DRAW_MIN_DIST) {
      path.points.push({ x: Math.round(gp.x), y: Math.round(gp.y) });
      scheduleDraftSave();
      render();
    }
    return;
  }

  if (mode === 'edit-path') {
    const hit = hitPathPoint(gp.x, gp.y);
    if (hit) {
      draggingPathPoint = hit;
      selected = { kind: 'path_point', id: null, pathId: hit.pathId, pointIdx: hit.pointIdx };
      render();
      return;
    }
    const p = hitPathSegment(gp.x, gp.y);
    if (p) {
      selected = { kind: 'path', id: p.id, pathId: p.id, pointIdx: -1 };
      render();
    }
    return;
  }

  if (mode === 'delete') {
    const door = hitDoor(gp.x, gp.y);
    if (door) {
      deleteDoor(door.id);
      return;
    }
    const room = hitRoom(gp.x, gp.y);
    if (room) {
      deleteRoom(room.id);
      return;
    }
    const pt = hitPathPoint(gp.x, gp.y);
    if (pt) {
      deletePathPoint(pt.pathId, pt.pointIdx);
      return;
    }
    const path = hitPathSegment(gp.x, gp.y);
    if (path) {
      deletePath(path.id);
      return;
    }
  }

  // select mode
  if (mode === 'select') {
    const pt = hitPathPoint(gp.x, gp.y);
    if (pt) {
      draggingPathPoint = pt;
      selected = { kind: 'path_point', id: null, pathId: pt.pathId, pointIdx: pt.pointIdx };
      render();
      return;
    }
    const door = hitDoor(gp.x, gp.y);
    if (door) {
      selected = { kind: 'door', id: door.id, pathId: null, pointIdx: -1 };
      draggingDoorId = door.id;
      render();
      return;
    }
    const room = hitRoom(gp.x, gp.y);
    if (room) {
      selected = { kind: 'room', id: room.id, pathId: null, pointIdx: -1 };
      draggingRoomId = room.id;
      render();
      return;
    }
    const path = hitPathSegment(gp.x, gp.y);
    if (path) {
      selected = { kind: 'path', id: path.id, pathId: path.id, pointIdx: -1 };
      render();
      return;
    }
    selected = { kind: null, id: null, pathId: null, pointIdx: -1 };
    render();
  }
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

  const gp = screenToGraph(sx, sy);

  if (draggingRoomId) {
    const r = v2.rooms.find(x => x.id === draggingRoomId);
    if (r) { r.x = Math.round(gp.x); r.y = Math.round(gp.y); scheduleDraftSave(); render(); }
    return;
  }
  if (draggingDoorId) {
    const d = v2.doors.find(x => x.id === draggingDoorId);
    if (d) { d.x = Math.round(gp.x); d.y = Math.round(gp.y); scheduleDraftSave(); render(); }
    return;
  }
  if (draggingPathPoint) {
    const p = v2.walkable_paths.find(x => x.id === draggingPathPoint.pathId);
    if (p && p.points && p.points[draggingPathPoint.pointIdx]) {
      p.points[draggingPathPoint.pointIdx] = { x: Math.round(gp.x), y: Math.round(gp.y) };
      scheduleDraftSave();
      render();
    }
    return;
  }

  if (mode === 'draw-path' && drawing && activePathId) {
    render(); // redraw preview line
  }
}

function onMouseUp() {
  if (isPanning) {
    isPanning = false;
    document.getElementById('canvasContainer').classList.remove('panning');
  }
  draggingRoomId = null;
  draggingDoorId = null;
  draggingPathPoint = null;
}

function onDoubleClick(e) {
  if (mode !== 'draw-path' || !drawing || !activePathId) return;
  const path = v2.walkable_paths.find(p => p.id === activePathId);
  if (path && (path.points || []).length < 2) {
    // discard single-point path
    v2.walkable_paths = v2.walkable_paths.filter(p => p.id !== activePathId);
  }
  drawing = false;
  activePathId = null;
  scheduleDraftSave();
  updateGraphInfo();
  render();
}

function onWheel(e) {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const zoomFactor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const newScale = Math.max(0.1, Math.min(10, scale * zoomFactor));
  offsetX = mx - (mx - offsetX) * (newScale / scale);
  offsetY = my - (my - offsetY) * (newScale / scale);
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

// --- CRUD helpers ---
function deleteRoom(roomId) {
  const room = v2.rooms.find(r => r.id === roomId);
  const doorIds = new Set((room && room.door_ids) || []);
  v2.doors = v2.doors.filter(d => !(d.room_id === roomId || doorIds.has(d.id)));
  v2.rooms = v2.rooms.filter(r => r.id !== roomId);
  selected = { kind: null, id: null, pathId: null, pointIdx: -1 };
  scheduleDraftSave();
  updateGraphInfo();
  render();
}

function deleteDoor(doorId) {
  const door = v2.doors.find(d => d.id === doorId);
  if (door) {
    const room = v2.rooms.find(r => r.id === door.room_id);
    if (room && Array.isArray(room.door_ids)) room.door_ids = room.door_ids.filter(id => id !== doorId);
  }
  v2.doors = v2.doors.filter(d => d.id !== doorId);
  selected = { kind: null, id: null, pathId: null, pointIdx: -1 };
  scheduleDraftSave();
  updateGraphInfo();
  render();
}

function deletePath(pathId) {
  v2.walkable_paths = v2.walkable_paths.filter(p => p.id !== pathId);
  selected = { kind: null, id: null, pathId: null, pointIdx: -1 };
  scheduleDraftSave();
  updateGraphInfo();
  render();
}

function deletePathPoint(pathId, idx) {
  const p = v2.walkable_paths.find(x => x.id === pathId);
  if (!p) return;
  p.points.splice(idx, 1);
  if (p.points.length < 2) {
    v2.walkable_paths = v2.walkable_paths.filter(x => x.id !== pathId);
  }
  scheduleDraftSave();
  updateGraphInfo();
  render();
}

function deleteSelection() {
  if (selected.kind === 'room') return deleteRoom(selected.id);
  if (selected.kind === 'door') return deleteDoor(selected.id);
  if (selected.kind === 'path') return deletePath(selected.id);
  if (selected.kind === 'path_point') return deletePathPoint(selected.pathId, selected.pointIdx);
}

// --- Modal ---
let pendingRoomX = 0, pendingRoomY = 0;
function openRoomModal(x, y) {
  pendingRoomX = x;
  pendingRoomY = y;
  document.getElementById('newNodeLabel').value = '';
  document.getElementById('addNodeModal').classList.add('visible');
  document.getElementById('newNodeLabel').focus();
}

function cancelAddNode() {
  document.getElementById('addNodeModal').classList.remove('visible');
}

function confirmAddNode() {
  const label = document.getElementById('newNodeLabel').value.trim();
  const type = document.getElementById('newNodeType').value;
  if (!label) { showToast('Please enter a label', 'error'); return; }
  const baseId = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  let uniqueId = baseId || ('room_' + Date.now());
  let counter = 1;
  while (v2.rooms.some(r => r.id === uniqueId)) uniqueId = (baseId || 'room') + '_' + counter++;
  v2.rooms.push({ id: uniqueId, label, type, x: pendingRoomX, y: pendingRoomY, door_ids: [], meta: { source: 'manual' } });
  cancelAddNode();
  selected = { kind: 'room', id: uniqueId, pathId: null, pointIdx: -1 };
  scheduleDraftSave();
  updateGraphInfo();
  render();
}

// --- Render ---
function render() {
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(offsetX, offsetY);
  ctx.scale(scale, scale);

  if (floorPlanImage) ctx.drawImage(floorPlanImage, 0, 0, imgWidth, imgHeight);

  // Walkable paths
  for (const p of v2.walkable_paths) {
    const pts = p.points || [];
    if (pts.length < 2) continue;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    const selectedPath = selected.kind === 'path' && selected.id === p.id;
    ctx.strokeStyle = selectedPath ? 'rgba(232, 121, 249, 0.9)' : 'rgba(34, 211, 238, 0.7)';
    ctx.lineWidth = (selectedPath ? 4 : 3) / scale;
    ctx.stroke();

    // points
    if (mode === 'edit-path' || selectedPath || selected.kind === 'path_point') {
      for (let i = 0; i < pts.length; i++) {
        const pt = pts[i];
        const isSelPt = selected.kind === 'path_point' && selected.pathId === p.id && selected.pointIdx === i;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, (isSelPt ? 6 : POINT_R) / scale, 0, Math.PI * 2);
        ctx.fillStyle = isSelPt ? '#e879f9' : '#22d3ee';
        ctx.fill();
        ctx.strokeStyle = '#0a0e1a';
        ctx.lineWidth = 1.2 / scale;
        ctx.stroke();
      }
    }
  }

  // Draw-path preview
  if (mode === 'draw-path' && drawing && activePathId) {
    const p = v2.walkable_paths.find(x => x.id === activePathId);
    if (p && (p.points || []).length) {
      const mp = screenToGraph(lastMouse.x, lastMouse.y);
      const pts = [...p.points, { x: mp.x, y: mp.y }];
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      ctx.strokeStyle = 'rgba(59, 130, 246, 0.7)';
      ctx.lineWidth = 2.5 / scale;
      ctx.setLineDash([6 / scale, 4 / scale]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  // Rooms
  for (const r of v2.rooms) {
    const isSel = selected.kind === 'room' && selected.id === r.id;
    ctx.beginPath();
    ctx.arc(r.x || 0, r.y || 0, (ROOM_R / scale), 0, Math.PI * 2);
    ctx.fillStyle = isSel ? '#e879f9' : '#3b82f6';
    ctx.fill();
    ctx.strokeStyle = '#0a0e1a';
    ctx.lineWidth = 1.5 / scale;
    ctx.stroke();

    const label = r.label || r.id;
    ctx.font = `${Math.max(10, 11 / scale)}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const w = ctx.measureText(label).width;
    const pad = 3 / scale;
    ctx.fillStyle = 'rgba(10, 14, 26, 0.75)';
    ctx.fillRect((r.x || 0) - w / 2 - pad, (r.y || 0) + (ROOM_R / scale) + 3 / scale, w + pad * 2, 14 / scale);
    ctx.fillStyle = '#e2e8f0';
    ctx.fillText(label, r.x || 0, (r.y || 0) + (ROOM_R / scale) + 4 / scale);
  }

  // Doors
  for (const d of v2.doors) {
    const isSel = selected.kind === 'door' && selected.id === d.id;
    const s = (DOOR_SIZE / scale);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(d.x - s / 2, d.y - s / 2, s, s);
    ctx.strokeStyle = isSel ? '#e879f9' : '#22c55e';
    ctx.lineWidth = (isSel ? 2.5 : 1.5) / scale;
    ctx.strokeRect(d.x - s / 2, d.y - s / 2, s, s);
  }

  ctx.restore();

  document.getElementById('statusZoom').textContent = `Zoom: ${Math.round(scale * 100)}%`;
}

// --- Processing modal helpers (reuse existing DOM) ---
function showProcessing(show) {
  const el = document.getElementById('processingOverlay') || document.getElementById('processingModal');
  if (!el) return;
  el.classList.toggle('visible', !!show);
}

function setProgress(pct) {
  const ring = document.getElementById('progressRing');
  const percent = document.getElementById('progressPercent');
  if (!ring || !percent) return;
  const circumference = 2 * Math.PI * 42;
  const offset = circumference - (pct / 100) * circumference;
  ring.style.strokeDashoffset = offset;
  percent.textContent = pct + '%';
}

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

// Expose functions used by inline HTML handlers
window.setMode = setMode;
window.zoomIn = zoomIn;
window.zoomOut = zoomOut;
window.fitToView = fitToView;
window.saveGraph = saveGraph;
window.resetGraph = () => { showToast('Reset is removed in V2 editor. Reload the floor to restore saved state.', 'info'); };
window.cancelAddNode = cancelAddNode;
window.confirmAddNode = confirmAddNode;
