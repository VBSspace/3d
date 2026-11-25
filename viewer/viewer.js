// BVSspace — 3D-просмотрщик мебели для клиентов.
// Данные проекта: model.glb (геометрия, метры, Y вверх) + model.json (детали, двери, помещение, мм).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import CONFIG from './config.js';
import { createPost, enhanceMaterials, buildRoom, buildLeds } from './realism.js';

const DRACO_PATH = 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/gltf/';
const MM = 0.001;
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const isTouch = matchMedia('(hover: none)').matches || 'ontouchstart' in window;
const store = { get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* приватный режим */ } } };

// ------------------------------------------------------------------ иконки
const I = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICON = {
  open: I('<rect x="4" y="3" width="10" height="18" rx="1"/><path d="M14 4.5 20 7v12l-6 2.5"/><circle cx="11.5" cy="12" r=".6" fill="currentColor"/>'),
  close: I('<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M12 3v18"/><circle cx="10" cy="12" r=".6" fill="currentColor"/><circle cx="14" cy="12" r=".6" fill="currentColor"/>'),
  inside: I('<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/><path d="M8.5 11h5M11 8.5v5"/>'),
  eye: I('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>'),
  person: I('<circle cx="12" cy="5" r="2.2"/><path d="M12 8v7m0 0-3 6m3-6 3 6M8 11h8"/>'),
  palette: I('<path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.6-.8 1.6-1.6 0-1.3-1.2-1.6-1.2-2.8 0-.9.7-1.6 1.6-1.6H16a5 5 0 0 0 5-5C21 6.3 17 3 12 3Z"/><circle cx="7.5" cy="11" r="1.1" fill="currentColor"/><circle cx="10" cy="7" r="1.1" fill="currentColor"/><circle cx="14.5" cy="7" r="1.1" fill="currentColor"/>'),
  xray: I('<rect x="3.5" y="3.5" width="17" height="17" rx="2" stroke-dasharray="3 2.4"/><path d="M8 8h8v8H8z"/>'),
  note: I('<path d="M12 21s-6.5-5.6-6.5-11A6.5 6.5 0 0 1 18.5 10c0 5.4-6.5 11-6.5 11Z"/><path d="M12 7.5v5M9.5 10h5"/>'),
  view: I('<path d="M12 2.8 20 7.3v9.4l-8 4.5-8-4.5V7.3z"/><path d="M12 12 20 7.3M12 12v9.2M12 12 4 7.3"/>'),
  more: I('<circle cx="5" cy="12" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/><circle cx="19" cy="12" r="1.3" fill="currentColor"/>'),
  share: I('<circle cx="18" cy="5.5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="18.5" r="2.5"/><path d="m8.2 10.8 7.6-4.1M8.2 13.2l7.6 4.1"/>'),
  camera: I('<path d="M4 7.5h3l1.8-2.5h6.4L17 7.5h3a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8.5a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13.3" r="3.6"/>'),
  ruler: I('<path d="m3 16.5 13.5-13.5 4.5 4.5L7.5 21z"/><path d="m7 12.5 2 2M10 9.5l2 2M13 6.5l2 2"/>'),
  dims: I('<path d="M3 20h18M3 17v6M21 17v6M4 3v13M1 4h6M1 15h6"/><rect x="9" y="5" width="11" height="10" rx="1"/>'),
  edges: I('<path d="M12 2.8 20 7.3v9.4l-8 4.5-8-4.5V7.3z"/><path d="M12 12 20 7.3M12 12v9.2M12 12 4 7.3"/>'),
  tex: I('<rect x="3.5" y="3.5" width="17" height="17" rx="2"/><path d="M3.5 15 9 9.5l5 5 2.5-2.5 4 4"/><circle cx="15.5" cy="8" r="1.5"/>'),
  moon: I('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/>'),
  sun: I('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
  wall: I('<path d="M3 5h18v14H3zM3 9.7h18M3 14.3h18M9 5v4.7M15 5v4.7M6 9.7v4.6M12 9.7v4.6M18 9.7v4.6M9 14.3V19M15 14.3V19"/>'),
  washer: I('<rect x="4.5" y="2.5" width="15" height="19" rx="2"/><circle cx="12" cy="13" r="4.5"/><path d="M7.5 5.5h3"/>'),
  help: I('<circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.6"/><circle cx="12" cy="17" r=".6" fill="currentColor"/>'),
  tg: I('<path d="m21 4-18 7.2 6.2 2.1L18 7.5l-7 7.3 7.2 5.2z"/>'),
  list: I('<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1" fill="currentColor"/><circle cx="4.5" cy="12" r="1" fill="currentColor"/><circle cx="4.5" cy="18" r="1" fill="currentColor"/>'),
  front: I('<rect x="5" y="4" width="14" height="16" rx="1"/><path d="M12 4v16"/>'),
  side: I('<path d="M6 4h12v16H6z"/><path d="M9 4v16"/>'),
  top: I('<rect x="4" y="7" width="16" height="10" rx="1"/><path d="M4 11h16"/>'),
  bulb: I('<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V16h5.2v-.2c0-.8.4-1.5 1-2A6 6 0 0 0 12 3Z"/>'),
  swipe: '<svg viewBox="0 0 48 48" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 26V11a3 3 0 0 1 6 0v11l7.5 1.6a4 4 0 0 1 3.1 4.6L35 38H21l-7-8.5a2.6 2.6 0 0 1 3.7-3.6z"/><path d="M8 8h-5m0 0 3-3M3 8l3 3M40 8h5m0 0-3-3m3 3-3 3"/></svg>',
  pinch: '<svg viewBox="0 0 48 48" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><circle cx="15" cy="15" r="4"/><circle cx="33" cy="33" r="4"/><path d="m5 5 6 6M43 43l-6-6M22 22l4 4"/></svg>',
  tap: '<svg viewBox="0 0 48 48" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 28V13a3 3 0 0 1 6 0v11l7.5 1.6a4 4 0 0 1 3.1 4.6L35 40H21l-7-8.5a2.6 2.6 0 0 1 3.7-3.6z"/><path d="M14 9a8 8 0 0 1 18 0"/></svg>',
};

// ------------------------------------------------------------------ состояние
const S = {
  data: null, root: null, parts: new Map(), partMeshes: [], roomMeshes: [], roomGroup: null, applMeshes: [],
  movers: [], moverOfPart: new Map(), mode: 'tex', dark: false, selected: null, tag: null,
  center: new THREE.Vector3(), size: new THREE.Vector3(), radius: 1,
  anim: null, tour: null, life: false, measure: null, dims: null, notesMode: false,
  notes: [], pins: new Map(), admin: null, idle: true, variant: 0, draft: null,
};

// ------------------------------------------------------------------ сцена
const stage = $('#stage');
// фон прозрачный — его цвет задаёт страница, поэтому он не искажается тон-маппингом
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false });
renderer.setClearColor(0x000000, 0);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.VSMShadowMap;     // мягкие размытые тени, как от комнатного света
renderer.shadowMap.autoUpdate = false;           // пересчёт только когда что-то движется
stage.appendChild(renderer.domElement);

const labels = new CSS2DRenderer({ element: $('#labels') });
labels.setSize(innerWidth, innerHeight);

const scene = new THREE.Scene();
const BG_LIGHT = new THREE.Color('#f4efe8');
const BG_DARK = new THREE.Color('#1d1a17');
scene.background = null;
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), 0.04).texture;

const camera = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, 0.02, 200);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.09;
controls.screenSpacePanning = true;
controls.maxPolarAngle = Math.PI * 0.95;
controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };

// постобработка: мягкие тени в углах и стыках (если видеокарта не тянет — отключится сама)
let post = null;
try { post = createPost(renderer, scene, camera, { mobile: isTouch }); } catch (e) { console.warn('без постобработки', e); }
function draw() { if (post) post.render(); else renderer.render(scene, camera); }

// свет: основной — сверху-спереди со стороны камеры (тени от полок ложатся внутрь ячеек),
// слабая заливка слева, мягкий рассеянный свет от неба/пола
const hemi = new THREE.HemisphereLight(0xffffff, 0xd8cfc4, 0.4);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff6ec, 2.2);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.bias = -0.0006;
sun.shadow.normalBias = 0.02;
sun.shadow.radius = isTouch ? 9 : 14;
sun.shadow.blurSamples = isTouch ? 10 : 20;
const fill = new THREE.DirectionalLight(0xf3f0ff, 0.6);
fill.target = sun.target;
scene.add(sun, sun.target, fill);
const floorMat = new THREE.MeshStandardMaterial({ color: 0xebe3d8, roughness: 0.95 });
const floor = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), floorMat);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

// общие материалы режимов
const MAT_WHITE = new THREE.MeshStandardMaterial({ color: 0xf7f5f2, roughness: 0.9, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
const EDGE_MAT = new THREE.LineBasicMaterial({ color: 0x3a332d, transparent: true, opacity: 0.85 });
const xrayCache = new Map();
const hiCache = new Map();

// ------------------------------------------------------------------ интерфейс
function buildUI() {
  const d = S.data;
  document.title = `${d.title || '3D-проект'} — BVSspace`;
  $('.title').textContent = d.title ? `${d.title}${d.code ? ' · ' + d.code.toUpperCase() : ''}` : '';
  const top = $('.topbar');
  top.append(
    btnChip('share', 'Поделиться', share),
    btnChip('help', '', () => showHint(true), 'icon', 'Подсказка'),
  );
  const dock = $('.dock');
  const hasMovers = d.movers.length > 0;
  const tools = [];
  if (hasMovers) tools.push(tool('openall', 'open', 'Открыть всё', toggleAll));
  if (hasMovers) tools.push(tool('tour', 'inside', 'Показать, что внутри', startTour));
  tools.push(tool('life', 'person', 'Как в жизни', toggleLife));
  if (d.facade?.material && d.facade.options?.length) tools.push(tool('colors', 'palette', 'Цвет фасадов', () => togglePop('colors')));
  tools.push(tool('xray', 'xray', 'Заглянуть внутрь', () => setMode(S.mode === 'xray' ? 'tex' : 'xray')));
  if (S.leds) tools.push(tool('leds', 'bulb', 'Подсветка', () => togglePop('leds')));
  if (CONFIG.api) tools.push(tool('notes', 'note', 'Замечание', toggleNotesMode));
  tools.push(el('span', 'sep'));
  tools.push(tool('views', 'view', 'Вид', () => togglePop('views')));
  tools.push(tool('more', 'more', 'Ещё', () => togglePop('more')));
  dock.append(...tools);

  // меню «Вид»
  const pv = $('#pop-views');
  pv.innerHTML = '<h4>Смотреть</h4>';
  const g = el('div', 'grid');
  [['3d', 'view', 'Объём'], ['front', 'front', 'Спереди'], ['side', 'side', 'Сбоку'], ['top', 'top', 'Сверху']].forEach(([v, ic, t]) => {
    g.append(opt(ic, t, () => { closePops(); setView(v); }));
  });
  pv.append(g);

  // меню «Ещё»
  const pm = $('#pop-more');
  pm.innerHTML = '<h4>Как показывать</h4>';
  const g1 = el('div', 'grid');
  g1.append(
    opt('tex', 'Обычный вид', () => setMode('tex'), 'mode-tex'),
    opt('edges', 'Чертёж (контуры)', () => setMode('edges'), 'mode-edges'),
    opt('xray', 'Заглянуть внутрь', () => setMode('xray'), 'mode-xray'),
    opt('moon', 'Тёмный фон', toggleDark, 'opt-dark'),
  );
  pm.append(g1);
  pm.append(el('h4', null, 'Инструменты'));
  const g2 = el('div', 'grid');
  g2.append(
    opt('dims', 'Габариты', toggleDims, 'opt-dims'),
    opt('ruler', 'Рулетка', toggleMeasure, 'opt-measure'),
    opt('camera', 'Снимок', snapshot),
  );
  if (S.roomMeshes.length) g2.append(opt('wall', 'Стены комнаты', toggleWalls, 'opt-walls'));
  if (S.applMeshes.length) g2.append(opt('washer', 'Техника', toggleAppl, 'opt-appl'));
  if (CONFIG.api) g2.append(opt('list', 'Все замечания', openNotesList));
  pm.append(g2);
  if (CONFIG.telegram) {
    pm.append(el('h4', null, 'Связь'));
    const g3 = el('div', 'grid');
    g3.append(opt('tg', 'Написать мастеру', () => window.open(`https://t.me/${CONFIG.telegram}`, '_blank', 'noopener')));
    pm.append(g3);
  }
  syncOpts();

  // меню «Цвет фасадов»
  if (d.facade?.options?.length) {
    const pc = $('#pop-colors');
    pc.innerHTML = '<h4>Цвет фасадов</h4>';
    const gc = el('div', 'grid');
    const opts = [{ name: 'Как в проекте', original: true }, ...d.facade.options];
    opts.forEach((o, i) => {
      const b = el('button', 'opt' + (i === 0 ? ' on' : ''));
      const sw = el('span', 'swatch');
      if (o.original) {
        const tx = d.materials?.[d.facade.material]?.texture;
        sw.style.backgroundImage = S.origFacadeUrl ? `url(${S.origFacadeUrl})` : '';
        if (!S.origFacadeUrl && tx) sw.style.background = '#a87b55';
      } else if (o.texture) sw.style.backgroundImage = `url(${o.texture})`;
      else sw.style.background = o.color;
      b.append(sw, document.createTextNode(o.name));
      b.onclick = () => { applyVariant(i); gc.querySelectorAll('.opt').forEach((x, j) => x.classList.toggle('on', j === i)); };
      gc.append(b);
    });
    pc.append(gc);
    pc.append(el('p', 'where', 'Цвет меняется у всех деталей из этого материала. Оттенок на экране может отличаться от образца.'));
  }

  // меню «Подсветка»: вкл/выкл, цвет света, яркость, вечерний свет
  if (S.leds) {
    const pl = el('div', 'pop', '');
    pl.id = 'pop-leds';
    document.body.append(pl);
    pl.innerHTML = '<h4>Подсветка</h4>';
    const g0 = el('div', 'grid');
    g0.append(opt('bulb', 'Включена', () => { if (!S.ledsOn) toggleLeds(); }, 'led-on'),
      opt('close', 'Выключена', () => { if (S.ledsOn) toggleLeds(); }, 'led-off'));
    pl.append(g0, el('h4', null, 'Цвет света'));
    const gc = el('div', 'grid');
    for (const [t, name, col] of [[3000, 'Тёплый<br>3000 K', '#ffb46b'], [4000, 'Нейтральный<br>4000 K', '#ffe2c0'], [6000, 'Холодный<br>6000 K', '#eef3ff']]) {
      const b = el('button', 'opt', `<span class="lamp" style="background:${col}"></span><span>${name}</span>`);
      b.dataset.temp = t;
      b.onclick = (e) => { e.stopPropagation(); if (!S.ledsOn) toggleLeds(); S.leds.color(t); syncOpts(); const c = $('#pop-leds .ledcalc'); if (c) c.innerHTML = ledSummaryHtml(S.ledW); };
      gc.append(b);
    }
    // яркость = реальные стандартные ленты (Вт/м); 9,6 Вт/м — исходная яркость модели
    pl.append(gc, el('h4', null, 'Яркость — какая лента'));
    const row = el('div', 'range', `<input type="range" min="0" max="${STRIPS.length - 1}" step="1" value="${STRIP_DEFAULT}" aria-label="Мощность ленты"><b></b>`);
    const rng = row.querySelector('input');
    const calc = el('div', 'ledcalc');
    const showStrip = () => {
      const w = STRIPS[+rng.value];
      S.ledW = w;
      row.querySelector('b').textContent = `${fmt1(w)} Вт/м`;
      calc.innerHTML = ledSummaryHtml(w);
    };
    rng.oninput = () => { if (!S.ledsOn) toggleLeds(); S.leds.brightness(STRIPS[+rng.value] / 9.6); showStrip(); };
    showStrip();
    pl.append(row, calc);
    if (CONFIG.api) {
      const send = el('button', 'sendchoice', 'Мне нравится так — отправить мастеру');
      send.onclick = async (e) => {
        e.stopPropagation();
        send.disabled = true;
        try {
          const first = [...S.parts.values()].find((p) => p.kind === 'light' && p.light);
          await api.post({ action: 'add', note: { part: first.id, partName: 'Подсветка', p: first.light.center,
            text: 'Выбор подсветки: ' + ledSummaryText(S.ledW), author: store.get('bvs_name', ''),
            view: { pos: camera.position.toArray(), target: controls.target.toArray() } } });
          const r = await api.list();
          S.notes = r.notes || [];
          renderPins();
          toast('Выбор подсветки отправлен мастеру');
        } catch { toast('Не получилось отправить. Попробуйте ещё раз'); }
        send.disabled = false;
      };
      pl.append(send);
    }
    const ge = el('div', 'grid');
    ge.style.marginTop = '14px';
    ge.append(opt('moon', 'Вечерний свет', toggleEvening, 'opt-evening'));
    pl.append(ge);
  }

  const foot = $('.foot');
  foot.innerHTML = `<a href="${CONFIG.calcUrl}" target="_blank" rel="noopener">Рассчитать свой проект</a>`;
}

function btnChip(ic, label, fn, cls = '', title = '') {
  const b = el('button', 'chipbtn ' + cls, ICON[ic] + (label ? `<span class="lbl">${label}</span>` : ''));
  b.title = title || label;
  b.onclick = fn;
  return b;
}
function tool(id, ic, label, fn) {
  const b = el('button', 'tool', ICON[ic] + `<span>${label}</span>`);
  b.id = 't-' + id;
  b.onclick = (e) => { e.stopPropagation(); fn(); };
  return b;
}
function opt(ic, label, fn, id) {
  const b = el('button', 'opt', ICON[ic] + `<span>${label}</span>`);
  if (id) b.id = id;
  b.onclick = (e) => { e.stopPropagation(); fn(); };
  return b;
}
function togglePop(name) {
  const p = $('#pop-' + name);
  const show = !p.classList.contains('show');
  closePops();
  if (show) { p.classList.add('show'); $('#t-' + name)?.classList.add('on'); }
}
function closePops() {
  document.querySelectorAll('.pop.show').forEach((p) => { p.classList.remove('show'); $('#t-' + p.id.slice(4))?.classList.remove('on'); });
}
function syncOpts() {
  ['tex', 'edges', 'xray'].forEach((m) => $('#mode-' + m)?.classList.toggle('on', S.mode === m));
  $('#t-xray')?.classList.toggle('on', S.mode === 'xray');
  $('#opt-dark')?.classList.toggle('on', S.dark);
  $('#opt-dims')?.classList.toggle('on', !!S.dims);
  $('#opt-measure')?.classList.toggle('on', !!S.measure);
  $('#opt-walls')?.classList.toggle('on', S.roomGroup?.visible);
  $('#opt-appl')?.classList.toggle('on', S.applMeshes[0]?.visible);
  $('#t-life')?.classList.toggle('on', S.life);
  $('#t-notes')?.classList.toggle('on', S.notesMode);
  $('#opt-evening')?.classList.toggle('on', !!S.evening);
  $('#led-on')?.classList.toggle('on', !!S.ledsOn);
  $('#led-off')?.classList.toggle('on', S.leds ? !S.ledsOn : false);
  document.querySelectorAll('#pop-leds [data-temp]').forEach((b) => b.classList.toggle('on', S.ledsOn && +b.dataset.temp === S.leds.temp));
  const anyOpen = S.movers.some((m) => m.target > 0.5);
  const oa = $('#t-openall');
  if (oa) oa.innerHTML = (anyOpen ? ICON.close : ICON.open) + `<span>${anyOpen ? 'Закрыть всё' : 'Открыть всё'}</span>`;
}

let toastT;
function toast(msg, ms = 2600) {
  const t = $('.toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove('show'), ms);
}
function modeChip(text, btn, fn) {
  const c = $('.modechip');
  if (!text) { c.classList.remove('show'); return; }
  c.innerHTML = `<span>${text}</span>`;
  const b = el('button', null, btn);
  b.onclick = fn;
  c.append(b);
  c.classList.add('show');
}

// ------------------------------------------------------------------ загрузка
async function load() {
  const base = new URL('.', location.href);
  const bar = $('#loader .bar i');
  const res = await fetch(new URL('model.json', base));
  if (!res.ok) throw new Error('model.json не найден');
  S.data = await res.json();
  const draco = new DRACOLoader().setDecoderPath(DRACO_PATH);
  const loader = new GLTFLoader().setDRACOLoader(draco);
  const gltf = await new Promise((ok, fail) => loader.load(new URL('model.glb', base).href, ok,
    (e) => { if (e.total) bar.style.width = Math.max(5, (e.loaded / e.total) * 100) + '%'; }, fail));
  bar.style.width = '100%';
  setup(gltf.scene);
}

function setup(root) {
  const d = S.data;
  S.root = root;
  scene.add(root);
  const roomIds = new Set((d.room || []).map((r) => r.id));
  S.roomGroup = new THREE.Group();
  scene.add(S.roomGroup);
  for (const p of d.parts) S.parts.set(p.id, p);
  for (const r of d.room || []) S.parts.set(r.id, { ...r, room: true });
  const objs = new Map();
  root.traverse((o) => { if (o.name && S.parts.has(o.name) && !objs.has(o.name)) objs.set(o.name, o); });
  for (const [id, o] of objs) {
    const info = S.parts.get(id);
    o.userData.pid = id;
    o.traverse((m) => {
      if (!m.isMesh) return;
      m.userData.pid = id;
      m.userData.orig = m.material;
      if (info.room) {
        m.receiveShadow = info.kind !== 'wall';
        m.castShadow = false;
        S.roomMeshes.push(m);
      } else {
        m.castShadow = true;
        m.receiveShadow = true;
        S.partMeshes.push(m);
        if (info.kind === 'appliance') S.applMeshes.push(m);
      }
    });
    if (roomIds.has(id)) S.roomGroup.attach(o);
  }
  // габариты сцены
  const bb = d.bbox;
  const mn = new THREE.Vector3(...bb.min).multiplyScalar(MM);
  const mx = new THREE.Vector3(...bb.max).multiplyScalar(MM);
  S.box = new THREE.Box3(mn, mx);
  S.box.getCenter(S.center);
  S.box.getSize(S.size);
  S.radius = S.size.length() / 2;
  const sb = d.sceneBox || bb;
  const smin = new THREE.Vector3(...sb.min).multiplyScalar(MM), smax = new THREE.Vector3(...sb.max).multiplyScalar(MM);
  const ssize = smax.clone().sub(smin);
  floor.scale.set(ssize.x + 4, ssize.z + 4, 1);
  floor.position.set((smin.x + smax.x) / 2, Math.min(0, smin.y) - 0.0005, (smin.z + smax.z) / 2);
  // свет и тени
  const r = Math.max(ssize.length() / 2, 1);
  sun.position.copy(S.center).add(new THREE.Vector3(0.55, 2.2, 1.3).multiplyScalar(r * 1.6));
  fill.position.copy(S.center).add(new THREE.Vector3(-1.2, 0.6, 0.8).multiplyScalar(r * 1.6));
  sun.target.position.copy(S.center);
  const sc = sun.shadow.camera;
  sc.left = sc.bottom = -r * 1.3; sc.right = sc.top = r * 1.3; sc.near = 0.1; sc.far = r * 6;
  sc.updateProjectionMatrix();
  camera.near = Math.max(0.01, r / 200);
  camera.far = r * 60;
  controls.maxDistance = r * 8;
  controls.minDistance = 0.15;

  enhanceMaterials(S.partMeshes, renderer);
  S.room = buildRoom({ scene, renderer, roomMeshes: S.roomMeshes, parts: S.parts, MM });
  if (S.room) floor.position.y -= 0.002;
  buildMovers();
  renderer.shadowMap.needsUpdate = true;
  scene.updateMatrixWorld(true);
  S.leds = buildLeds({ parts: S.parts, meshOf: partObject, MM, mobile: isTouch,
    solids: [...S.partMeshes, ...S.roomMeshes].filter((m) => S.parts.get(m.userData.pid)?.kind !== 'light') });
  S.ledsOn = !!S.leds;
  // текстура фасада (для образца «как в проекте»)
  const fm = findMaterial(d.facade?.material);
  if (fm?.map?.image) {
    try {
      const c = document.createElement('canvas');
      c.width = 96; c.height = 64;
      c.getContext('2d').drawImage(fm.map.image, 0, 0, 96, 64);
      S.origFacadeUrl = c.toDataURL('image/jpeg', 0.8);
    } catch { /* без образца */ }
  }
  S.facadeOrig = fm ? { map: fm.map, color: fm.color.clone() } : null;

  buildUI();
  setView('3d', false);
  $('#loader').classList.add('hide');
  setTimeout(() => $('#loader').remove(), 600);
  if (!store.get('bvs_hint_seen', false) || isTouch) showHint();
  initNotes();
}

function findMaterial(name) {
  if (!name) return null;
  let found = null;
  S.root.traverse((o) => { if (!found && o.isMesh && o.userData.orig?.name === name) found = o.userData.orig; });
  return found;
}

// ------------------------------------------------------------------ двери и ящики
function buildMovers() {
  const d = S.data;
  const groups = new Map();
  const getObj = (pid) => { let r = null; S.root.traverse((o) => { if (!r && o.userData.pid === pid && !o.isMesh) r = o; }); if (!r) S.root.traverse((o) => { if (!r && o.userData.pid === pid) r = o; }); return r; };
  const ordered = [...d.movers].sort((a, b) => (a.parent ? 1 : 0) - (b.parent ? 1 : 0));
  for (const m of ordered) {
    const pivot = new THREE.Group();
    pivot.name = m.id;
    const parent = m.parent && groups.get(m.parent) ? groups.get(m.parent) : S.root;
    const mv = { ...m, obj: pivot, t: 0, target: 0 };
    if (m.type === 'door') {
      const a = new THREE.Vector3(...m.a).multiplyScalar(MM);
      const b = new THREE.Vector3(...m.b).multiplyScalar(MM);
      pivot.position.copy(parent.worldToLocal(a.clone()));
      mv.axis = b.sub(a).normalize();
      mv.max = THREE.MathUtils.degToRad(m.angle || 75);
    } else {
      mv.vec = new THREE.Vector3(...m.dir).normalize().multiplyScalar((m.dist || 0) * MM);
    }
    parent.add(pivot);
    pivot.updateMatrixWorld(true);
    for (const pid of m.parts) {
      const o = getObj(pid);
      if (o) { pivot.attach(o); S.moverOfPart.set(pid, mv); }
    }
    groups.set(m.id, pivot);
    S.movers.push(mv);
  }
}
function setMover(mv, open) { mv.target = open ? 1 : 0; S.idle = false; }
function toggleAll() {
  const anyOpen = S.movers.some((m) => m.target > 0.5);
  S.movers.forEach((m, i) => setTimeout(() => setMover(m, !anyOpen), (anyOpen ? 0 : i * 90)));
  setTimeout(syncOpts, 20);
}
function stepMovers(dt) {
  for (const m of S.movers) {
    if (m.t === m.target) continue;
    renderer.shadowMap.needsUpdate = true;
    const speed = m.type === 'door' ? 1.6 : 1.3;
    m.t = m.target > m.t ? Math.min(m.target, m.t + dt * speed) : Math.max(m.target, m.t - dt * speed);
    const e = m.t < 0.5 ? 2 * m.t * m.t : 1 - Math.pow(-2 * m.t + 2, 2) / 2;
    if (m.type === 'door') m.obj.quaternion.setFromAxisAngle(m.axis, m.max * e);
    else m.obj.position.copy(m.vec).multiplyScalar(e);
  }
}

// ------------------------------------------------------------------ виды и камера
function fitDistance(size, fov = camera.fov) {
  const vfov = THREE.MathUtils.degToRad(fov);
  const hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
  const r = size;
  return Math.max(r / Math.sin(vfov / 2), r / Math.sin(hfov / 2)) * 0.8;
}
function viewPose(v) {
  const c = S.center.clone();
  const R = S.radius;
  let dir;
  if (v === 'front') dir = new THREE.Vector3(0, 0.02, 1);
  else if (v === 'side') dir = new THREE.Vector3(1, 0.02, 0.0001);
  else if (v === 'top') dir = new THREE.Vector3(0, 1, 0.012);
  else dir = new THREE.Vector3(0.55, 0.38, 1);
  dir.normalize();
  void R;
  const dist = fitBox(dir, c, 40);
  // центр свободной области экрана (между шапкой и нижней панелью) — сдвигаем взгляд
  const H = innerHeight;
  const k = ((1 - (2 * 78) / H) + (-1 + (2 * (innerWidth < 640 ? 112 : 104)) / H)) / 2;
  const up = new THREE.Vector3(0, 1, 0).addScaledVector(dir, -dir.y);
  if (up.lengthSq() < 1e-6) up.set(0, 0, -1);
  up.normalize();
  const shift = up.multiplyScalar(-k * dist * Math.tan(THREE.MathUtils.degToRad(20)));
  const target = c.clone().add(shift);
  return { pos: target.clone().add(dir.multiplyScalar(dist)), target, fov: 40 };
}
// расстояние, на котором весь корпус помещается между верхними кнопками и нижней панелью
function fitBox(dir, c, fov) {
  const cam = new THREE.PerspectiveCamera(fov, camera.aspect, 0.01, 100);
  const corners = [];
  const { min, max } = S.box;
  for (const x of [min.x, max.x]) for (const y of [min.y, max.y]) for (const z of [min.z, max.z]) corners.push(new THREE.Vector3(x, y, z));
  const H = innerHeight;
  const top = 1 - (2 * 78) / H, bottom = -1 + (2 * (innerWidth < 640 ? 112 : 104)) / H;
  // смещаем точку взгляда, чтобы центр корпуса был посередине свободной области
  const fits = (d) => {
    cam.position.copy(c).addScaledVector(dir, d);
    cam.lookAt(c);
    cam.updateMatrixWorld();
    let y0 = Infinity, y1 = -Infinity;
    for (const p of corners) {
      const q = p.clone().project(cam);
      if (q.z > 1 || Math.abs(q.x) > 0.92) return false;
      y0 = Math.min(y0, q.y); y1 = Math.max(y1, q.y);
    }
    return y1 - y0 <= top - bottom;
  };
  let lo = 0.2, hi = 60;
  for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; if (fits(m)) hi = m; else lo = m; }
  return hi * 1.04;
}
function setView(v, animate = true) {
  exitLife(false);
  stopTour();
  flyTo(viewPose(v), animate ? 0.9 : 0);
}
function flyTo(pose, dur = 0.9, done) {
  const from = { pos: camera.position.clone(), target: controls.target.clone(), fov: camera.fov };
  if (!dur) {
    camera.position.copy(pose.pos); controls.target.copy(pose.target); camera.fov = pose.fov || camera.fov;
    camera.updateProjectionMatrix(); controls.update(); done && done(); return;
  }
  S.anim = { from, to: pose, t: 0, dur, done };
}
function stepCamera(dt) {
  const a = S.anim;
  if (!a) return;
  a.t = Math.min(1, a.t + dt / a.dur);
  const e = 1 - Math.pow(1 - a.t, 3);
  camera.position.lerpVectors(a.from.pos, a.to.pos, e);
  controls.target.lerpVectors(a.from.target, a.to.target, e);
  if (a.to.fov) { camera.fov = a.from.fov + (a.to.fov - a.from.fov) * e; camera.updateProjectionMatrix(); }
  if (a.t >= 1) { S.anim = null; a.done && a.done(); }
}

// «Показать, что внутри»: открыть всё и облететь
function startTour() {
  exitLife(false);
  closePops();
  S.movers.forEach((m, i) => setTimeout(() => setMover(m, true), i * 90));
  setTimeout(syncOpts, 30);
  const dist = fitBox(new THREE.Vector3(0, 0.3, 1).normalize(), S.center, 40) * 1.3;
  const start = { az: -0.95, el: 0.3 };
  const pos = (az, elv) => S.center.clone().add(new THREE.Vector3(Math.sin(az) * Math.cos(elv), Math.sin(elv), Math.cos(az) * Math.cos(elv)).multiplyScalar(dist));
  flyTo({ pos: pos(start.az, start.el), target: S.center.clone(), fov: 40 }, 1.0, () => {
    S.tour = { t: 0, dur: 10, pos };
  });
  modeChip('Смотрим, что внутри…', 'Стоп', () => stopTour(true));
}
function stepTour(dt) {
  const T = S.tour;
  if (!T) return;
  T.t += dt / T.dur;
  const k = Math.min(1, T.t);
  const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
  const az = -0.95 + 1.9 * e;
  const elv = 0.3 - 0.18 * Math.sin(Math.PI * e);
  camera.position.copy(T.pos(az, elv));
  controls.target.copy(S.center);
  camera.lookAt(S.center);
  if (k >= 1) { stopTour(); flyTo(viewPose('3d'), 1.2); }
}
function stopTour(user) {
  if (!S.tour && !user) return;
  S.tour = null;
  if (!S.life && !S.measure && !S.notesMode) modeChip('');
}

// «Как в жизни»: глаза на высоте 1,6 м, из входа в комнату
function toggleLife() { S.life ? exitLife(true) : enterLife(); }
function enterLife() {
  stopTour();
  closePops();
  const e = S.data.eye;
  if (!e) return;
  const pos = new THREE.Vector3(...e.pos).multiplyScalar(MM);
  const tgt = new THREE.Vector3(...e.target).multiplyScalar(MM);
  const dir = tgt.clone().sub(pos).normalize();
  S.life = { saved: { pos: camera.position.clone(), target: controls.target.clone(), fov: camera.fov } };
  flyTo({ pos, target: pos.clone().add(dir.multiplyScalar(0.05)), fov: 68 }, 1.1);
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.rotateSpeed = -0.35;
  controls.minDistance = 0.01;
  modeChip('Вид от входа, рост 1,6 м — двигайте, чтобы осмотреться', 'Выйти', () => exitLife(true));
  syncOpts();
}
function exitLife(restore) {
  if (!S.life) return;
  const saved = S.life.saved;
  S.life = false;
  controls.enableZoom = true;
  controls.enablePan = true;
  controls.rotateSpeed = 1;
  controls.minDistance = 0.15;
  modeChip('');
  if (restore) flyTo(viewPose('3d'), 1.0);
  else camera.fov = 40, camera.updateProjectionMatrix();
  void saved;
  syncOpts();
}

// ------------------------------------------------------------------ режимы отображения
function setMode(m) {
  S.mode = m;
  for (const mesh of S.partMeshes) {
    if (m !== 'tex' && !mesh.userData.edges) {
      const kind = S.parts.get(mesh.userData.pid)?.kind;
      const eg = new THREE.EdgesGeometry(mesh.geometry, kind === 'appliance' || kind === 'hardware' ? 70 : 28);
      const ls = new THREE.LineSegments(eg, EDGE_MAT);
      ls.raycast = () => {};
      mesh.add(ls);
      mesh.userData.edges = ls;
    }
    if (mesh.userData.edges) mesh.userData.edges.visible = m !== 'tex';
  }
  EDGE_MAT.opacity = m === 'xray' ? 0.55 : 0.85;
  renderer.shadowMap.needsUpdate = true;
  if (post) post.ao.enabled = m === 'tex' && !S.lowPower;
  applyMaterials();
  syncOpts();
  if (m === 'xray') toast('Детали стали прозрачными — видно полки и внутреннее устройство');
}
function xrayOf(mat) {
  let x = xrayCache.get(mat.uuid);
  if (!x) {
    x = mat.clone();
    x.transparent = true;
    x.opacity = 0.22;
    x.depthWrite = false;
    xrayCache.set(mat.uuid, x);
  }
  return x;
}
function hiOf(mat) {
  let h = hiCache.get(mat.uuid);
  if (!h) {
    h = mat.clone();
    h.emissive = new THREE.Color(0xe07020);
    h.emissiveIntensity = 0.35;
    if (h.transparent) h.opacity = Math.max(h.opacity, 0.55);
    hiCache.set(mat.uuid, h);
  }
  return h;
}
function applyMaterials() {
  for (const mesh of S.partMeshes) {
    let m = mesh.userData.orig;
    if (S.mode === 'edges') m = MAT_WHITE;
    else if (S.mode === 'xray') m = xrayOf(m);
    if (S.selected && mesh.userData.pid === S.selected) m = hiOf(m);
    mesh.material = m;
    mesh.castShadow = S.mode !== 'xray';
  }
}
function toggleDark() {
  S.dark = !S.dark;
  document.body.classList.toggle('dark', S.dark);
  floorMat.color.set(S.dark ? 0x2b2622 : 0xebe3d8);
  EDGE_MAT.color.set(S.dark ? 0x1a1613 : 0x3a332d);
  hemi.intensity = S.dark ? 0.4 : 0.55;
  syncOpts();
}
// ------------------------------------------------------------------ подсветка: реальные ленты
// стандартные ленты для мебели, Вт/м; световой поток ≈ 90 лм/Вт с учётом рассеивателя профиля
const STRIPS = [2.4, 4.8, 7.2, 9.6, 12, 14.4, 19.2];
const STRIP_DEFAULT = 3;
const PSU = [12, 24, 36, 48, 60, 75, 100, 150, 200, 240, 320, 400];
const fmt1 = (v) => String(Math.round(v * 10) / 10).replace('.', ',');
function ledTotals(w) {
  const list = [...S.parts.values()].filter((p) => p.kind === 'light' && p.light);
  const meters = list.reduce((a, p) => a + p.light.len, 0) / 1000;
  const watts = meters * w;
  const psu = PSU.find((x) => x >= watts * 1.3) || Math.ceil(watts * 1.3);
  return { n: list.length, meters, watts, psu, lm: Math.round(w * 90 / 10) * 10 };
}
const TEMP_NAME = { 3000: 'тёплый', 4000: 'нейтральный', 6000: 'холодный' };
function ledSummaryHtml(w) {
  const t = ledTotals(w);
  return `<div><b>≈ ${t.lm} лм/м</b> · ${S.leds.temp} K (${TEMP_NAME[S.leds.temp] || ''})</div>` +
    `<div>${t.n} ${t.n === 1 ? 'профиль' : t.n < 5 ? 'профиля' : 'профилей'}, всего ${fmt1(t.meters)} м ленты</div>` +
    `<div>Мощность ≈ ${fmt1(t.watts)} Вт · блок питания от <b>${t.psu} Вт</b></div>`;
}
function ledSummaryText(w) {
  const t = ledTotals(w);
  return `${S.leds.temp} K (${TEMP_NAME[S.leds.temp] || ''}), лента ${fmt1(w)} Вт/м (≈ ${t.lm} лм/м), ` +
    `${t.n} шт., всего ${fmt1(t.meters)} м, ≈ ${fmt1(t.watts)} Вт, блок питания от ${t.psu} Вт.`;
}

// «Подсветка»: включить / выключить светодиоды
function toggleLeds() {
  S.ledsOn = !S.ledsOn;
  S.leds.set(S.ledsOn);
  renderer.shadowMap.needsUpdate = true;
  toast(S.ledsOn ? 'Подсветка включена' : 'Подсветка выключена', 1500);
  syncOpts();
}
// «Вечерний свет»: приглушаем свет комнаты — светодиоды становятся заметны
function toggleEvening() {
  S.evening = !S.evening;
  const k = S.evening ? 0.18 : 1;
  hemi.intensity = 0.4 * k;
  sun.intensity = 2.2 * k;
  fill.intensity = 0.6 * k;
  scene.traverse((o) => {
    if (!o.isMesh) return;
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      if (!m || m.envMapIntensity === undefined) continue;
      if (m.userData.envBase === undefined) m.userData.envBase = m.envMapIntensity;
      m.envMapIntensity = m.userData.envBase * (S.evening ? 0.15 : 1);
    }
  });
  S.leds?.evening(S.evening);
  if (S.evening && S.leds && !S.ledsOn) toggleLeds();
  toast(S.evening ? 'Вечерний свет — видно подсветку' : 'Дневной свет');
  syncOpts();
}
function toggleWalls() { S.roomGroup.visible = !S.roomGroup.visible; syncOpts(); }
function toggleAppl() { const v = !S.applMeshes[0].visible; S.applMeshes.forEach((m) => (m.visible = v)); syncOpts(); }

// цвет фасадов
function applyVariant(i) {
  const d = S.data;
  const mat = findMaterial(d.facade.material);
  if (!mat) return;
  S.variant = i;
  xrayCache.clear(); hiCache.clear();
  if (i === 0) {
    mat.map = S.facadeOrig.map; mat.color.copy(S.facadeOrig.color); mat.needsUpdate = true; applyMaterials(); return;
  }
  const o = d.facade.options[i - 1];
  if (o.texture) {
    new THREE.TextureLoader().load(o.texture, (t) => {
      t.colorSpace = THREE.SRGBColorSpace;
      t.flipY = false;
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.anisotropy = 4;
      mat.map = t; mat.color.set(0xffffff); mat.needsUpdate = true; applyMaterials();
    });
  } else {
    mat.map = null; mat.color.set(o.color); mat.needsUpdate = true; applyMaterials();
  }
  toast(o.name);
}

// ------------------------------------------------------------------ выбор детали
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
function pick(ev, withRoom = false) {
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const vis = S.partMeshes.filter((m) => m.visible);
  const hit = ray.intersectObjects(vis, false)[0];
  if (hit) return hit;
  if (withRoom && S.roomGroup.visible) return ray.intersectObjects(S.roomMeshes.filter((m) => m.visible), false)[0] || null;
  return null;
}
function select(hit) {
  clearTag();
  if (!hit) { S.selected = null; applyMaterials(); return; }
  const pid = hit.object.userData.pid;
  const p = S.parts.get(pid);
  S.selected = p.room ? null : pid;
  applyMaterials();
  // компактная подпись: название, размер, материал; закрывается сама
  const div = el('div', 'tag');
  div.innerHTML = `<b>${esc(p.name)}</b>` +
    (p.size ? `<span class="sz">${p.size.join(' × ')} мм</span>` : '') +
    (p.material ? `<div class="mt">${esc(p.material)}</div>` : '');
  const acts = el('div', 'acts');
  const mv = S.moverOfPart.get(pid);
  if (mv) {
    const b = el('button', 'pri', mv.target > 0.5 ? 'Закрыть' : (mv.type === 'door' ? 'Открыть' : 'Выдвинуть'));
    b.onclick = (e) => { e.stopPropagation(); setMover(mv, mv.target < 0.5); syncOpts(); b.textContent = mv.target > 0.5 ? 'Закрыть' : (mv.type === 'door' ? 'Открыть' : 'Выдвинуть'); };
    acts.append(b);
  }
  if (CONFIG.api) {
    const b = el('button', null, 'Замечание сюда');
    b.onclick = (e) => { e.stopPropagation(); clearTag(); startDraft(hit); };
    acts.append(b);
  }
  if (acts.children.length) div.append(acts);
  div.addEventListener('pointerdown', (e) => e.stopPropagation());
  const obj = new CSS2DObject(div);
  obj.center.set(0.5, 1);
  hit.object.add(obj);
  obj.position.copy(hit.object.worldToLocal(hit.point.clone()));
  S.tag = obj;
  // закрыть через 5 с, если на подпись не навели мышь / не нажали кнопку
  let hold = false;
  div.addEventListener('pointerenter', () => { hold = true; });
  div.addEventListener('pointerleave', () => { hold = false; });
  const close = () => { if (S.tag !== obj) return; if (hold) { tagTimer = setTimeout(close, 2000); return; } select(null); };
  clearTimeout(tagTimer);
  tagTimer = setTimeout(close, 5000);
}
let tagTimer;
function clearTag() {
  clearTimeout(tagTimer);
  if (S.tag) { S.tag.element.remove(); S.tag.parent?.remove(S.tag); S.tag = null; }
}

// ------------------------------------------------------------------ габариты
function toggleDims() {
  if (S.dims) { S.dims.traverse((o) => o.element?.remove()); scene.remove(S.dims); S.dims = null; syncOpts(); return; }
  const g = new THREE.Group();
  const b = S.box;
  const off = 0.08;
  const lm = new THREE.LineBasicMaterial({ color: 0xe07020, depthTest: false });
  const line = (a, c, text) => {
    const geo = new THREE.BufferGeometry().setFromPoints([a, c]);
    const l = new THREE.Line(geo, lm); l.renderOrder = 10; g.add(l);
    const dir = c.clone().sub(a).normalize();
    const n = Math.abs(dir.y) > 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
    for (const p of [a, c]) {
      const t = new THREE.Line(new THREE.BufferGeometry().setFromPoints([p.clone().addScaledVector(n, -0.03), p.clone().addScaledVector(n, 0.03)]), lm);
      t.renderOrder = 10; g.add(t);
    }
    const lab = new CSS2DObject(el('div', 'dim', text));
    lab.position.copy(a).add(c).multiplyScalar(0.5);
    g.add(lab);
  };
  const mm = (v) => `${Math.round(v * 1000)} мм`;
  const { min, max } = b;
  line(new THREE.Vector3(min.x, min.y + 0.01, max.z + off), new THREE.Vector3(max.x, min.y + 0.01, max.z + off), 'ширина ' + mm(max.x - min.x));
  line(new THREE.Vector3(min.x - off, min.y, max.z), new THREE.Vector3(min.x - off, max.y, max.z), 'высота ' + mm(max.y - min.y));
  line(new THREE.Vector3(max.x + off, min.y + 0.01, min.z), new THREE.Vector3(max.x + off, min.y + 0.01, max.z), 'глубина ' + mm(max.z - min.z));
  scene.add(g);
  S.dims = g;
  closePops();
  syncOpts();
}

// ------------------------------------------------------------------ рулетка
function toggleMeasure() {
  closePops();
  if (S.measure) {
    S.measure.group.traverse((o) => o.element?.remove());
    scene.remove(S.measure.group);
    S.measure = null;
    modeChip('');
  } else {
    if (S.notesMode) toggleNotesMode();
    S.measure = { group: new THREE.Group(), a: null };
    scene.add(S.measure.group);
    modeChip('Рулетка: нажмите на две точки', 'Готово', toggleMeasure);
  }
  syncOpts();
}
function measureClick(hit) {
  if (!hit) return;
  const M = S.measure;
  const p = hit.point.clone();
  const dot = new CSS2DObject(el('div', 'dot'));
  dot.position.copy(p);
  M.group.add(dot);
  if (!M.a) { M.a = p; return; }
  const geo = new THREE.BufferGeometry().setFromPoints([M.a, p]);
  const l = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xe07020, depthTest: false }));
  l.renderOrder = 10;
  M.group.add(l);
  const lab = new CSS2DObject(el('div', 'dim', `${Math.round(M.a.distanceTo(p) * 1000)} мм`));
  lab.position.copy(M.a).add(p).multiplyScalar(0.5);
  M.group.add(lab);
  M.a = null;
}

// ------------------------------------------------------------------ снимок
function snapshot() {
  closePops();
  clearTag();
  if (new URLSearchParams(location.search).has('savepreview')) { renderPreview(); return; }
  S.room?.update(camera, S.roomGroup.visible, !!S.life);
  draw();
  const src = renderer.domElement;
  const c = document.createElement('canvas');
  c.width = src.width; c.height = src.height;
  const g = c.getContext('2d');
  g.fillStyle = '#' + (S.dark ? BG_DARK : BG_LIGHT).getHexString();
  g.fillRect(0, 0, c.width, c.height);
  g.drawImage(src, 0, 0);
  const s = c.width / 1200;
  g.font = `800 ${Math.round(22 * s)}px Montserrat, sans-serif`;
  const txt = 'BVSspace';
  const w = g.measureText(txt).width;
  const x = c.width - w - 30 * s, y = c.height - 30 * s;
  g.fillStyle = S.dark ? 'rgba(255,255,255,.8)' : 'rgba(43,39,36,.75)';
  g.fillText(txt, x, y);
  g.font = `500 ${Math.round(11 * s)}px Montserrat, sans-serif`;
  g.fillText('мебель на заказ', x, y + 16 * s);
  if (new URLSearchParams(location.search).has('savepreview')) { savePreview(c); return; }
  c.toBlob((blob) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `bvsspace-${S.data.code || 'proekt'}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }, 'image/png');
  toast('Снимок сохранён');
}
// для разработчика: локальный сервер (tools/serve.py) сохраняет preview.jpg рядом с моделью
// превью для мессенджеров: отдельный кадр 1200×630 с видом «объём», без интерфейса
function renderPreview() {
  const W = 1200, H = 630, pr = renderer.getPixelRatio();
  const saved = { pos: camera.position.clone(), target: controls.target.clone(), aspect: camera.aspect, fov: camera.fov };
  renderer.setPixelRatio(1);
  renderer.setSize(W, H, false);
  post?.setSize(W, H);
  camera.aspect = W / H;
  camera.fov = 40;
  camera.updateProjectionMatrix();
  const dir = new THREE.Vector3(0.55, 0.3, 1).normalize();
  const d = fitBox(dir, S.center, 40) * 0.92;
  camera.position.copy(S.center).addScaledVector(dir, d);
  camera.lookAt(S.center);
  S.room?.update(camera, S.roomGroup.visible, false);
  draw();
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.fillStyle = '#' + BG_LIGHT.getHexString();
  g.fillRect(0, 0, W, H);
  g.drawImage(renderer.domElement, 0, 0);
  renderer.setPixelRatio(pr);
  renderer.setSize(innerWidth, innerHeight);
  post?.setSize(innerWidth, innerHeight);
  camera.aspect = saved.aspect; camera.fov = saved.fov; camera.updateProjectionMatrix();
  camera.position.copy(saved.pos); controls.target.copy(saved.target);
  savePreview(c);
}
function savePreview(c) {
  const t = document.createElement('canvas');
  t.width = 1200; t.height = 630;
  const k = Math.max(1200 / c.width, 630 / c.height);
  t.getContext('2d').drawImage(c, (1200 - c.width * k) / 2, (630 - c.height * k) / 2, c.width * k, c.height * k);
  t.toBlob((b) => fetch('preview.jpg', { method: 'PUT', body: b }).then((r) => toast(r.ok ? 'preview.jpg сохранён' : 'не сохранено')), 'image/jpeg', 0.86);
}

// ------------------------------------------------------------------ поделиться
async function share() {
  const url = location.origin + location.pathname;
  const title = `${S.data.title || 'Проект мебели'} — BVSspace`;
  if (navigator.share && isTouch) {
    try { await navigator.share({ title, text: 'Посмотрите проект мебели в 3D', url }); return; } catch { /* отмена */ }
  }
  try { await navigator.clipboard.writeText(url); toast('Ссылка скопирована — отправьте её близким'); }
  catch { prompt('Скопируйте ссылку:', url); }
}

// ------------------------------------------------------------------ подсказка
let hintT;
function showHint(force) {
  const h = $('#hint');
  const items = isTouch
    ? [['swipe', 'Ведите пальцем — повернуть'], ['pinch', 'Двумя пальцами — приблизить'], ['tap', 'Нажмите на дверь — откроется']]
    : [['swipe', 'Тяните мышью — повернуть'], ['pinch', 'Колёсико — приблизить'], ['tap', 'Нажмите на дверь — откроется']];
  h.innerHTML = '<div class="in">' + items.map(([ic, t]) => `<div class="it">${ICON[ic]}<span>${t}</span></div>`).join('') + '</div>';
  h.classList.add('show');
  clearTimeout(hintT);
  hintT = setTimeout(hideHint, force ? 6000 : 5000);
  store.set('bvs_hint_seen', true);
}
function hideHint() { $('#hint').classList.remove('show'); }

// ------------------------------------------------------------------ замечания
const api = {
  async call(method, body) {
    const u = new URL(CONFIG.api, location.href);
    u.searchParams.set('project', projectId());
    // «простой» запрос (text/plain) — без предварительного CORS-запроса
    if (body && S.admin) body = { ...body, admin: S.admin };
    const r = await fetch(u, { method, headers: body ? { 'Content-Type': 'text/plain;charset=UTF-8' } : {},
      body: body ? JSON.stringify(body) : undefined, cache: 'no-store' });
    if (!r.ok) throw new Error((await r.text()) || r.status);
    return r.json();
  },
  list() { return this.call('GET'); },
  post(b) { return this.call('POST', b); },
};

function projectId() {
  const segs = location.pathname.split('/').filter((s) => s && !s.endsWith('.html'));
  return (segs.pop() || S.data.code || 'proekt').toLowerCase();
}
async function initNotes() {
  if (!CONFIG.api) return;
  const m = location.hash.match(/admin=([^&]+)/);
  if (m) {
    store.set('bvs_admin', decodeURIComponent(m[1]));
    history.replaceState(null, '', location.pathname + location.search + location.hash.replace(/&?admin=[^&]+/, '').replace(/^#$/, ''));
  }
  S.admin = store.get('bvs_admin', null);
  try {
    if (S.admin) {
      const w = await api.post({ action: 'whoami' });
      if (!w.admin) { S.admin = null; store.set('bvs_admin', null); }
      else toast('Режим мастера: можно отвечать и отмечать «Решено»');
    }
    const r = await api.list();
    S.notes = r.notes || [];
  } catch (e) {
    console.warn('замечания недоступны', e);
    return;
  }
  renderPins();
  const n = location.hash.match(/note=(\d+)/);
  if (n) setTimeout(() => focusNote(+n[1]), 700);
  addEventListener('hashchange', () => {
    if (/admin=/.test(location.hash)) { location.reload(); return; }
    const h = location.hash.match(/note=(\d+)/);
    if (h) focusNote(+h[1]);
  });
}
function partObject(pid) {
  let r = null;
  scene.traverse((o) => { if (!r && o.isMesh && o.userData.pid === pid) r = o; });
  return r;
}
function renderPins() {
  for (const [, o] of S.pins) { o.element.remove(); o.parent?.remove(o); }
  S.pins.clear();
  for (const n of S.notes) {
    const host = partObject(n.part) || S.root;
    // внешний блок двигает CSS2DRenderer, внутренний — увеличивается при наведении (иначе метка «прыгает»)
    const div = el('div', 'pinwrap');
    div.append(el('div', 'pin' + (n.status === 'resolved' ? ' done' : ''), n.status === 'resolved' ? '✓' : String(n.n)));
    div.title = n.text;
    div.addEventListener('pointerdown', (e) => e.stopPropagation());
    div.onclick = (e) => { e.stopPropagation(); focusNote(n.n); };
    const o = new CSS2DObject(div);
    o.position.set(...n.p.map((v) => v * MM));
    host.add(o);
    S.pins.set(n.n, o);
  }
  const t = $('#t-notes');
  if (t) {
    t.querySelector('.badge')?.remove();
    const open = S.notes.filter((x) => x.status !== 'resolved').length;
    if (open) t.append(el('span', 'badge', String(open)));
  }
  if ($('#notes').classList.contains('show')) renderNotesList();
}
function toggleNotesMode() {
  closePops();
  if (S.measure) toggleMeasure();
  S.notesMode = !S.notesMode;
  if (S.notesMode) {
    exitLife(false);
    modeChip('Нажмите на место в модели, к которому есть замечание', 'Отмена', toggleNotesMode);
    if (!S.notes.length) toast('Замечания видны вам и мастеру — каждое на своём месте модели', 3500);
  } else { modeChip(''); cancelDraft(); }
  syncOpts();
}
function startDraft(hit) {
  cancelDraft();
  if (!hit) return;
  const pid = hit.object.userData.pid;
  const p = S.parts.get(pid);
  const local = hit.object.worldToLocal(hit.point.clone());
  const wrap = el('div', 'pinwrap');
  wrap.append(el('div', 'pin new', '+'));
  const pin = new CSS2DObject(wrap);
  pin.position.copy(local);
  hit.object.add(pin);
  S.draft = { pid, name: p.name, p: local.toArray().map((v) => Math.round(v / MM * 10) / 10), pin,
    view: { pos: camera.position.toArray().map((v) => +v.toFixed(3)), target: controls.target.toArray().map((v) => +v.toFixed(3)) } };
  if (S.notesMode) { S.notesMode = false; modeChip(''); syncOpts(); }
  openSheet('Новое замечание', (body) => {
    body.innerHTML = `<div class="where">Место: <b>${esc(p.name)}</b></div>
      <div class="form"><textarea id="nt" rows="4" maxlength="2000" placeholder="Что изменить или уточнить? Например: «полку сделать выше на 5 см»"></textarea>
      <input id="na" maxlength="60" placeholder="Ваше имя (необязательно)" value="${esc(store.get('bvs_name', ''))}">
      <input id="hp" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px" aria-hidden="true">
      <div class="row"><button id="nc">Отмена</button><button class="pri" id="ns">Отправить</button></div></div>`;
    $('#nc').onclick = () => { cancelDraft(); closeSheet(); };
    $('#ns').onclick = sendDraft;
    setTimeout(() => $('#nt').focus(), 300);
  }, cancelDraft);
}
function cancelDraft() {
  if (!S.draft) return;
  S.draft.pin.element.remove();
  S.draft.pin.parent?.remove(S.draft.pin);
  S.draft = null;
}
async function sendDraft() {
  const text = $('#nt').value.trim();
  if (!text) { $('#nt').focus(); return; }
  const author = $('#na').value.trim();
  store.set('bvs_name', author);
  const b = $('#ns');
  b.disabled = true; b.textContent = 'Отправляем…';
  try {
    const r = await api.post({ action: 'add', hp: $('#hp').value,
      note: { part: S.draft.pid, partName: S.draft.name, p: S.draft.p, text, author, view: S.draft.view } });
    cancelDraft();
    S.notes = r.notes;
    renderPins();
    closeSheet();
    toast(`Замечание №${r.note.n} отправлено мастеру`);
  } catch (e) {
    b.disabled = false; b.textContent = 'Отправить';
    toast('Не получилось отправить. Проверьте интернет и попробуйте ещё раз');
  }
}
function fmtDate(s) {
  try { return new Date(s).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }); } catch { return s; }
}
function openNotesList() { closePops(); openSheet(`Замечания (${S.notes.length})`, renderNotesList); }
function renderNotesList(body = $('#notes .body'), sel) {
  $('#notes header b').textContent = `Замечания (${S.notes.length})`;
  if (!S.notes.length) {
    body.innerHTML = `<div class="empty">Пока нет замечаний.<br>Нажмите «Замечание» внизу, затем — на место в модели, и напишите, что поменять.</div>`;
    return;
  }
  body.innerHTML = '';
  for (const n of [...S.notes].sort((a, b) => (a.status === 'resolved') - (b.status === 'resolved') || b.n - a.n)) {
    const c = el('div', 'note' + (n.status === 'resolved' ? ' done' : '') + (sel === n.n ? ' sel' : ''));
    c.innerHTML = `<div class="hd"><span class="num">${n.status === 'resolved' ? '✓' : n.n}</span><span>№${n.n} · ${esc(n.partName || '')} · ${fmtDate(n.created)}</span></div>
      <div class="tx">${esc(n.text)}</div>${n.author ? `<div class="where">— ${esc(n.author)}</div>` : ''}
      ${(n.replies || []).map((r) => `<div class="reply"><b>${esc(r.author || 'BVSspace')}:</b> ${esc(r.text)}</div>`).join('')}
      ${n.status === 'resolved' ? '<div class="st">Решено</div>' : ''}`;
    c.onclick = () => focusNote(n.n, false);
    if (S.admin) {
      const a = el('div', 'adm');
      const rb = el('button', null, 'Ответить');
      rb.onclick = (e) => { e.stopPropagation(); replyForm(c, n); };
      const sb = el('button', n.status === 'resolved' ? '' : 'pri', n.status === 'resolved' ? 'Вернуть в работу' : 'Решено');
      sb.onclick = async (e) => { e.stopPropagation(); await adminAct({ action: 'status', n: n.n, status: n.status === 'resolved' ? 'open' : 'resolved' }); };
      const db = el('button', null, 'Удалить');
      db.onclick = async (e) => { e.stopPropagation(); if (confirm(`Удалить замечание №${n.n}?`)) await adminAct({ action: 'delete', n: n.n }); };
      a.append(rb, sb, db);
      c.append(a);
    }
    body.append(c);
  }
}
function replyForm(card, n) {
  if (card.querySelector('.form')) return;
  const f = el('div', 'form');
  f.style.marginTop = '8px';
  f.innerHTML = '<textarea rows="3" maxlength="2000" placeholder="Ответ клиенту"></textarea><div class="row"><button class="pri">Ответить</button></div>';
  f.onclick = (e) => e.stopPropagation();
  f.querySelector('button').onclick = async () => {
    const t = f.querySelector('textarea').value.trim();
    if (t) await adminAct({ action: 'reply', n: n.n, text: t });
  };
  card.append(f);
  f.querySelector('textarea').focus();
}
async function adminAct(body) {
  try { const r = await api.post(body); S.notes = r.notes; renderPins(); renderNotesList(); }
  catch { toast('Не получилось. Попробуйте ещё раз'); }
}
function focusNote(num, openList = true) {
  const n = S.notes.find((x) => x.n === num);
  if (!n) return;
  exitLife(false);
  const pin = S.pins.get(num);
  // если замечание на двери — откроем её, чтобы место было видно
  const mv = S.moverOfPart.get(n.part);
  const wp = new THREE.Vector3();
  if (pin) pin.getWorldPosition(wp);
  if (n.view) {
    flyTo({ pos: new THREE.Vector3(...n.view.pos), target: new THREE.Vector3(...n.view.target), fov: 40 }, 1.0);
  } else if (pin) {
    flyTo({ pos: wp.clone().add(new THREE.Vector3(0.35, 0.3, 1.2)), target: wp, fov: 40 }, 1.0);
  }
  if (mv && mv.target < 0.5 && n.view == null) setMover(mv, true);
  if (pin) { pin.element.firstChild.animate([{ scale: 1 }, { scale: 1.5 }, { scale: 1 }], { duration: 700, iterations: 2 }); }
  if (openList) openSheet(`Замечания (${S.notes.length})`, (b) => renderNotesList(b, num));
  else document.querySelectorAll('#notes .note').forEach((c) => c.classList.toggle('sel', c.querySelector('.num')?.textContent == num));
}

let sheetClose = null;
function openSheet(title, fill, onClose) {
  const s = $('#notes');
  $('#notes header b').textContent = title;
  fill($('#notes .body'));
  s.classList.add('show');
  sheetClose = onClose || null;
}
function closeSheet() {
  $('#notes').classList.remove('show');
  if (sheetClose) { const f = sheetClose; sheetClose = null; f(); }
}

// ------------------------------------------------------------------ ввод
let down = null;
renderer.domElement.addEventListener('pointerdown', (e) => {
  down = { x: e.clientX, y: e.clientY, t: performance.now() };
  hideHint();
  S.idle = false;
  if (S.tour) stopTour(true);
  S.anim = null;
});
renderer.domElement.addEventListener('pointerup', (e) => {
  if (!down) return;
  const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
  const dt = performance.now() - down.t;
  down = null;
  if (moved > 7 || dt > 600) return;
  closePops();
  if (S.measure) { measureClick(pick(e, true)); return; }
  if (S.notesMode) { const h = pick(e, true); if (h) startDraft(h); else toast('Нажмите на саму мебель или стену'); return; }
  const hit = pick(e);
  if (!hit) { select(null); return; }
  // дверь открывается от нажатия на неё; ящик — от нажатия на его лицо (фасад)
  const pid = hit.object.userData.pid;
  const mv = S.moverOfPart.get(pid);
  if (mv && (mv.type === 'door' || S.parts.get(pid)?.kind === 'facade')) {
    // дверь просто открывается; карточка не нужна — она закрывала бы вид
    setMover(mv, mv.target < 0.5);
    syncOpts();
    select(null);
    const p = S.parts.get(pid);
    toast(`${p.name}${p.size ? ' · ' + p.size.join(' × ') + ' мм' : ''}`, 1800);
    return;
  }
  select(hit);
});
$('#notes .x').onclick = closeSheet;
addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closePops(); clearTag(); select(null);
    if (S.measure) toggleMeasure();
    if (S.notesMode) toggleNotesMode();
    if (S.life) exitLife(true);
  }
});
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  post?.setSize(innerWidth, innerHeight);
  labels.setSize(innerWidth, innerHeight);
});
document.addEventListener('pointerdown', (e) => { if (!e.target.closest('.pop,.tool,.chipbtn')) closePops(); });

// ------------------------------------------------------------------ цикл
const clock = new THREE.Clock();
function loop() {
  requestAnimationFrame(loop);
  const dt = Math.min(clock.getDelta(), 0.05);
  stepMovers(dt);
  stepCamera(dt);
  stepTour(dt);
  if (S.idle && S.root && !S.anim) {
    // лёгкое покачивание до первого касания
    const t = clock.elapsedTime;
    const off = camera.position.clone().sub(controls.target);
    off.applyAxisAngle(new THREE.Vector3(0, 1, 0), Math.sin(t * 0.5) * 0.0012);
    camera.position.copy(controls.target).add(off);
  }
  if (!S.tour) controls.update();
  S.room?.update(camera, S.roomGroup.visible, !!S.life);
  draw();
  watchFps(dt);
  labels.render(scene, camera);
}

// если кадров мало (слабый телефон) — выключаем мягкие тени и снижаем чёткость
let fpsAcc = 0, fpsN = 0;
function watchFps(dt) {
  if (S.lowPower || !S.root || fpsN < 0) return;
  fpsAcc += dt; fpsN++;
  if (fpsN === 90) {
    if (fpsAcc / fpsN > 1 / 26) {
      S.lowPower = true;
      if (post) post.ao.enabled = false;
      renderer.setPixelRatio(Math.min(devicePixelRatio, 1.25));
      renderer.setSize(innerWidth, innerHeight);
      post?.setSize(innerWidth, innerHeight);
    }
    fpsN = -1;
  }
}

window.bvs = { S, camera, controls, scene, setView, setMode, post, renderer }; // для отладки в консоли
load().catch((e) => {
  console.error(e);
  $('#loader p').textContent = 'Не удалось загрузить модель. Обновите страницу.';
});
loop();
