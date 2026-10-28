import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

function colorForPart(name) {
  if (PART_COLORS[name]) {
    return PART_COLORS[name];
  }
  if (name.startsWith("Strut")) {
    return PART_COLORS.strut;
  }
  if (name.startsWith("Leg")) {
    return PART_COLORS.leg;
  }
  if (name.startsWith("Caster")) {
    return PART_COLORS.caster;
  }
  if (name.startsWith("Side") || name === "Front" || name === "Back" || name === "Base") {
    return PART_COLORS.cart;
  }
  return PART_COLORS.fallback;
}

function applyPartColors(root) {
  root.traverse((node) => {
    if (!node.isMesh) {
      return;
    }
    const hex = colorForPart(node.name || (node.parent && node.parent.name) || "");
    node.material = new THREE.MeshStandardMaterial({
      color: hex,
      metalness: 0.05,
      roughness: 0.72,
    });
    node.castShadow = false;
    node.receiveShadow = false;
  });
}

function fitCameraToObject(camera, controls, object) {
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = (camera.fov * Math.PI) / 180;
  const distance = (maxDim / 2) / Math.tan(fov / 2);
  const offset = distance * CAMERA.fitPadding;

  camera.near = Math.max(maxDim / 200, 0.01);
  camera.far = maxDim * 40;
  camera.updateProjectionMatrix();

  camera.position.set(
    center.x + offset * CAMERA.iso.x,
    center.y + offset * CAMERA.iso.y,
    center.z + offset * CAMERA.iso.z
  );
  controls.target.copy(center);
  controls.minDistance = maxDim * 0.35;
  controls.maxDistance = maxDim * 8;
  controls.update();
}

function createScene(container) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(SCENE.background);

  const camera = new THREE.PerspectiveCamera(
    CAMERA.fov,
    container.clientWidth / Math.max(container.clientHeight, 1),
    0.01,
    100
  );

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);
  renderer.domElement.setAttribute("tabindex", "0");
  renderer.domElement.setAttribute("aria-label", "Folding CNC table 3D model");

  const hemi = new THREE.HemisphereLight(SCENE.hemiSky, SCENE.hemiGround, SCENE.hemiIntensity);
  scene.add(hemi);

  const key = new THREE.DirectionalLight(0xffffff, SCENE.keyIntensity);
  key.position.set(4, 8, 6);
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xfff2d8, SCENE.fillIntensity);
  fill.position.set(-6, 3, -4);
  scene.add(fill);

  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(8, 48),
    new THREE.MeshStandardMaterial({
      color: SCENE.ground,
      roughness: 1,
      metalness: 0,
    })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.01;
  scene.add(ground);

  const grid = new THREE.GridHelper(6, 12, 0x6a6a6a, 0x4a4a4a);
  grid.position.y = 0;
  scene.add(grid);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = true;
  controls.enableZoom = true;
  controls.screenSpacePanning = true;
  controls.zoomToCursor = true;
  controls.rotateSpeed = 0.85;
  controls.panSpeed = 0.7;
  controls.zoomSpeed = 1.0;

  return { scene, camera, renderer, controls, ground, grid };
}

function mountViewer() {
  const container = document.getElementById(VIEWER.containerId);
  const status = document.getElementById(VIEWER.statusId);
  const resetBtn = document.getElementById(VIEWER.resetId);
  if (!container) {
    return;
  }

  const { scene, camera, renderer, controls, ground, grid } = createScene(container);
  const loader = new GLTFLoader();
  let root = null;

  function setStatus(text) {
    if (status) {
      status.textContent = text;
    }
  }

  function onResize() {
    const width = container.clientWidth;
    const height = Math.max(container.clientHeight, 1);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  }

  window.addEventListener("resize", onResize);

  loader.load(
    VIEWER.modelUrl,
    (gltf) => {
      root = gltf.scene;
      applyPartColors(root);
      scene.add(root);

      const box = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);
      ground.position.set(center.x, box.min.y - 0.002, center.z);
      ground.scale.setScalar(Math.max(maxDim * 1.6, 1));
      grid.position.set(center.x, box.min.y, center.z);
      grid.scale.setScalar(Math.max(maxDim / 3, 1));

      fitCameraToObject(camera, controls, root);
      setStatus("Drag to orbit · scroll to zoom · right-drag or two-finger drag to pan");
    },
    (event) => {
      if (!event.total) {
        return;
      }
      const pct = Math.round((event.loaded / event.total) * 100);
      setStatus("Loading model… " + pct + "%");
    },
    () => {
      setStatus("Could not load the 3D model. Try refreshing the page.");
    }
  );

  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      if (root) {
        fitCameraToObject(camera, controls, root);
      }
    });
  }

  function tick() {
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  tick();
}

// ---------------------------------------------------------------------------
// USER-EDITABLE SETTINGS
// ---------------------------------------------------------------------------
const VIEWER = {
  containerId: "folding-table-viewer",
  statusId: "folding-table-status",
  resetId: "folding-table-reset",
  modelUrl: "/models/folding-table.glb",
};

const CAMERA = {
  fov: 42,
  fitPadding: 1.45,
  iso: { x: 0.85, y: 0.65, z: 1.05 },
};

const SCENE = {
  background: 0x2a2a2a,
  ground: 0x3d3d3d,
  hemiSky: 0xf0f0ff,
  hemiGround: 0x3a3228,
  hemiIntensity: 1.05,
  keyIntensity: 1.35,
  fillIntensity: 0.45,
};

const PART_COLORS = {
  TableTop: 0xc7a36b,
  cart: 0x1f1c1a,
  strut: 0x2e2924,
  leg: 0xb28a52,
  caster: 0x38332e,
  fallback: 0x888888,
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mountViewer);
} else {
  mountViewer();
}
