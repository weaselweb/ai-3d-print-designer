// Colour-aware multi-body three.js viewer, shared by designs and signs.
// Loads each body STL in its own colour so multicolour parts preview correctly.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

let renderer, scene, camera, controls, group, grid;

function init(container) {
  const w = container.clientWidth || 640, h = container.clientHeight || 460;
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x15181d);
  camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 5000);
  camera.position.set(0, -120, 90);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(w, h);
  container.appendChild(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  scene.add(new THREE.AmbientLight(0xffffff, 0.8));
  const key = new THREE.DirectionalLight(0xffffff, 1.0);
  key.position.set(0.6, -1, 1); scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.35);
  fill.position.set(-0.6, 0.5, -0.5); scene.add(fill);
  grid = new THREE.GridHelper(300, 30, 0x2a2f38, 0x22262d);
  grid.rotation.x = Math.PI / 2;          // grid in the XY (print bed) plane
  scene.add(grid);
  window.addEventListener("resize", () => {
    const nw = container.clientWidth, nh = container.clientHeight;
    camera.aspect = nw / nh; camera.updateProjectionMatrix(); renderer.setSize(nw, nh);
  });
  (function animate() {
    requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera);
  })();
}

// bodies: [{stl_url, color}, ...]
window.reloadBodies = function (bodies) {
  if (!scene || !bodies || !bodies.length) return;
  if (group) scene.remove(group);
  group = new THREE.Group();
  scene.add(group);
  const loader = new STLLoader();
  let remaining = bodies.length;
  bodies.forEach(function (b) {
    loader.load(b.stl_url + (b.stl_url.indexOf("?") < 0 ? "?t=" + Date.now() : ""), function (geo) {
      geo.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({ color: b.color || "#4c9aff", metalness: 0.05, roughness: 0.7 });
      group.add(new THREE.Mesh(geo, mat));
      if (--remaining === 0) frame();
    });
  });
};

function frame() {
  const box = new THREE.Box3().setFromObject(group);
  const size = new THREE.Vector3(); box.getSize(size);
  const center = new THREE.Vector3(); box.getCenter(center);
  group.position.sub(center);
  group.position.z += size.z / 2;   // sit on the bed
  const radius = Math.max(size.x, size.y, size.z) || 50;
  camera.position.set(radius * 0.4, -radius * 1.6, radius * 1.1);
  controls.target.set(0, 0, size.z / 2);
  controls.update();
}

const container = document.getElementById("body-viewer");
if (container) {
  init(container);
  if (window.__pendingBodies) window.reloadBodies(window.__pendingBodies);
}
