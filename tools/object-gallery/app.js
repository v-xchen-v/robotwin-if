import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader.js';
import URDFLoader from 'urdf-loader';

// ---------------------------------------------------------------- helpers ---
const $ = (sel, el = document) => el.querySelector(sel);
const dirOf = (url) => url.slice(0, url.lastIndexOf('/') + 1);

function showToast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.add('hidden'), 2600);
}

// ------------------------------------------------------------- model load ---
// Returns a Promise<THREE.Object3D>, already oriented Y-up. Each call builds a
// fresh object (so thumbnail and detail views can each own a copy).
function instanceURLs(root, entry, inst) {
  const base = `${root}/${entry.dir}/`;
  const mesh = base + inst.mesh;
  return { mesh, mtl: inst.mtl ? base + inst.mtl : null, base };
}

function loadGLB(url) {
  return new GLTFLoader().loadAsync(url).then((g) => g.scene);
}

async function loadOBJ(meshURL, mtlURL) {
  const objLoader = new OBJLoader();
  if (mtlURL) {
    const mtlLoader = new MTLLoader();
    mtlLoader.setPath(dirOf(mtlURL));
    mtlLoader.setResourcePath(dirOf(mtlURL)); // textures sit beside the .mtl
    const mats = await mtlLoader.loadAsync(mtlURL.slice(mtlURL.lastIndexOf('/') + 1));
    mats.preload();
    objLoader.setMaterials(mats);
  }
  const obj = await objLoader.loadAsync(meshURL);
  obj.traverse((c) => {
    if (c.isMesh && (!c.material || c.material.name === '')) {
      c.material = new THREE.MeshStandardMaterial({ color: 0xbfc4cc, roughness: 0.8 });
    }
  });
  return obj;
}

function loadURDF(url) {
  return new Promise((resolve, reject) => {
    const manager = new THREE.LoadingManager();
    const loader = new URDFLoader(manager);
    loader.loadMeshCb = (path, mgr, done) => {
      const ext = path.split('.').pop().toLowerCase();
      if (ext === 'obj') {
        new OBJLoader(mgr).load(path, (o) => {
          o.traverse((c) => {
            if (c.isMesh && (!c.material || c.material.name === '')) {
              c.material = new THREE.MeshStandardMaterial({ color: 0xbfc4cc, roughness: 0.8 });
            }
          });
          done(o);
        }, undefined, (e) => done(null, e));
      } else if (ext === 'glb' || ext === 'gltf') {
        new GLTFLoader(mgr).load(path, (g) => done(g.scene), undefined, (e) => done(null, e));
      } else {
        done(null, new Error('unsupported mesh ' + ext));
      }
    };
    let robot = null;
    // onComplete gives the robot before its (async) meshes finish; wait for the
    // LoadingManager to drain so the bounding box is non-empty before framing.
    manager.onLoad = () => {
      if (!robot) return;
      robot.rotation.x = -Math.PI / 2; // PartNet-mobility is Z-up -> Y-up
      resolve(robot);
    };
    loader.load(url, (r) => { robot = r; }, undefined, (e) => reject(e));
  });
}

function loadModel(root, entry, inst) {
  const { mesh, mtl } = instanceURLs(root, entry, inst);
  if (entry.type === 'glb') return loadGLB(mesh);
  if (entry.type === 'obj') return loadOBJ(mesh, mtl);
  if (entry.type === 'urdf') return loadURDF(mesh);
  return Promise.reject(new Error('unknown type ' + entry.type));
}

// Center at origin, scale so max dimension = 1, return {pivot, radius}.
function fit(obj) {
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  obj.position.sub(center);
  const pivot = new THREE.Group();
  pivot.add(obj);
  pivot.scale.setScalar(1 / maxDim);
  const radius = 0.5 * size.length() / maxDim;
  return { pivot, radius };
}

function makeCamera(radius, aspect) {
  const cam = new THREE.PerspectiveCamera(35, aspect, 0.01, 100);
  const dist = (radius / Math.tan((cam.fov / 2) * (Math.PI / 180))) * 1.5;
  cam.position.set(dist * 0.85, dist * 0.6, dist * 1.1);
  cam.lookAt(0, 0, 0);
  return cam;
}

function addLights(scene) {
  const hemi = new THREE.HemisphereLight(0xffffff, 0x30343c, 2.2);
  scene.add(hemi);
  const key = new THREE.DirectionalLight(0xffffff, 2.0);
  key.position.set(3, 5, 4);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.6);
  fill.position.set(-4, 1, -3);
  scene.add(fill);
}

// ------------------------------------------------------- shared thumb grid ---
const state = {
  root: '',
  objects: [],
  filtered: [],
  cards: new Map(), // id -> {el, thumb, entry, scene, camera, pivot, status}
};

const thumbCanvas = $('#thumb-canvas');
const thumbRenderer = new THREE.WebGLRenderer({ canvas: thumbCanvas, antialias: true, alpha: true });
thumbRenderer.setPixelRatio(Math.min(devicePixelRatio, 2));
thumbRenderer.outputColorSpace = THREE.SRGBColorSpace;

function resizeThumbCanvas() {
  const w = innerWidth, h = innerHeight;
  if (thumbCanvas.width !== w * thumbRenderer.getPixelRatio()) {
    thumbRenderer.setSize(w, h, false);
    thumbCanvas.style.width = w + 'px';
    thumbCanvas.style.height = h + 'px';
  }
}
addEventListener('resize', resizeThumbCanvas);

let lastT = performance.now();
function animateThumbs(now) {
  requestAnimationFrame(animateThumbs);
  const dt = Math.min((now - lastT) / 1000, 0.05);
  lastT = now;
  resizeThumbCanvas();
  thumbRenderer.setScissorTest(true);
  const H = innerHeight;
  for (const card of state.cards.values()) {
    if (!card.pivot) continue;
    const r = card.thumb.getBoundingClientRect();
    if (r.bottom < 0 || r.top > H || r.right < 0 || r.left > innerWidth) continue;
    if (r.width < 2 || r.height < 2) continue;
    if (card.rotating) card.pivot.rotation.y += dt * 0.6;
    const bottom = H - r.bottom;
    thumbRenderer.setViewport(r.left, bottom, r.width, r.height);
    thumbRenderer.setScissor(r.left, bottom, r.width, r.height);
    card.camera.aspect = r.width / r.height;
    card.camera.updateProjectionMatrix();
    thumbRenderer.render(card.scene, card.camera);
  }
}
requestAnimationFrame(animateThumbs);

// -------------------------------------------------------------- load queue ---
const queue = [];
let active = 0;
const MAX_CONCURRENT = 6;

function enqueue(card) {
  if (card.status !== 'idle') return;
  card.status = 'queued';
  queue.push(card);
  pump();
}
function pump() {
  while (active < MAX_CONCURRENT && queue.length) {
    const card = queue.shift();
    active++;
    card.status = 'loading';
    card.el.classList.add('loading');
    const inst = card.entry.instances[0];
    loadModel(state.root, card.entry, inst)
      .then((obj) => {
        const { pivot, radius } = fit(obj);
        card.scene = new THREE.Scene();
        addLights(card.scene);
        card.scene.add(pivot);
        card.pivot = pivot;
        card.camera = makeCamera(radius, 1);
        card.status = 'done';
        card.el.classList.remove('loading');
      })
      .catch((err) => {
        card.status = 'error';
        card.el.classList.remove('loading');
        card.el.classList.add('error');
        console.warn('load failed', card.entry.id, err);
      })
      .finally(() => {
        active--;
        pump();
      });
  }
}

const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (e.isIntersecting) {
      const card = state.cards.get(e.target.dataset.id);
      if (card) enqueue(card);
    }
  }
}, { rootMargin: '300px' });

// ------------------------------------------------------------- grid build ---
const grid = $('#grid');

function cardTemplate(entry) {
  const el = document.createElement('article');
  el.className = 'card';
  el.dataset.id = entry.id;
  el.innerHTML = `
    <div class="thumb"></div>
    <div class="label">
      <span class="name">${entry.name}</span>
      <span class="badge badge-${entry.type}">${entry.type}</span>
    </div>
    <div class="sub">${entry.id}${entry.instances.length > 1 ? ` · ${entry.instances.length} instances` : ''}</div>
    <div class="spinner"></div>`;
  return el;
}

function renderGrid() {
  grid.innerHTML = '';
  io.disconnect();
  state.cards.clear();
  for (const entry of state.filtered) {
    const el = cardTemplate(entry);
    const card = {
      el, thumb: $('.thumb', el), entry,
      scene: null, camera: null, pivot: null,
      rotating: true, status: 'idle',
    };
    state.cards.set(entry.id, card);
    el.addEventListener('click', () => openDetail(entry));
    grid.appendChild(el);
    io.observe(el);
  }
  $('#count').textContent = `${state.filtered.length} / ${state.objects.length} objects`;
}

// --------------------------------------------------------------- filtering ---
let activeGroup = 'all';
function syncURL() {
  const p = new URLSearchParams();
  const q = $('#search').value.trim();
  if (q) p.set('q', q);
  if (activeGroup !== 'all') p.set('group', activeGroup);
  const qs = p.toString();
  history.replaceState(null, '', qs ? '?' + qs : location.pathname);
}
function applyFilter() {
  const q = $('#search').value.trim().toLowerCase();
  state.filtered = state.objects.filter((o) => {
    if (activeGroup !== 'all' && o.group !== activeGroup) return false;
    if (!q) return true;
    return o.name.toLowerCase().includes(q) || o.id.toLowerCase().includes(q);
  });
  syncURL();
  renderGrid();
}

function buildFilters() {
  const groups = ['all', ...Array.from(new Set(state.objects.map((o) => o.group)))];
  const box = $('#filters');
  box.innerHTML = '';
  for (const g of groups) {
    const b = document.createElement('button');
    b.className = 'chip' + (g === 'all' ? ' active' : '');
    b.textContent = g;
    b.onclick = () => {
      activeGroup = g;
      box.querySelectorAll('.chip').forEach((c) => c.classList.toggle('active', c === b));
      applyFilter();
    };
    box.appendChild(b);
  }
}
$('#search').addEventListener('input', () => applyFilter());

// ------------------------------------------------------------ detail modal ---
const detail = {
  el: $('#detail'),
  renderer: null, scene: null, camera: null, controls: null,
  pivot: null, radius: 1, grid: null, raf: 0, entry: null,
};

function initDetailRenderer() {
  if (detail.renderer) return;
  const canvas = $('#detail-canvas');
  detail.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  detail.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  detail.renderer.outputColorSpace = THREE.SRGBColorSpace;
  detail.renderer.setClearColor(0x0e1014, 1);
  detail.controls = new OrbitControls(detail.camera || new THREE.PerspectiveCamera(), canvas);
}

function detailResize() {
  const stage = $('.detail-stage');
  const w = stage.clientWidth, h = stage.clientHeight;
  detail.renderer.setSize(w, h, false);
  if (detail.camera) {
    detail.camera.aspect = w / h;
    detail.camera.updateProjectionMatrix();
  }
}

function detailLoop() {
  detail.raf = requestAnimationFrame(detailLoop);
  if ($('#opt-rotate').checked && detail.pivot) detail.pivot.rotation.y += 0.006;
  detail.controls.update();
  detail.renderer.render(detail.scene, detail.camera);
}

async function loadInstanceIntoDetail(entry, instIdx) {
  $('#detail-loading').classList.remove('hidden');
  const inst = entry.instances[instIdx];
  try {
    const obj = await loadModel(state.root, entry, inst);
    const { pivot, radius } = fit(obj);
    // rebuild scene
    detail.scene = new THREE.Scene();
    addLights(detail.scene);
    detail.grid = new THREE.GridHelper(4, 16, 0x3a3f4b, 0x23262e);
    detail.grid.position.y = -radius;
    detail.grid.visible = $('#opt-grid').checked;
    detail.scene.add(detail.grid);
    detail.scene.add(pivot);
    detail.pivot = pivot;
    detail.radius = radius;
    applyWireframe($('#opt-wire').checked);

    const stage = $('.detail-stage');
    detail.camera = makeCamera(radius, stage.clientWidth / stage.clientHeight);
    detail.controls.object = detail.camera;
    detail.controls.target.set(0, 0, 0);
    detail.controls.update();
    detailResize();
  } catch (err) {
    showToast('Failed to load ' + entry.id);
    console.warn(err);
  } finally {
    $('#detail-loading').classList.add('hidden');
  }
}

function applyWireframe(on) {
  if (!detail.pivot) return;
  detail.pivot.traverse((c) => {
    if (c.isMesh && c.material) {
      (Array.isArray(c.material) ? c.material : [c.material]).forEach((m) => (m.wireframe = on));
    }
  });
}

function openDetail(entry) {
  detail.entry = entry;
  detail.el.classList.remove('hidden');
  detail.el.setAttribute('aria-hidden', 'false');
  $('#detail-title').textContent = entry.name;
  $('#detail-meta').innerHTML =
    `<span class="badge badge-${entry.type}">${entry.type}</span>` +
    `<span>${entry.id}</span><span>${entry.instances.length} instance(s)</span>`;
  // instance buttons
  const list = $('#instance-list');
  list.innerHTML = '';
  entry.instances.forEach((inst, i) => {
    const b = document.createElement('button');
    b.className = 'inst-btn' + (i === 0 ? ' active' : '');
    b.textContent = i;
    b.title = inst.mesh;
    b.onclick = () => {
      list.querySelectorAll('.inst-btn').forEach((x) => x.classList.toggle('active', x === b));
      loadInstanceIntoDetail(entry, i);
    };
    list.appendChild(b);
  });
  initDetailRenderer();
  if (!detail.raf) detailLoop();
  loadInstanceIntoDetail(entry, 0);
}

function closeDetail() {
  detail.el.classList.add('hidden');
  detail.el.setAttribute('aria-hidden', 'true');
  cancelAnimationFrame(detail.raf);
  detail.raf = 0;
}

$('#detail-close').onclick = closeDetail;
detail.el.addEventListener('click', (e) => { if (e.target === detail.el) closeDetail(); });
addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDetail(); });
$('#opt-wire').onchange = (e) => applyWireframe(e.target.checked);
$('#opt-grid').onchange = (e) => { if (detail.grid) detail.grid.visible = e.target.checked; };
addEventListener('resize', () => { if (!detail.el.classList.contains('hidden')) detailResize(); });

// -------------------------------------------------------------------- boot ---
async function boot() {
  try {
    const res = await fetch('manifest.json', { cache: 'no-cache' });
    const manifest = await res.json();
    state.root = manifest.objectsRoot;
    state.objects = manifest.objects;
    state.filtered = manifest.objects;
    buildFilters();
    // deep-link support: ?q=<text>&group=<group>
    const params = new URLSearchParams(location.search);
    if (params.get('q')) $('#search').value = params.get('q');
    if (params.get('group')) {
      activeGroup = params.get('group');
      $('#filters').querySelectorAll('.chip').forEach((c) =>
        c.classList.toggle('active', c.textContent === activeGroup));
    }
    applyFilter();
  } catch (err) {
    showToast('Could not load manifest.json — run gen_manifest.py first');
    console.error(err);
  }
}
boot();
