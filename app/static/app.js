// three.js STL preview. One persistent scene per page; reloadModel swaps geometry.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

let renderer, scene, camera, controls, mesh, grid;

function initViewer(container) {
  const w = container.clientWidth || 640;
  const h = container.clientHeight || 460;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x15181d);

  camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 5000);
  camera.position.set(80, 80, 120);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(w, h);
  container.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(1, 1.5, 1);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.4);
  fill.position.set(-1, -0.5, -1);
  scene.add(fill);

  grid = new THREE.GridHelper(300, 30, 0x2a2f38, 0x22262d);
  scene.add(grid);

  window.addEventListener("resize", () => {
    const nw = container.clientWidth, nh = container.clientHeight;
    camera.aspect = nw / nh;
    camera.updateProjectionMatrix();
    renderer.setSize(nw, nh);
  });

  (function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  })();
}

window.reloadModel = function (url) {
  if (!scene) return;
  const loader = new STLLoader();
  loader.load(url, (geometry) => {
    if (mesh) {
      scene.remove(mesh);
      mesh.geometry.dispose();
      mesh.material.dispose();
    }
    geometry.computeVertexNormals();
    geometry.center();
    const material = new THREE.MeshStandardMaterial({ color: 0x4c9aff, metalness: 0.1, roughness: 0.6 });
    mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    // Fit camera to the bounding sphere and drop the model onto the grid.
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    const size = new THREE.Vector3();
    box.getSize(size);
    mesh.position.y = size.y / 2;
    grid.position.y = 0;
    const radius = Math.max(size.x, size.y, size.z);
    camera.position.set(radius * 1.4, radius * 1.2, radius * 1.8);
    controls.target.set(0, size.y / 2, 0);
    controls.update();
  });
};

const container = document.getElementById("viewer");
if (container) {
  initViewer(container);
  const initial = window.__pendingStl || container.dataset.stl;
  if (initial) window.reloadModel(initial);
}
