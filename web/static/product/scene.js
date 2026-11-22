// AirLens Node: adegan Three.js. Tidak tahu apa pun tentang gulir; scroll.js memberi keadaan yang dituju
// lewat apply(state) dan scene ini hanya menggambar.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { CONCEPT_FILE, BETA_FILE, SHELL, MODULES, BETA_CASE, EXPLODE, SLEEVE_FADE, SHUTTER_CLOSE_X, SPOTLIGHTS, BENCH,
  LABELS, WIRES, WIRE_COLOURS, VOLUMES, AIRFLOW } from "./parts.js";

const DEG = Math.PI / 180;
// Tata letak berdampingan: desktop, dan HP/tablet miring >= 600 px. Sama persis dengan media query di product.css.
const WIDE = "(min-width: 900px), (orientation: landscape) and (min-width: 600px)";
const UP = new THREE.Vector3(0, 1, 0);

export function createScene(canvas, { weak, labelLayer, onProgress }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: !weak, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.95;
  renderer.shadowMap.enabled = !weak;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  let maxDpr = weak ? 1.5 : 2;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 5, 6000);

  // Environment map ruangan: memberi kilap pada logam (pendingin Pi, pelindung modul).
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), 0.04).texture;
  pmrem.dispose();

  // Pencahayaan studio: langit lembut, key dari depan-kiri atas, rim tipis dari belakang.
  scene.add(new THREE.HemisphereLight(0xd6e9f5, 0x0a1622, 0.35));
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(-300, 520, 420);
  key.castShadow = !weak;
  key.shadow.mapSize.set(1024, 1024);
  Object.assign(key.shadow.camera, { left: -260, right: 260, top: 260, bottom: -260, near: 100, far: 1600 });
  key.shadow.bias = -0.0005;
  key.shadow.radius = 6;
  key.target.position.set(0, 100, 0);
  scene.add(key, key.target);
  const rim = new THREE.DirectionalLight(0x9fd3ef, 1.2);
  rim.position.set(380, 260, -420);
  scene.add(rim);

  // Lantai: hanya menerima bayangan, tanpa grid.
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(1600, 1600), new THREE.ShadowMaterial({ opacity: 0.32 }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -24;
  floor.receiveShadow = true;
  scene.add(floor);

  const concept = new THREE.Group(), beta = new THREE.Group();
  beta.visible = false;
  scene.add(concept, beta);

  // ---------------------------------------------------------------- kelompok node (casing / modul), titik putar di pusatnya
  // groups[key] = { obj (Group di pusat kotak batasnya), rest (Vector3), mats (Material[]), opacity, meshes }
  const groups = {};
  function buildGroups(gltfScene, parent, keyOf) {
    const byKey = {};
    for (const node of [...gltfScene.children]) {
      const k = keyOf(node.name || "");
      if (k) (byKey[k] ||= []).push(node);
    }
    for (const [k, nodes] of Object.entries(byKey)) {
      const box = new THREE.Box3();
      for (const n of nodes) box.expandByObject(n);
      const centre = box.getCenter(new THREE.Vector3());
      const obj = new THREE.Group();
      obj.position.copy(centre);
      parent.add(obj);
      obj.updateMatrixWorld(true);
      const clones = new Map(), meshes = [];
      for (const n of nodes) {
        obj.attach(n);
        n.traverse((o) => {
          if (!o.isMesh) return;
          if (!clones.has(o.material)) {
            const m = o.material.clone();
            // assemble.py (trimesh) menulis warna sRGB ke baseColorFactor yang menurut glTF linear.
            m.color.convertSRGBToLinear();
            m.emissive?.convertSRGBToLinear();
            m.transparent = true;
            m.envMapIntensity = m.metalness > 0.5 ? 1.1 : 0.55;
            clones.set(o.material, m);
          }
          o.material = clones.get(o.material);
          o.castShadow = !weak; o.receiveShadow = !weak;
          meshes.push(o);
        });
      }
      groups[k] = { obj, rest: centre.clone(), box, mats: [...clones.values()], meshes, opacity: 1 };
    }
  }

  // ---------------------------------------------------------------- pemuatan (dua GLB + placements.json) dengan progres
  async function fetchAll(urls) {
    const totals = urls.map(() => 0), got = urls.map(() => 0);
    const report = () => onProgress?.(got.reduce((x, y) => x + y, 0), totals.reduce((x, y) => x + y, 0));
    return Promise.all(urls.map(async (url, i) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
      totals[i] = Number(res.headers.get("Content-Length")) || 0;
      if (!res.body || !totals[i]) { const buf = await res.arrayBuffer(); got[i] = totals[i] = buf.byteLength; report(); return buf; }
      const reader = res.body.getReader(), chunks = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value); got[i] += value.byteLength; report();
      }
      const out = new Uint8Array(got[i]);
      let off = 0;
      for (const ch of chunks) { out.set(ch, off); off += ch.byteLength; }
      return out.buffer;
    }));
  }

  let loaded = false, placements = {};
  async function loadModels(base) {
    const [conceptBuf, betaBuf, placeBuf] = await fetchAll([base + CONCEPT_FILE, base + BETA_FILE, base + "placements.json"]);
    placements = JSON.parse(new TextDecoder().decode(placeBuf));
    const loader = new GLTFLoader();
    const parse = (buf) => new Promise((resolve, reject) => loader.parse(buf, "", resolve, reject));
    const [c, b] = await Promise.all([parse(conceptBuf), parse(betaBuf)]);
    buildGroups(c.scene, concept, (name) => SHELL.includes(name) ? name : (MODULES.find((m) => name.startsWith(`comp_${m}__`)) || null));
    buildGroups(b.scene, beta, (name) => BETA_CASE.includes(name) ? name : "beta_inner");
    // titik label Beta: atas-tengah kotak batas node yang bernama sama
    beta.updateMatrixWorld(true);
    for (const L of labels.filter((l) => l.beta)) {
      const box = new THREE.Box3();
      beta.traverse((o) => { if (o.isMesh && o.name.startsWith(L.groupKey)) box.expandByObject(o); });
      if (!box.isEmpty()) L.local = new THREE.Vector3((box.min.x + box.max.x) / 2, box.max.y, (box.min.z + box.max.z) / 2).sub(groups.beta_inner.rest);
    }
    for (const w of wires) w.local = w.path.map(([g, x, y, z]) => new THREE.Vector3(x, y, z).sub(groups[g].rest));
    for (const L of labels.filter((l) => !l.beta)) L.local = L.point.clone().sub(groups[L.groupKey].rest);
    for (const w of wires) w.tube.mesh.visible = true;
    loaded = true;
  }

  // ---------------------------------------------------------------- kabel (tabung, diperbarui di tempat)
  class Tube {
    constructor(colour, segs = 64, radial = 6, radius = 0.6) {
      this.segs = segs; this.radial = radial; this.radius = radius;
      const n = (segs + 1) * radial;
      this.pos = new Float32Array(n * 3); this.nor = new Float32Array(n * 3);
      const idx = [];
      for (let i = 0; i < segs; i++) for (let j = 0; j < radial; j++) {
        const a = i * radial + j, b2 = i * radial + (j + 1) % radial, c2 = a + radial, d = b2 + radial;
        idx.push(a, c2, b2, b2, c2, d);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(this.pos, 3));
      g.setAttribute("normal", new THREE.BufferAttribute(this.nor, 3));
      g.setIndex(idx);
      this.material = new THREE.MeshStandardMaterial({ color: colour, roughness: 0.38, metalness: 0, transparent: true, envMapIntensity: 1.2 });
      this.mesh = new THREE.Mesh(g, this.material);
      this.mesh.frustumCulled = false;
      this.mesh.visible = false;
      this.curve = new THREE.CatmullRomCurve3([], false, "centripetal");
      this.p = new THREE.Vector3(); this.t = new THREE.Vector3(); this.n = new THREE.Vector3(); this.b = new THREE.Vector3();
    }
    update(points) {
      this.curve.points = points;
      const { p, t, n, b } = this;
      for (let i = 0; i <= this.segs; i++) {
        const u = i / this.segs;
        this.curve.getPoint(u, p);
        this.curve.getTangent(u, t).normalize();
        if (i === 0) { n.set(0, 1, 0); if (Math.abs(t.dot(n)) > 0.9) n.set(1, 0, 0); }
        n.addScaledVector(t, -n.dot(t)).normalize();          // transport sejajar: normal tetap tegak lurus tangen
        b.crossVectors(t, n);
        for (let j = 0; j < this.radial; j++) {
          const a = (j / this.radial) * Math.PI * 2, cs = Math.cos(a), sn = Math.sin(a);
          const k = (i * this.radial + j) * 3;
          const nx = n.x * cs + b.x * sn, ny = n.y * cs + b.y * sn, nz = n.z * cs + b.z * sn;
          this.nor[k] = nx; this.nor[k + 1] = ny; this.nor[k + 2] = nz;
          this.pos[k] = p.x + nx * this.radius; this.pos[k + 1] = p.y + ny * this.radius; this.pos[k + 2] = p.z + nz * this.radius;
        }
      }
      const g = this.mesh.geometry;
      g.attributes.position.needsUpdate = true; g.attributes.normal.needsUpdate = true;
    }
  }
  const wires = WIRES.map((w) => {
    const tube = new Tube(WIRE_COLOURS[w.colour]);
    concept.add(tube.mesh);
    return { ...w, tube, local: null };
  });
  let wireSignature = "";
  function updateWires(s) {
    const sig = Object.values(groups).map((g) => g.obj.matrixWorld.elements.map((v) => v.toFixed(2)).join()).join("|");
    if (sig === wireSignature) return;
    wireSignature = sig;
    for (const w of wires) {
      const pts = w.path.map(([g], i) => groups[g].obj.localToWorld(w.local[i].clone()));
      const n = pts.length, start = pts[0].clone(), end = pts[n - 1].clone();
      const pf = s.spot[w.path[0][0]] || 0, pt = s.spot[w.path[n - 1][0]] || 0;
      // Modul yang ditarik keluar: titik rute di dekat ujungnya menyatu ke titik berikutnya, agar kabel tidak
      // membentuk lengkungan panjang. Bila kedua ujung ditarik (ISB -> ADS1115), kabel jadi lurus di antara keduanya.
      if (pf > 0 && pt > 0) for (let i = 1; i < n - 1; i++) pts[i].lerp(start.clone().lerp(end, i / (n - 1)), Math.min(pf, pt));
      if (pf > 0 && n > 3) pts[1].lerp(pts[2], pf);
      if (pt > 0 && n > 5) { const a = pts[n - 4]; for (let i = n - 3; i < n - 1; i++) pts[i].lerp(a, pt); }
      w.tube.update(pts);
    }
  }

  // ---------------------------------------------------------------- volume penanda (garis tepi + isian tipis)
  const volumes = {};
  for (const [name, v] of Object.entries(VOLUMES)) {
    const size = new THREE.Vector3(...v.max).sub(new THREE.Vector3(...v.min));
    const centre = new THREE.Vector3(...v.min).add(new THREE.Vector3(...v.max)).multiplyScalar(0.5);
    const geo = new THREE.BoxGeometry(size.x, size.y, size.z);
    const fill = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: v.colour, transparent: true, opacity: 0, depthWrite: false }));
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: v.colour, transparent: true, opacity: 0, depthTest: false }));
    edges.renderOrder = 10;
    const g = new THREE.Group();
    g.add(fill, edges);
    g.position.copy(centre);
    g.visible = false;
    concept.add(g);
    volumes[name] = { g, fill, edges, fillMax: v.fill ?? 0.05 };
  }

  // ---------------------------------------------------------------- dua aliran udara (partikel di sepanjang kurva)
  const dotCanvas = document.createElement("canvas");
  dotCanvas.width = dotCanvas.height = 32;
  const dctx = dotCanvas.getContext("2d");
  dctx.beginPath(); dctx.arc(16, 16, 13, 0, Math.PI * 2); dctx.fillStyle = "#fff"; dctx.fill();
  const dotTex = new THREE.CanvasTexture(dotCanvas);
  const flows = {};
  for (const [name, f] of Object.entries(AIRFLOW)) {
    const curves = f.paths.map((p) => new THREE.CatmullRomCurve3(p.map((v) => new THREE.Vector3(...v))));
    const n = weak ? 60 : 110;
    const pos = new Float32Array(n * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const mat = new THREE.PointsMaterial({ color: f.colour, size: 5.5, map: dotTex, transparent: true, opacity: 0, depthWrite: false, alphaTest: 0.05 });
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    pts.visible = false;
    concept.add(pts);
    const seeds = Array.from({ length: n }, (_, i) => ({ c: i % curves.length, ph: (i * 0.618) % 1, j: [Math.sin(i * 12.9) * 4, Math.sin(i * 78.2) * 4, Math.sin(i * 37.7) * 4] }));
    flows[name] = { curves, pos, geo, mat, pts, seeds };
  }
  const tmpV = new THREE.Vector3();
  function updateFlow(f, t) {
    f.seeds.forEach((s, i) => {
      f.curves[s.c].getPointAt((s.ph + t * 0.09) % 1, tmpV);
      f.pos[i * 3] = tmpV.x + s.j[0]; f.pos[i * 3 + 1] = tmpV.y + s.j[1]; f.pos[i * 3 + 2] = tmpV.z + s.j[2];
    });
    f.geo.attributes.position.needsUpdate = true;
  }

  // ---------------------------------------------------------------- label penunjuk (lapisan HTML di atas kanvas)
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("class", "callout-lines");
  labelLayer?.append(svg);
  const labels = [];
  for (const [set, list] of Object.entries(LABELS)) {
    for (const [groupKey, text, point, dx, dy] of list) {
      const el = document.createElement("span");
      el.className = "callout";
      el.textContent = text;
      el.hidden = true;
      labelLayer?.append(el);
      const line = document.createElementNS(svgNS, "line");
      const dot = document.createElementNS(svgNS, "circle");
      dot.setAttribute("r", "2.5");
      line.style.display = dot.style.display = "none";
      svg.append(line, dot);
      labels.push({ set, groupKey, beta: set === "beta", point: point && new THREE.Vector3(...point), local: null, el, line, dot, dx, dy });
    }
  }
  const proj = new THREE.Vector3();
  function hideLabel(L) { L.el.style.opacity = "0"; L.line.style.opacity = L.dot.style.opacity = "0"; }
  function updateLabels(s) {
    const scale = layout === "narrow" ? 0.62 : 1;
    for (const L of labels) {
      const w = loaded && L.local ? (s.labels[L.set] || 0) : 0;
      const show = w > 0.02;
      if (L.el.hidden === show) { L.el.hidden = !show; L.line.style.display = L.dot.style.display = show ? "" : "none"; }
      if (!show) continue;
      const g = L.beta ? groups.beta_inner : groups[L.groupKey];
      proj.copy(L.local).applyMatrix4(g.obj.matrixWorld).project(camera);
      if (proj.z > 1) { hideLabel(L); continue; }
      const sx = (proj.x + 1) / 2 * width, sy = (1 - proj.y) / 2 * height;
      if (!L.size) L.size = [L.el.offsetWidth, L.el.offsetHeight];
      const [lw, lh] = L.size;
      const x = sx + L.dx * scale, y = sy + L.dy * scale;
      let left = L.dx < 0 ? x - lw : L.dx === 0 ? x - lw / 2 : x;
      left = Math.min(Math.max(8, (s.textRight || 0) + 12, left), width - lw - 8);
      const maxTop = Math.min(height - lh - 8, (s.textTop ?? Infinity) - lh - 8);
      // Ponsel: label yang tidak muat di atas panel teks disembunyikan, bukan ditumpuk di strip sempit.
      if (y - lh / 2 > maxTop) { hideLabel(L); continue; }
      const top = Math.max(8, Math.min(y - lh / 2, maxTop));
      L.el.style.transform = `translate(${left.toFixed(1)}px, ${top.toFixed(1)}px)`;
      L.el.style.opacity = w.toFixed(3);
      const ex = L.dx < 0 ? left + lw : L.dx === 0 ? left + lw / 2 : left;
      const ey = L.dx === 0 ? top : top + lh / 2;
      L.line.setAttribute("x1", sx.toFixed(1)); L.line.setAttribute("y1", sy.toFixed(1));
      L.line.setAttribute("x2", ex.toFixed(1)); L.line.setAttribute("y2", ey.toFixed(1));
      L.dot.setAttribute("cx", sx.toFixed(1)); L.dot.setAttribute("cy", sy.toFixed(1));
      L.line.style.opacity = L.dot.style.opacity = w.toFixed(3);
    }
  }

  // ---------------------------------------------------------------- ukuran & kamera
  let width = 1, height = 1, layout = "wide";
  function resize() {
    width = canvas.clientWidth || 1; height = canvas.clientHeight || 1;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, maxDpr));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    layout = window.matchMedia(WIDE).matches ? "wide" : "narrow";
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    for (const L of labels) L.size = null;
    // Lebar: model di kanan (teks di kiri). Ponsel tegak: model di bagian atas (teks di bawah).
    if (layout === "wide") camera.setViewOffset(width, height, -width * 0.2, 0, width, height);
    else camera.setViewOffset(width, height, 0, height * 0.18, width, height);
    camera.updateProjectionMatrix();
  }
  function lowerQuality() {
    if (maxDpr <= 1) return false;
    maxDpr = Math.max(1, maxDpr - 0.5);
    resize();
    return true;
  }

  // Titik sorot tiap sorotan: di depan menara, ke arah kamera sorotan itu.
  const benchOf = SPOTLIGHTS.map((sp) => new THREE.Vector3(Math.sin(sp.az * DEG) * BENCH.out, BENCH.y, Math.cos(sp.az * DEG) * BENCH.out));
  const spotOf = {};
  SPOTLIGHTS.forEach((sp, i) => sp.keys.forEach((k) => { spotOf[k] = i; }));
  function spotTarget(i) {
    const sp = SPOTLIGHTS[i], b = benchOf[i].clone();
    const offs = sp.keys.map((k) => new THREE.Vector3(...(sp.offset?.[k] || [0, 0, 0])));
    const mean = offs.reduce((a, v) => a.add(v), new THREE.Vector3()).multiplyScalar(1 / offs.length);
    return b.add(mean).toArray();
  }

  // ---------------------------------------------------------------- terapkan keadaan
  // state = { az, el, dist, target, explode:{key:0..1, modules}, shutter, fade:{key}, spot:{module:0..1}, labels:{set},
  //           volumes:{name}, flows:{name}, wires, swap, betaOpen, time, textRight, textTop }
  const tmpP = new THREE.Vector3();
  function setOpacity(g, o) {
    g.obj.visible = o > 0.01;
    if (Math.abs(o - g.opacity) < 0.002) return;
    g.opacity = o;
    for (const m of g.mats) { m.opacity = o; m.depthWrite = o > 0.98; }
    for (const mesh of g.meshes) mesh.castShadow = !weak && o > 0.5;
  }
  function apply(s) {
    const swap = s.swap || 0;
    concept.visible = swap < 0.995;
    beta.visible = swap > 0.005;

    if (loaded) {
      // posisi kelompok konsep
      for (const k of [...SHELL, ...MODULES]) {
        const g = groups[k];
        if (!g) continue;
        const p = tmpP.copy(g.rest);
        const ex = EXPLODE[k];
        if (ex) p.y += ex.dy * (s.explode[k] || 0);
        if (k === "enclosure_shutter") p.x += SHUTTER_CLOSE_X * (s.shutter || 0);
        if (MODULES.includes(k)) {
          const dir = placements[k]?.pull_dir;
          if (dir) p.add(tmpV.set(...dir).normalize().multiplyScalar(EXPLODE.modules.pull * (s.explode.modules || 0)));
          const sp = s.spot[k] || 0;
          if (sp > 0.001) {
            const i = spotOf[k];
            const goal = benchOf[i].clone().add(new THREE.Vector3(...(SPOTLIGHTS[i].offset?.[k] || [0, 0, 0])));
            const e = sp * sp * (3 - 2 * sp);
            p.lerp(goal, e).addScaledVector(UP, Math.sin(e * Math.PI) * 20);
            g.obj.rotation.y = Math.sin(s.time * 0.6) * 20 * DEG * e;
          } else g.obj.rotation.y = 0;
        }
        g.obj.position.copy(p);
        let o = s.fade[k] ?? 1;
        if (k === "enclosure_sleeve") o = Math.min(o, 1 - (1 - SLEEVE_FADE) * (s.explode.enclosure_sleeve || 0) * (s.sleeveHide ?? 1));
        setOpacity(g, o * (1 - swap));
      }
      // Beta: tutup terangkat dan memudar, nampan memudar (Unwrapped)
      const open = s.betaOpen || 0;
      if (groups.beta_case_lid) {
        groups.beta_case_lid.obj.position.copy(groups.beta_case_lid.rest).y += 55 * open;
        setOpacity(groups.beta_case_lid, swap * (1 - open));
        setOpacity(groups.beta_case_base, swap * (1 - open));
        setOpacity(groups.beta_inner, swap);
      }
      scene.updateMatrixWorld();
      updateWires(s);
      for (const w of wires) {
        // kabel yang tidak menyentuh modul yang disorot meredup bersama modulnya
        const ends = Math.max(s.fade[w.path[0][0]] ?? 1, s.fade[w.path[w.path.length - 1][0]] ?? 1);
        const o = (s.wires ?? 1) * (1 - swap) * Math.max(0.25, Math.min(1, ends));
        w.tube.mesh.visible = o > 0.01;
        w.tube.material.opacity = o;
        w.tube.material.depthWrite = o > 0.98;
      }
    }
    for (const [name, v] of Object.entries(volumes)) {
      const o = (s.volumes[name] || 0) * (1 - swap);
      v.g.visible = o > 0.01;
      v.fill.material.opacity = v.fillMax * o;
      v.edges.material.opacity = 0.75 * o;
    }
    for (const [name, f] of Object.entries(flows)) {
      const o = (s.flows[name] || 0) * (1 - swap);
      f.pts.visible = o > 0.01;
      f.mat.opacity = 0.9 * o;
      if (f.pts.visible) updateFlow(f, s.time);
    }

    const t = s.target, cel = Math.cos(s.el * DEG);
    camera.position.set(t[0] + s.dist * cel * Math.sin(s.az * DEG), t[1] + s.dist * Math.sin(s.el * DEG), t[2] + s.dist * cel * Math.cos(s.az * DEG));
    camera.lookAt(t[0], t[1], t[2]);
    renderer.render(scene, camera);
    updateLabels(s);
  }

  resize();
  return { apply, resize, loadModels, spotTarget, lowerQuality, get layout() { return layout; }, get loaded() { return loaded; } };
}
