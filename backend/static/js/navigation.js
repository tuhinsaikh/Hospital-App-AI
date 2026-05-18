/**
 * Hospital Indoor Navigation — Leaflet.js Map Controller
 * Handles map rendering, pathfinding API calls, autocomplete, and path animation.
 */

// ── State ──────────────────────────────────────────
let navMap = null;
let navLayerGroup = null;
let roomLabelLayer = null;
let allLocations = [];
let currentFloor = 1;

// ── Init ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  loadLocations();
  setupAutocomplete('sourceInput', 'sourceDropdown');
  setupAutocomplete('destInput', 'destDropdown');
  parseQueryParams();
});

function initMap() {
  navMap = L.map('mapDiv', {
    crs: L.CRS.Simple,
    zoomSnap: 0.25,
    zoomDelta: 0.5,
    minZoom: -2,
    maxZoom: 4,
    zoomAnimation: true,
    attributionControl: false
  });
  navLayerGroup = L.layerGroup().addTo(navMap);
  roomLabelLayer = L.layerGroup().addTo(navMap);

  // Set initial view
  navMap.setView([400, 500], -1);

  // Load base floor plan
  loadFloorPlan();
}

async function loadFloorPlan() {
  try {
    const res = await fetch(`/navigation/path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: '_', destination: '_', floor: currentFloor })
    });
    // We expect this to fail (no valid path), but we try loadLocations for the image
  } catch (e) { /* expected */ }

  // Try to get floor info from locations endpoint
  try {
    const res = await fetch(`/navigation/locations?floor=${currentFloor}`);
    if (res.ok) {
      const data = await res.json();
      // We need the image — do a quick path request with real locations
      if (data.locations && data.locations.length >= 2) {
        const testRes = await fetch(`/navigation/path`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source: data.locations[0].label,
            destination: data.locations[1].label,
            floor: currentFloor
          })
        });
        if (testRes.ok) {
          const pathData = await testRes.json();
          renderBaseMap(pathData);
          return;
        }
      }
    }
  } catch (e) {
    console.log('Could not load floor plan:', e);
  }
  updateStatus('Upload a floor plan to get started', '📋');
}

function renderBaseMap(pathData) {
  navLayerGroup.clearLayers();
  roomLabelLayer.clearLayers();

  const h = pathData.image_height;
  const w = pathData.image_width;
  const bounds = [[0, 0], [h, w]];

  L.imageOverlay(pathData.background_image, bounds).addTo(navLayerGroup);
  navMap.fitBounds(bounds, { padding: [20, 20] });

  // Add room labels for all locations
  addRoomLabels(h);
  updateStatus('Select source and destination to navigate', '🗺️');
}

async function loadLocations() {
  try {
    const res = await fetch(`/navigation/locations?floor=${currentFloor}`);
    if (!res.ok) return;
    const data = await res.json();
    allLocations = data.locations || [];
  } catch (e) {
    console.error('Failed to load locations:', e);
  }
}

function addRoomLabels(imageHeight) {
  roomLabelLayer.clearLayers();
  allLocations.forEach(loc => {
    if (!loc.label || loc.label.trim() === '') return;
    if (loc.type === 'junction') return;
    const y = imageHeight - (loc.y || 0);
    const x = loc.x || 0;
    // Use invisible marker with permanent tooltip
    L.marker([y, x], {
      opacity: 0,
      interactive: false,
      keyboard: false
    }).bindTooltip(loc.label, {
      permanent: true,
      direction: 'center',
      className: 'room-label'
    }).addTo(roomLabelLayer);
  });
}

// ── Autocomplete ───────────────────────────────────
function setupAutocomplete(inputId, dropdownId) {
  const input = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);

  input.addEventListener('input', () => {
    const val = input.value.toLowerCase().trim();
    if (val.length < 1) {
      dropdown.classList.remove('visible');
      return;
    }
    const filtered = allLocations.filter(loc => {
      if (loc.type === 'junction') return false;
      if (!loc.label || loc.label.trim() === '') return false;
      return loc.label.toLowerCase().includes(val) || loc.id.toLowerCase().includes(val);
    });
    renderDropdown(dropdown, filtered, input);
  });

  input.addEventListener('focus', () => {
    if (input.value.trim().length > 0) {
      input.dispatchEvent(new Event('input'));
    }
  });

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest(`#${inputId}`) && !e.target.closest(`#${dropdownId}`)) {
      dropdown.classList.remove('visible');
    }
  });
}

function renderDropdown(dropdown, items, input) {
  dropdown.innerHTML = '';
  if (items.length === 0) {
    dropdown.classList.remove('visible');
    return;
  }
  items.slice(0, 8).forEach(loc => {
    const div = document.createElement('div');
    div.className = 'autocomplete-item';
    div.innerHTML = `
      <span>${loc.label}</span>
      <span class="type-badge">${loc.type || 'room'}</span>
    `;
    div.addEventListener('click', () => {
      input.value = loc.label;
      dropdown.classList.remove('visible');
    });
    dropdown.appendChild(div);
  });
  dropdown.classList.add('visible');
}

// ── Navigation ─────────────────────────────────────
async function navigate() {
  const source = document.getElementById('sourceInput').value.trim();
  const dest = document.getElementById('destInput').value.trim();

  if (!source || !dest) {
    updateStatus('Please enter both source and destination', '⚠️');
    return;
  }

  const btn = document.getElementById('navigateBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.innerHTML = '<span class="btn-spinner"></span> Calculating...';
  updateStatus('Calculating shortest path...', '⏳');

  try {
    const res = await fetch('/navigation/path', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, destination: dest, floor: currentFloor })
    });

    if (!res.ok) {
      const err = await res.json();
      updateStatus(err.detail || 'Could not find path', '❌');
      return;
    }

    const pathData = await res.json();
    renderPath(pathData);
  } catch (err) {
    console.error(err);
    updateStatus('Error connecting to server', '❌');
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
    btn.innerHTML = '🧭 Navigate';
  }
}

function renderPath(pathData) {
  navLayerGroup.clearLayers();
  roomLabelLayer.clearLayers();

  const h = pathData.image_height;
  const w = pathData.image_width;
  const bounds = [[0, 0], [h, w]];

  // Floor plan image
  L.imageOverlay(pathData.background_image, bounds).addTo(navLayerGroup);

  // Path polyline coordinates (Leaflet uses [y, x] with flipped Y)
  const coords = pathData.path.map(wp => [h - wp.y, wp.x]);

  // Main path (single stroke to avoid "multiple path" confusion)
  L.polyline(coords, {
    color: '#4285F4',
    weight: 5,
    lineCap: 'round',
    lineJoin: 'round',
    className: 'animated-path'
  }).addTo(navLayerGroup);

  // Direction arrows along the path
  addDirectionArrows(coords);

  // Waypoint dots (intermediate points)
  pathData.path.forEach((wp, i) => {
    if (i === 0 || i === pathData.path.length - 1) return;
    if (wp.type === 'junction') {
      L.circleMarker([h - wp.y, wp.x], {
        radius: 3,
        color: '#4285F4',
        fillColor: '#4285F4',
        fillOpacity: 0.6,
        weight: 0
      }).addTo(navLayerGroup);
    } else {
      L.circleMarker([h - wp.y, wp.x], {
        radius: 5,
        color: '#4285F4',
        fillColor: 'white',
        fillOpacity: 1,
        weight: 2
      }).addTo(navLayerGroup).bindPopup(wp.label);
    }
  });

  // Source marker (green pulsing)
  const srcWp = pathData.path[0];
  const srcIcon = L.divIcon({
    className: 'pulse-marker green',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
  });
  L.marker([h - srcWp.y, srcWp.x], { icon: srcIcon })
    .addTo(navLayerGroup)
    .bindPopup(`<b>Start:</b> ${srcWp.label}`);

  // Destination marker (red pulsing)
  const destWp = pathData.path[pathData.path.length - 1];
  const destIcon = L.divIcon({
    className: 'pulse-marker red',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
  });
  L.marker([h - destWp.y, destWp.x], { icon: destIcon })
    .addTo(navLayerGroup)
    .bindPopup(`<b>Destination:</b> ${destWp.label}`);

  // Fit map to path bounds with padding
  navMap.fitBounds(L.polyline(coords).getBounds(), { padding: [60, 60] });

  // Room labels
  addRoomLabels(h);

  // Update directions panel
  renderDirections(pathData);

  // Update status
  updateStatus(`${srcWp.label} → ${destWp.label}`, '📍');
}

function addDirectionArrows(coords) {
  for (let i = 0; i < coords.length - 1; i++) {
    const start = coords[i];
    const end = coords[i + 1];
    const midY = (start[0] + end[0]) / 2;
    const midX = (start[1] + end[1]) / 2;

    const angle = Math.atan2(end[0] - start[0], end[1] - start[1]) * (180 / Math.PI);

    const arrowIcon = L.divIcon({
      className: '',
      html: `<div style="
        color: #4285F4;
        font-size: 14px;
        transform: rotate(${angle - 90}deg);
        text-shadow: 0 0 4px rgba(0,0,0,0.5);
        font-weight: bold;
      ">▲</div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7]
    });
    L.marker([midY, midX], { icon: arrowIcon, interactive: false }).addTo(navLayerGroup);
  }
}

function renderDirections(pathData) {
  const panel = document.getElementById('directionsContent');
  const summary = document.getElementById('walkSummary');

  const fullPath = Array.isArray(pathData.path) ? pathData.path : [];
  const lastIdx = Math.max(0, fullPath.length - 1);
  // UX: hide internal corridor/junction hops in the step list; keep geometry unchanged for the polyline.
  const steps = fullPath.filter((wp, i) => {
    if (i === 0 || i === lastIdx) return true;
    const t = (wp.type || '').toLowerCase();
    return !['junction', 'corridor'].includes(t);
  });

  // Calculate estimated walk time (~1.2m/s walking, pixels to approx meters)
  const totalPixelDist = fullPath.reduce((sum, wp, i) => {
    if (i === 0) return 0;
    const prev = fullPath[i - 1];
    return sum + Math.hypot(wp.x - prev.x, wp.y - prev.y);
  }, 0);
  // Rough: 1 pixel ≈ 0.05m (adjustable)
  const estMeters = totalPixelDist * 0.05;
  const estMinutes = Math.max(1, Math.round(estMeters / 72)); // 72m/min walking speed

  // Show summary
  summary.classList.add('visible');
  document.getElementById('walkSteps').textContent = steps.length;
  document.getElementById('walkTime').textContent = `~${estMinutes} min`;

  // Build step list
  let html = '';
  steps.forEach((wp, i) => {
    let dotClass = '';
    if (i === 0) dotClass = 'start';
    else if (i === steps.length - 1) dotClass = 'end';

    const showConnector = i < steps.length - 1;

    html += `
      <div class="direction-step">
        <div class="step-line">
          <div class="step-dot ${dotClass}"></div>
          ${showConnector ? '<div class="step-connector"></div>' : ''}
        </div>
        <div class="step-info">
          <div class="step-name">${wp.label || wp.id}</div>
          <div class="step-type">${wp.type || 'room'}</div>
        </div>
      </div>
    `;
  });
  panel.innerHTML = html;
}

// ── Helpers ─────────────────────────────────────────
function swapLocations() {
  const srcInput = document.getElementById('sourceInput');
  const destInput = document.getElementById('destInput');
  const temp = srcInput.value;
  srcInput.value = destInput.value;
  destInput.value = temp;
}

function updateStatus(text, icon) {
  const el = document.getElementById('mapStatus');
  if (el) el.innerHTML = `${icon} ${text}`;
}

function parseQueryParams() {
  const params = new URLSearchParams(window.location.search);
  const source = params.get('source');
  const dest = params.get('dest') || params.get('destination');
  const floor = params.get('floor');

  if (floor) currentFloor = parseInt(floor);
  if (source) document.getElementById('sourceInput').value = source;
  if (dest) document.getElementById('destInput').value = dest;

  // Auto-navigate if both params present
  if (source && dest) {
    setTimeout(() => navigate(), 800);
  }
}

function setFloor(floor) {
  currentFloor = floor;
  document.querySelectorAll('.floor-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.floor) === floor);
  });
  loadLocations().then(() => loadFloorPlan());
}
