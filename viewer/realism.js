// Реализм: мягкие тени в углах (GTAO), материалы ЛДСП/металла/техники, комната с плиткой и светом.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';

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
  // ореол только у очень ярких точек — светодиодных лент (обычные поверхности не светятся)
  const bloom = new UnrealBloomPass(new THREE.Vector2(size.x, size.y), 0.55, 0.35, 1.0);
  bloom.enabled = false;
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  return {
    composer, ao, bloom,
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
export function buildRoom({ scene, renderer, roomMeshes, parts, MM }) {
  const walls = [];
  const wallMat = new THREE.MeshStandardMaterial({ color: 0xeee9e2, roughness: 0.93, metalness: 0, side: THREE.DoubleSide });
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
  // пол из плитки 600×600 в границах комнаты
  const sx = rmax.x - rmin.x, sz = rmax.z - rmin.z;
  const tex = tileTexture(renderer);
  tex.repeat.set(sx / 0.6, sz / 0.6);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(sx, sz),
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.42, metalness: 0, envMapIntensity: 0.7 }));
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
export function buildLeds({ parts, meshOf, MM, mobile }) {
  const leds = [];
  const list = [...parts.values()].filter((p) => p.kind === 'light' && p.light);
  if (!list.length) return null;
  RectAreaLightUniformsLib.init();
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
    const stripMat = new THREE.MeshBasicMaterial({ color: c.clone().multiplyScalar(4), toneMapped: false, side: THREE.DoubleSide });
    const strip = new THREE.Mesh(new THREE.PlaneGeometry(len, w), stripMat);
    strip.quaternion.setFromRotationMatrix(basis);
    strip.position.copy(pos);
    strip.raycast = () => {};
    mesh.add(strip);
    // источник света: прямоугольник длиной с профиль, светит наружу
    const light = new THREE.RectAreaLight(c, mobile ? 18 : 24, len, Math.max(w, 0.02));
    light.position.copy(pos);
    light.quaternion.setFromRotationMatrix(basis);
    mesh.add(light);
    leds.push({ strip, light, stripMat, base: c });
  }
  return {
    leds,
    set(on) { for (const l of leds) { l.strip.visible = on; l.light.visible = on; } },
  };
}
