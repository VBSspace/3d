// Реализм: мягкие тени в углах (GTAO), материалы ЛДСП/металла/техники, комната с плиткой и светом.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { Pass, FullScreenQuad } from 'three/addons/postprocessing/Pass.js';

// Тонкое затенение кромок (cavity): тёмная линия во внутренних углах, светлая — на рёбрах.
// Нужно для мелкого рельефа (фрезеровка 3–5 мм), который большой GTAO не видит.
// Берёт нормали и глубину из GTAOPass, поэтому работает только когда он включён.
class CavityPass extends Pass {
  constructor(ao, camera, { valley = 0.5, ridge = 0.3, radius = 1 } = {}) {
    super();
    this.ao = ao; this.camera = camera;
    this.material = new THREE.ShaderMaterial({
      uniforms: {
        tDiffuse: { value: null }, tNormal: { value: null }, tDepth: { value: null },
        texel: { value: new THREE.Vector2() }, radius: { value: radius },
        cameraNear: { value: 0.1 }, cameraFar: { value: 100 },
        valley: { value: valley }, ridge: { value: ridge },
      },
      vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: `
        #include <packing>
        uniform sampler2D tDiffuse, tNormal, tDepth;
        uniform vec2 texel; uniform float radius, cameraNear, cameraFar, valley, ridge;
        varying vec2 vUv;
        float rawD(vec2 uv) { return texture2D(tDepth, uv).x; }
        float viewZ(float d) { return perspectiveDepthToViewZ(d, cameraNear, cameraFar); }
        vec3 nrm(vec2 uv) { return texture2D(tNormal, uv).xyz * 2.0 - 1.0; }
        // приращение нормали вдоль оси; 0, если соседи — другой предмет или фон
        float axis(vec2 o, float z0, float tol, bool isX) {
          vec2 a = vUv - o, b = vUv + o;
          float da = rawD(a), db = rawD(b);
          if (da >= 1.0 || db >= 1.0) return 0.0;
          if (abs(viewZ(da) - z0) > tol || abs(viewZ(db) - z0) > tol) return 0.0;
          vec3 na = nrm(a), nb = nrm(b);
          return isX ? nb.x - na.x : nb.y - na.y;
        }
        void main() {
          vec4 c = texture2D(tDiffuse, vUv);
          float d0 = rawD(vUv);
          if (d0 >= 1.0) { gl_FragColor = c; return; }
          float z0 = viewZ(d0);
          float tol = abs(z0) * 0.01 + 0.003;
          float k = axis(vec2(texel.x * radius, 0.0), z0, tol, true) + axis(vec2(0.0, texel.y * radius), z0, tol, false);
          float f = 1.0 - valley * clamp(-k, 0.0, 1.0) + ridge * clamp(k, 0.0, 1.0);
          gl_FragColor = vec4(c.rgb * f, c.a);
        }`,
      depthTest: false, depthWrite: false,
    });
    this.fsQuad = new FullScreenQuad(this.material);
  }
  setSize(w, h) { this.material.uniforms.texel.value.set(1 / w, 1 / h); }
  render(renderer, writeBuffer, readBuffer) {
    this.needsSwap = this.ao.enabled;          // без GTAO нормали не обновляются — пропускаем
    if (!this.ao.enabled) return;
    const u = this.material.uniforms;
    u.tDiffuse.value = readBuffer.texture;
    u.tNormal.value = this.ao.normalTexture;
    u.tDepth.value = this.ao.depthTexture;
    u.cameraNear.value = this.camera.near; u.cameraFar.value = this.camera.far;
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.fsQuad.render(renderer);
  }
}

// ------------------------------------------------------------------ постобработка
export function createPost(renderer, scene, camera, { mobile }) {
  const size = renderer.getSize(new THREE.Vector2());
  const rt = new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType, samples: mobile ? 2 : 4 });
  const composer = new EffectComposer(renderer, rt);
  composer.setPixelRatio(renderer.getPixelRatio());
  composer.setSize(size.x, size.y);
  composer.addPass(new RenderPass(scene, camera));
  const ao = new GTAOPass(scene, camera, size.x, size.y);
  // короткий радиус: затемняются стыки и углы, без грязных пятен по всей ячейке
  ao.blendIntensity = 0.85;
  ao.updateGtaoMaterial({ radius: 0.22, distanceExponent: 2.0, thickness: 1.0, scale: 1.0,
    samples: mobile ? 8 : 16, distanceFallOff: 1.0, screenSpaceRadius: false });
  ao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: mobile ? 6 : 8, rings: 2, samples: mobile ? 8 : 16 });
  composer.addPass(ao);
  // линии кромок ~1 css-пиксель на любом экране
  const cavity = new CavityPass(ao, camera, { radius: Math.min(2, Math.max(1, renderer.getPixelRatio())) });
  composer.addPass(cavity);
  composer.addPass(new OutputPass());
  return {
    composer, ao, cavity,
    render() { composer.render(); },
    setSize(w, h) { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(w, h); },
  };
}

// ------------------------------------------------------------------ материалы
const isWood = (code) => /^(H|K|F|R)\d/i.test(code);
const isMetal = (code) => /сталь|хром|steel|alum|алюм/i.test(code);

export function enhanceMaterials(meshes, renderer) {
  const aniso = renderer.capabilities.getMaxAnisotropy();
  const seen = new Set();
  for (const mesh of meshes) {
    const mat = mesh.userData.orig;
    if (!mat || seen.has(mat)) continue;
    seen.add(mat);
    const name = mat.name || '';
    if (mat.map) {
      mat.map.anisotropy = aniso;
      mat.map.needsUpdate = true;
    }
    if (name.startsWith('tex:')) {
      const code = name.slice(4);
      if (isMetal(code)) {
        Object.assign(mat, { metalness: 1, roughness: 0.22, envMapIntensity: 1.3 });
        mat.color.setRGB(0.86, 0.87, 0.89);
      } else {
        // ЛДСП: полуматовая поверхность, у древесных декоров — лёгкий рельеф пор
        Object.assign(mat, { metalness: 0, roughness: isWood(code) ? 0.58 : 0.66, envMapIntensity: 0.4 });
        if (isWood(code) && mat.map) { mat.bumpMap = mat.map; mat.bumpScale = 0.6; }
      }
    } else if (name === 'steel') {
      Object.assign(mat, { metalness: 1, roughness: 0.25, envMapIntensity: 1.3 });
    } else if (name === 'black') {
      Object.assign(mat, { roughness: 0.55, envMapIntensity: 0.5 });
    } else if (name.startsWith('col:')) {
      // бытовая техника: белая эмаль/пластик, тёмное стекло люка, хром
      const c = mat.color;
      const lum = 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
      if (mat.transparent) Object.assign(mat, { roughness: 0.05, metalness: 0, envMapIntensity: 1.6, opacity: Math.min(mat.opacity, 0.4) });
      else if (lum > 0.6) Object.assign(mat, { roughness: 0.3, metalness: 0, envMapIntensity: 0.9 });
      else if (lum > 0.3) Object.assign(mat, { roughness: 0.35, metalness: 0.6, envMapIntensity: 1.1 });
      else Object.assign(mat, { roughness: 0.4, metalness: 0, envMapIntensity: 0.8 });
    }
    mat.needsUpdate = true;
  }
}

// ------------------------------------------------------------------ комната
/** Паркет «ёлочкой» (классическая, английская): доска 90×540 мм под 45°.
 *  Текстура — квадрат √2·6·90 ≈ 763,7 мм, повторяется без швов. */
const PQ_W = 90, PQ_N = 6;
const PARQUET_MM = Math.SQRT2 * PQ_N * PQ_W;
function parquetTexture(renderer, color) {
  const N = 1024, c = document.createElement('canvas');
  c.width = c.height = N;
  const g = c.getContext('2d');
  const base = new THREE.Color(color || '#bdae97');
  const img = g.createImageData(N, N);
  const s = PARQUET_MM / N / PQ_W;           // ширин доски на пиксель
  const n = PQ_N;
  const hash = (a, b, k) => { const h = Math.sin(a * 127.1 + b * 311.7 + k * 74.7) * 43758.5453; return h - Math.floor(h); };
  // доска под точкой (u, v) в единицах ширины доски: [id строки, id доски, тип 0/1, позиция вдоль доски]
  function plank(u, v) {
    const cu = Math.floor(u);
    let cv = Math.floor(v);
    const j = Math.floor((cv - cu + n - 1) / (2 * n));
    const vv = v - 2 * n * j; cv -= 2 * n * j;
    if (cv - cu <= 0) return [j, cv, 0, u - cv];          // «горизонтальная» доска
    return [j, cu, 1, vv - (cu + 1)];                      // «вертикальная» доска
  }
  const rawId = (x, y) => {                                 // доска под точкой (x, y в ширинах доски)
    const [j, k, ty] = plank((x + y) / Math.SQRT2, (y - x) / Math.SQRT2);
    return (j * 100003 + k) * 2 + ty;
  };
  for (let yy = 0; yy < N; yy++) {
    for (let xx = 0; xx < N; xx++) {
      const x = xx * s, y = yy * s;
      const u = (x + y) / Math.SQRT2, v = (y - x) / Math.SQRT2;
      const [j, k, ty, tpos] = plank(u, v);
      const cls = (((k + n * j) % n) + n) % n;                 // доска с учётом повторения плитки
      const tn = 0.92 + hash(cls, ty, 1) * 0.16;               // разнотон досок
      const gr = 1 + 0.03 * Math.sin(tpos * 6.0 + hash(cls, ty, 5) * 30) + 0.015 * Math.sin(tpos * 1.7 + cls);
      let kk = tn * gr;
      const id = rawId(x, y);
      if (rawId(x + 2 * s, y) !== id || rawId(x, y + 2 * s) !== id || rawId(x - s, y) !== id || rawId(x, y - s) !== id) kk *= 0.74;   // шов между досками (≈3 px — читается и издалека)
      const o = (yy * N + xx) * 4;
      img.data[o] = Math.min(255, base.r * 255 * kk);
      img.data[o + 1] = Math.min(255, base.g * 255 * kk);
      img.data[o + 2] = Math.min(255, base.b * 255 * kk);
      img.data[o + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  const tx = new THREE.CanvasTexture(c);
  tx.colorSpace = THREE.SRGBColorSpace;
  tx.wrapS = tx.wrapT = THREE.RepeatWrapping;
  tx.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return tx;
}

function tileTexture(renderer) {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const g = c.getContext('2d');
  g.fillStyle = '#e4dfd7';
  g.fillRect(0, 0, 512, 512);
  // лёгкая «каменная» неоднородность керамогранита
  const img = g.getImageData(0, 0, 512, 512);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (rnd() - 0.5) * 10;
    img.data[i] += n; img.data[i + 1] += n; img.data[i + 2] += n;
  }
  g.putImageData(img, 0, 0);
  g.fillStyle = '#a89f94';            // затирка ~3 мм на плитке 600 мм (чуть шире — чтобы читалась издалека)
  g.fillRect(0, 0, 512, 5);
  g.fillRect(0, 0, 5, 512);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return t;
}

/**
 * Делает комнату «как настоящую»: непрозрачные окрашенные стены, плиточный пол, потолочный свет.
 * Стена, которая оказывается между камерой и мебелью, прячется (как в планировщиках интерьера).
 */
export function buildRoom({ scene, renderer, roomMeshes, parts, MM, wallColor, floor: floorOpt }) {
  const walls = [];
  // цвет стен — из model.json проекта (wallColor), по умолчанию светлый
  const wallMat = new THREE.MeshStandardMaterial({ color: wallColor || 0xeee9e2, roughness: 0.93, metalness: 0, side: THREE.DoubleSide });
  for (const m of roomMeshes) {
    const info = parts.get(m.userData.pid);
    if (!info || info.kind !== 'wall') continue;
    m.material = wallMat;
    m.userData.orig = wallMat;
    m.renderOrder = 0;
    m.castShadow = false;
    m.receiveShadow = true;
    walls.push({ mesh: m, min: new THREE.Vector3(...info.min).multiplyScalar(MM), max: new THREE.Vector3(...info.max).multiplyScalar(MM) });
  }
  if (!walls.length) return null;
  const rmin = walls.reduce((a, w) => a.min(w.min), new THREE.Vector3(Infinity, Infinity, Infinity));
  const rmax = walls.reduce((a, w) => a.max(w.max), new THREE.Vector3(-Infinity, -Infinity, -Infinity));
  const center = rmin.clone().add(rmax).multiplyScalar(0.5);
  for (const w of walls) {
    const ext = w.max.clone().sub(w.min);
    const ax = ext.x < ext.z ? 'x' : 'z';
    const c = w.min.clone().add(w.max).multiplyScalar(0.5);
    w.center = c;
    w.inward = new THREE.Vector3();
    w.inward[ax] = Math.sign(center[ax] - c[ax]) || 1;
  }
  // пол в границах комнаты: по умолчанию плитка 600×600, в проекте можно задать паркет «ёлочкой»
  const sx = rmax.x - rmin.x, sz = rmax.z - rmin.z;
  const parquet = floorOpt && floorOpt.type === 'herringbone';
  const tex = parquet ? parquetTexture(renderer, floorOpt.color) : tileTexture(renderer);
  const tile = parquet ? PARQUET_MM / 1000 : 0.6;
  tex.repeat.set(sx / tile, sz / tile);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(sx, sz),
    new THREE.MeshStandardMaterial({ map: tex, roughness: parquet ? 0.55 : 0.42, metalness: 0, envMapIntensity: parquet ? 0.5 : 0.7 }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(center.x, rmin.y + 0.0008, center.z);
  floor.receiveShadow = true;
  floor.userData.pid = null;
  scene.add(floor);
  return {
    walls, floor, center, min: rmin, max: rmax,
    update(camera, enabled, inside) {
      for (const w of walls) {
        // «как в жизни» стоим в проёме — видим все стены; иначе прячем ту, что загораживает мебель
        const outside = !inside && camera.position.clone().sub(w.center).dot(w.inward) < 0;
        w.mesh.visible = enabled && !outside;
      }
      floor.visible = enabled;
    },
  };
}

// ------------------------------------------------------------------ подсветка
const KELVIN = [[2700, 0xffa757], [3000, 0xffb46b], [3500, 0xffc489], [4000, 0xffd1a3], [4500, 0xffdbba],
  [5000, 0xffe4ce], [6000, 0xfff3ef], [6500, 0xfff9fd]];
function kelvin(t) {
  let best = KELVIN[0];
  for (const k of KELVIN) if (Math.abs(k[0] - t) < Math.abs(best[0] - t)) best = k;
  return new THREE.Color(best[1]);
}

/**
 * Светодиодные профили/ленты: светящийся рассеиватель + прямоугольный источник света вдоль профиля.
 * Всё крепится к самой детали — если она в ящике или на двери, свет едет вместе с ней.
 */
// мягкий ореол вокруг ленты: текстура «капсула» с плавным краем, складывается со сценой
let haloTex = null;
function haloTexture() {
  if (haloTex) return haloTex;
  const c = document.createElement('canvas');
  c.width = 256; c.height = 64;
  const g = c.getContext('2d');
  const img = g.createImageData(256, 64);
  for (let y = 0; y < 64; y++) {
    for (let x = 0; x < 256; x++) {
      const dx = Math.max(0, Math.abs(x - 127.5) - 96) / 32;   // края по длине
      const dy = Math.abs(y - 31.5) / 32;
      const d = Math.min(1, Math.hypot(dx, dy));
      const a = Math.pow(1 - d, 2.2);
      const i = (y * 256 + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = 255;
      img.data[i + 3] = Math.round(a * 255);
    }
  }
  g.putImageData(img, 0, 0);
  haloTex = new THREE.CanvasTexture(c);
  return haloTex;
}

export function buildLeds({ parts, meshOf, MM, mobile, solids }) {
  const leds = [];
  const list = [...parts.values()].filter((p) => p.kind === 'light' && p.light);
  if (!list.length) return null;
  const ray = new THREE.Raycaster();
  let shadowed = 0;
  for (const p of list) {
    const L = p.light;
    const mesh = meshOf(p.id);
    if (!mesh) continue;
    const c = kelvin(L.temp);
    const dir = new THREE.Vector3(...L.dir);
    const len = L.len * MM, w = Math.max(L.width - 4, 4) * MM;
    const pos = new THREE.Vector3(...L.center).multiplyScalar(MM).addScaledVector(dir, (L.depth / 2 + 0.4) * MM);
    // ось ленты и ориентация: X прямоугольника — вдоль профиля, нормаль — направление света
    const along = new THREE.Vector3(); along.setComponent(L.long, 1);
    const up = new THREE.Vector3().crossVectors(along, dir).normalize();   // правая тройка: x=вдоль, z=−свет
    const basis = new THREE.Matrix4().makeBasis(along, up, dir.clone().negate());
    // рассеиватель (не участвует в тон-маппинге — ярче белого, даёт ореол)
    const stripMat = new THREE.MeshBasicMaterial({ color: c.clone().multiplyScalar(2.6), toneMapped: false, side: THREE.DoubleSide });
    const strip = new THREE.Mesh(new THREE.PlaneGeometry(len, w), stripMat);
    strip.quaternion.setFromRotationMatrix(basis);
    strip.position.copy(pos);
    strip.raycast = () => {};
    mesh.add(strip);
    // ореол
    const halo = new THREE.Mesh(new THREE.PlaneGeometry(len + 0.08, w + 0.07), new THREE.MeshBasicMaterial({
      map: haloTexture(), color: c, transparent: true, opacity: 0.75, blending: THREE.AdditiveBlending,
      depthWrite: false, toneMapped: false, side: THREE.DoubleSide }));
    halo.quaternion.copy(strip.quaternion);
    halo.position.copy(pos).addScaledVector(dir, 0.0015);
    halo.raycast = () => {};
    halo.renderOrder = 3;
    mesh.add(halo);
    // свет: прожекторы вдоль профиля (через каждые ~45 см) с тенями и затуханием до ближайшей детали —
    // свет останавливается на полке/ящике и не «пробивает» до пола
    ray.set(pos.clone().addScaledVector(dir, 0.002), dir);
    const hit = ray.intersectObjects(solids.filter((m) => m !== mesh), false)[0];
    const reach = hit ? hit.distance : 1.0;
    const distance = Math.min(Math.max(reach * 1.7, 0.25), 1.6);
    const n = Math.max(1, Math.round(len / 0.45));
    const lights = [];
    for (let i = 0; i < n; i++) {
      const at = pos.clone().addScaledVector(along, ((i + 0.5) / n - 0.5) * len);
      const spot = new THREE.SpotLight(c, (mobile ? 1.6 : 1.8) / n * Math.max(1, len / 0.45), distance, 1.25, 1.0, 1.6);
      spot.position.copy(at);
      spot.target.position.copy(at).add(dir);
      if (shadowed < (mobile ? 4 : 8)) {
        shadowed++;
        spot.castShadow = true;
        spot.shadow.mapSize.set(mobile ? 256 : 512, mobile ? 256 : 512);
        spot.shadow.camera.near = 0.01;
        spot.shadow.camera.far = distance;
        spot.shadow.bias = -0.0005;
        spot.shadow.radius = 4;
        spot.shadow.blurSamples = 8;
      }
      mesh.add(spot, spot.target);
      spot.userData.base = spot.intensity;
      lights.push(spot);
    }
    leds.push({ strip, halo, lights, stripMat, base: c });
  }
  return {
    leds,
    temp: list[0]?.light.temp || 4000, level: 1, eve: false,
    set(on) { for (const l of leds) { l.strip.visible = l.halo.visible = on; l.lights.forEach((x) => (x.visible = on)); } },
    evening(on) { this.eve = on; this.apply(); },
    color(t) { this.temp = t; this.apply(); },
    brightness(k) { this.level = k; this.apply(); },
    apply() {
      const c = kelvin(this.temp), k = this.level;
      for (const l of leds) {
        l.stripMat.color.copy(c).multiplyScalar(2.6 * (0.45 + 0.55 * k));
        l.halo.material.color.copy(c);
        l.halo.material.opacity = Math.min(1, (this.eve ? 1 : 0.75) * k);
        for (const x of l.lights) { x.color.copy(c); x.intensity = x.userData.base * k; }
      }
    },
  };
}
