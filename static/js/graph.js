'use strict';

import { KW, ASSET_PATH } from './utils.js';

// ════════════════════════════════════════════════════════════
//  NODE DATA
// ════════════════════════════════════════════════════════════
let nodes = [];                // { id, data, x, y, z, vx, vy, vz, size, ambient }
let activeCount = 0;           // how many nodes are actual data (non-ambient)
const MAX_PARTICLES = 6000;
const AMBIENT_COUNT = 120;     // decorative particles as visual baseline
const ACTIVE_THRESHOLD = 0.3;  // raycaster threshold for click detection

// ════════════════════════════════════════════════════════════
//  THREE.JS STATE
// ════════════════════════════════════════════════════════════
let scene, camera, renderer;
let pointSystem = null;
let pointGeo = null;
let pointMat = null;
let animFrame, sceneLight;

// ════════════════════════════════════════════════════════════
//  MORPH STATE
// ════════════════════════════════════════════════════════════
let morphState = 'orbit';
let orbIntensity = 0;
let orbTargetInt = 0;
let morphTargets = null;
let mx = 0, my = 0;

// ════════════════════════════════════════════════════════════
//  INTERACTION
// ════════════════════════════════════════════════════════════
const raycaster = new THREE.Raycaster();
const mouseVec = new THREE.Vector2();
const raycasterThreshold = 0.4;
let onNodeClickCallback = null;
let hoveredNodeIdx = -1;

// ════════════════════════════════════════════════════════════
//  IMAGE SAMPLING (preserved from original)
// ════════════════════════════════════════════════════════════
let orbCanvas2d, orbCtx2d;

// ════════════════════════════════════════════════════════════
//  BURST PARTICLES
// ════════════════════════════════════════════════════════════
const bCanvas = document.getElementById('burst-canvas');
const bCtx = bCanvas ? bCanvas.getContext('2d') : null;
let burstParticles = [];

// ════════════════════════════════════════════════════════════
//  CALLBACKS
// ════════════════════════════════════════════════════════════
export function onNodeClick(fn) { onNodeClickCallback = fn; }

// ════════════════════════════════════════════════════════════
//  LINK SYSTEM
// ════════════════════════════════════════════════════════════
let links = [];
let linkLines = null;

export function linkPair(sourceIdx, targetIdx) {
  links.push({ source: sourceIdx, target: targetIdx });
  rebuildLinks();
}

function rebuildLinks() {
  if (linkLines) { scene.remove(linkLines); linkLines = null; }
  if (links.length === 0) return;

  const verts = [];
  for (const l of links) {
    const s = nodes[l.source], t = nodes[l.target];
    if (!s || !t) continue;
    verts.push(s.x, s.y, s.z, t.x, t.y, t.z);
  }
  if (verts.length === 0) return;

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  const colors = new Float32Array(verts.length);
  for (let i = 0; i < verts.length / 3; i++) {
    colors[i*3] = 0; colors[i*3+1] = 0.6; colors[i*3+2] = 0.8;
  }
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

  const mat = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 0.25,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });

  linkLines = new THREE.LineSegments(geo, mat);
  scene.add(linkLines);
}

function updateLinkPositions() {
  if (!linkLines || links.length === 0) return;
  const pos = linkLines.geometry.attributes.position.array;
  for (let i = 0; i < links.length; i++) {
    const s = nodes[links[i].source], t = nodes[links[i].target];
    if (s && t) {
      pos[i*6] = s.x; pos[i*6+1] = s.y; pos[i*6+2] = s.z;
      pos[i*6+3] = t.x; pos[i*6+4] = t.y; pos[i*6+5] = t.z;
    }
  }
  linkLines.geometry.attributes.position.needsUpdate = true;
}

// ════════════════════════════════════════════════════════════
//  NODE MANAGEMENT
// ════════════════════════════════════════════════════════════
export function addNode(data) {
  const id = nodes.length;
  const ambient = data === null;
  const node = {
    id,
    data,
    x: (Math.random() - 0.5) * 2,
    y: (Math.random() - 0.5) * 2,
    z: (Math.random() - 0.5) * 2,
    vx: 0, vy: 0, vz: 0,
    size: ambient
      ? 0.03 + Math.random() * 0.04
      : 0.05 + Math.random() * 0.08,
    ambient,
  };
  nodes.push(node);
  if (!ambient) activeCount++;
  rebuildParticleSystem();
  return node;
}

export function addNodes(dataArray) {
  dataArray.forEach(d => addNode(d));
}

export function getNodeCount() {
  return activeCount;
}

export function getTotalCount() {
  return nodes.length;
}

export function addNodeAnimated(data) {
  const node = {
    id: nodes.length,
    data,
    x: 0, y: 0, z: 0,
    vx: 0, vy: 0, vz: 0,
    size: 0.06 + Math.random() * 0.06,
    ambient: false,
  };
  nodes.push(node);
  activeCount++;
  rebuildParticleSystem();

  const targetX = (Math.random() - 0.5) * 8;
  const targetY = (Math.random() - 0.5) * 6;
  const targetZ = (Math.random() - 0.5) * 4;

  const p = { t: 0 };
  gsap.to(p, {
    t: 1, duration: 1.2, ease: 'power3.out',
    onUpdate: () => {
      node.x = targetX * p.t;
      node.y = targetY * p.t;
      node.z = targetZ * p.t;
    }
  });

  return node;
}

export function clearDataNodes() {
  nodes = nodes.filter(n => n.ambient);
  activeCount = 0;
  links = [];
  linkLines = null;
  rebuildParticleSystem();
}

// ════════════════════════════════════════════════════════════
//  PARTICLE SYSTEM BUILDER
// ════════════════════════════════════════════════════════════
function rebuildParticleSystem() {
  const total = Math.min(Math.max(nodes.length, AMBIENT_COUNT), MAX_PARTICLES);

  // Add ambient nodes if needed
  while (nodes.length < total) {
    nodes.push({
      id: nodes.length,
      data: null,
      x: (Math.random() - 0.5) * 8,
      y: (Math.random() - 0.5) * 8,
      z: (Math.random() - 0.5) * 4,
      vx: 0, vy: 0, vz: 0,
      size: 0.03 + Math.random() * 0.04,
      ambient: true,
    });
  }

  const count = nodes.length;

  if (!pointGeo) {
    // Pre-allocate with MAX_PARTICLES capacity
    createPointSystem();
  }

  // Update buffer data for active range
  const pos = pointGeo.attributes.position.array;
  const col = pointGeo.attributes.color.array;
  const sizes = pointGeo.attributes.size.array;

  for (let i = 0; i < count; i++) {
    const n = nodes[i];
    pos[i*3] = n.x; pos[i*3+1] = n.y; pos[i*3+2] = n.z;

    if (n.ambient) {
      col[i*3] = 0; col[i*3+1] = 0.5 + Math.random()*0.2; col[i*3+2] = 0.6 + Math.random()*0.2;
    } else {
      col[i*3] = 0.2; col[i*3+1] = 0.8 + Math.random()*0.2; col[i*3+2] = 0.9 + Math.random()*0.1;
    }

    sizes[i] = n.size;
  }

  pointGeo.attributes.position.needsUpdate = true;
  pointGeo.attributes.color.needsUpdate = true;
  pointGeo.attributes.size.needsUpdate = true;
  pointGeo.setDrawRange(0, count);
}

function createPointSystem() {
  if (pointSystem) scene.remove(pointSystem);

  const cap = MAX_PARTICLES;
  const pos = new Float32Array(cap * 3);
  const col = new Float32Array(cap * 3);
  const sizes = new Float32Array(cap);

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
  geo.setDrawRange(0, 0);

  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uPixelRatio: { value: Math.min(devicePixelRatio, 2) },
      uOpacity: { value: 0.75 },
    },
    vertexShader: `
      attribute float size;
      attribute vec3 color;
      varying vec3 vColor;
      uniform float uPixelRatio;
      uniform float uOpacity;
      void main() {
        vColor = color;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = size * uPixelRatio * (280.0 / -mvPosition.z);
        gl_PointSize = clamp(gl_PointSize, 0.5, 24.0);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      void main() {
        vec2 center = gl_PointCoord - vec2(0.5);
        float d = length(center);
        if (d > 0.5) discard;
        float alpha = smoothstep(0.5, 0.0, d);
        alpha *= 0.85;
        gl_FragColor = vec4(vColor, alpha);
      }
    `,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  const pts = new THREE.Points(geo, mat);
  scene.add(pts);
  pointSystem = pts;
  pointGeo = geo;
  pointMat = mat;
}

// ════════════════════════════════════════════════════════════
//  FORCE SIMULATION (simple 3D force-directed layout)
// ════════════════════════════════════════════════════════════
let simRunning = true;
const REPULSION_STR = 40;
const CENTER_STR = 0.008;
const DAMPING = 0.94;
const MAX_VEL = 0.5;

function tickForces() {
  if (!simRunning || nodes.length < 2) return;

  const active = nodes.filter(n => !n.ambient);
  if (active.length < 2) return;

  // Repulsion between active nodes
  for (let i = 0; i < active.length; i++) {
    for (let j = i + 1; j < active.length; j++) {
      const a = active[i], b = active[j];
      const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
      const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) || 0.01;
      const force = REPULSION_STR / (dist * dist + 0.1);
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      const fz = (dz / dist) * force;
      a.vx -= fx; a.vy -= fy; a.vz -= fz;
      b.vx += fx; b.vy += fy; b.vz += fz;
    }
  }

  // Center gravity on all nodes (including ambient)
  for (const n of nodes) {
    n.vx -= n.x * CENTER_STR;
    n.vy -= n.y * CENTER_STR;
    n.vz -= n.z * CENTER_STR;

    n.vx *= DAMPING;
    n.vy *= DAMPING;
    n.vz *= DAMPING;

    const v = Math.sqrt(n.vx*n.vx + n.vy*n.vy + n.vz*n.vz);
    if (v > MAX_VEL) {
      n.vx = (n.vx / v) * MAX_VEL;
      n.vy = (n.vy / v) * MAX_VEL;
      n.vz = (n.vz / v) * MAX_VEL;
    }

    n.x += n.vx;
    n.y += n.vy;
    n.z += n.vz;
  }
}

// ════════════════════════════════════════════════════════════
//  THREE.JS SETUP
// ════════════════════════════════════════════════════════════
export function initGraph() {
  const canvas = document.getElementById('three-canvas');
  const area   = document.getElementById('orb-area');
  if (!canvas || !area) return;

  scene    = new THREE.Scene();
  camera   = new THREE.PerspectiveCamera(60, area.clientWidth / area.clientHeight, 0.1, 200);
  camera.position.z = 14;

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(area.clientWidth, area.clientHeight);
  renderer.setClearColor(0x000000, 0);

  scene.add(new THREE.AmbientLight(0x0a1a2e, 3));
  sceneLight = new THREE.PointLight(0x00f5ff, 2, 30);
  sceneLight.position.set(0, 5, 5);
  scene.add(sceneLight);

  orbCanvas2d = document.createElement('canvas');
  orbCtx2d    = orbCanvas2d.getContext('2d');

  // Seed ambient nodes
  for (let i = 0; i < AMBIENT_COUNT; i++) {
    addNode(null);
  }

  raycaster.params.Points = { threshold: ACTIVE_THRESHOLD };

  window.addEventListener('resize', onResizeGraph);
  window.addEventListener('mousemove', onMouseMove);

  const threeCanvas = renderer.domElement;
  threeCanvas.addEventListener('click', onCanvasClick);
  threeCanvas.style.cursor = 'pointer';

  // ── Animation Loop ──
  let t = 0;
  function loop() {
    animFrame = requestAnimationFrame(loop);
    t += 0.012;

    orbIntensity += (orbTargetInt - orbIntensity) * 0.04;

    // Apply morph targets if set (image morph)
    updateMorph();

    // Run force simulation
    if (morphState === 'orbit') tickForces();

    // Update geometry positions from node data
    if (pointGeo) {
      const pos = pointGeo.attributes.position.array;
      for (let i = 0; i < nodes.length; i++) {
        pos[i*3] = nodes[i].x;
        pos[i*3+1] = nodes[i].y;
        pos[i*3+2] = nodes[i].z;
      }
      pointGeo.attributes.position.needsUpdate = true;

      // Update colors based on intensity
      if (morphState !== 'image') {
        const col = pointGeo.attributes.color.array;
        for (let i = 0; i < nodes.length; i++) {
          if (nodes[i].ambient) {
            col[i*3] = 0;
            col[i*3+1] = 0.5 + orbIntensity * 0.4;
            col[i*3+2] = 0.6 + orbIntensity * 0.3;
          } else {
            col[i*3] = orbIntensity * 0.5;
            col[i*3+1] = 0.65 + orbIntensity * 0.35 + 0.15 * Math.sin(t * 2 + i * 0.1);
            col[i*3+2] = 0.75 + orbIntensity * 0.25;
          }
        }
        pointGeo.attributes.color.needsUpdate = true;
      }
    }

    // Opacity based on state
    if (pointMat) {
      const breathe = 1 + 0.06 * Math.sin(t * (1 + orbIntensity * 3));
      let op = (0.6 + orbIntensity * 0.4) * breathe;
      if (morphState === 'think') op = 0.4 + 0.6 * Math.abs(Math.sin(t * 1.5));
      pointMat.uniforms.uOpacity.value = op;
    }

    sceneLight.intensity = 1 + orbIntensity * 4;

    camera.position.x += (mx * 2 - camera.position.x) * 0.025;
    camera.position.y += (my * 1.5 - camera.position.y) * 0.025;
    camera.lookAt(0, 0, 0);

    // Update size for ambient particles with sine wave
    if (pointGeo && morphState === 'orbit') {
      const sizes = pointGeo.attributes.size.array;
      for (let i = 0; i < nodes.length; i++) {
        if (nodes[i].ambient) {
          sizes[i] = nodes[i].size * (1 + 0.2 * Math.sin(t * 0.5 + i * 0.3));
        }
      }
      pointGeo.attributes.size.needsUpdate = true;
    }

    updateLinkPositions();

    renderer.render(scene, camera);
  }
  loop();

  initBurst();
}

// ════════════════════════════════════════════════════════════
//  RESIZE
// ════════════════════════════════════════════════════════════
function onResizeGraph() {
  const area = document.getElementById('orb-area');
  if (!camera || !renderer || !area) return;
  camera.aspect = area.clientWidth / area.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(area.clientWidth, area.clientHeight);
}

// ════════════════════════════════════════════════════════════
//  MOUSE & CLICK
// ════════════════════════════════════════════════════════════
function onMouseMove(e) {
  mx = (e.clientX / innerWidth)  * 2 - 1;
  my = -(e.clientY / innerHeight) * 2 + 1;
}

function onCanvasClick(e) {
  if (!pointSystem || !renderer) return;

  const rect = renderer.domElement.getBoundingClientRect();
  mouseVec.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  mouseVec.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

  raycaster.setFromCamera(mouseVec, camera);

  const intersects = raycaster.intersectObject(pointSystem);
  if (intersects.length > 0) {
    const idx = intersects[0].index;
    if (idx !== undefined && idx < nodes.length && !nodes[idx].ambient) {
      if (onNodeClickCallback) onNodeClickCallback(nodes[idx].data, idx);
    }
  }
}

// ════════════════════════════════════════════════════════════
//  ORB STATE
// ════════════════════════════════════════════════════════════
export function setOrbThinking(on) {
  orbTargetInt = on ? 0.85 : 0.1;
  const ring = document.getElementById('status-ring');
  const txt = document.getElementById('status-txt');
  const lbl = document.getElementById('orb-label');
  if (ring) ring.className = 'status-ring' + (on ? ' thinking' : '');
  if (txt) txt.textContent = on ? 'PROCESSING' : 'ONLINE';
  if (lbl) lbl.textContent = on ? 'DEEP REASONING' : 'NEURAL CORE';
  if (on) morphState = 'think'; else if (morphState === 'think') morphState = 'orbit';
}

export function setOrbIdle() {
  orbTargetInt = 0.05;
  morphState = 'orbit';
  const lbl = document.getElementById('orb-label');
  if (lbl) lbl.textContent = 'NEURAL CORE';
}

export function setOrbTargetIntensity(val) {
  orbTargetInt = val;
}

// ════════════════════════════════════════════════════════════
//  MORPH UPDATER
// ════════════════════════════════════════════════════════════
function updateMorph() {
  if (morphState === 'orbit') {
    for (const n of nodes) {
      n.vx += Math.sin(Date.now() * 0.0005 + n.id * 0.1) * 0.0001;
    }
  }
}

// ════════════════════════════════════════════════════════════
//  IMAGE SAMPLING (preserved from original)
// ════════════════════════════════════════════════════════════
function sampleImage(img) {
  const res = 140;
  orbCanvas2d.width = orbCanvas2d.height = res;

  orbCtx2d.fillStyle = '#000';
  orbCtx2d.fillRect(0, 0, res, res);
  orbCtx2d.drawImage(img, 0, 0, res, res);
  const d0 = orbCtx2d.getImageData(0, 0, res, res).data;
  const corners = [
    (d0[0]+d0[1]+d0[2])/3,
    (d0[(res-1)*4]+d0[(res-1)*4+1]+d0[(res-1)*4+2])/3,
    (d0[(res*(res-1))*4]+d0[(res*(res-1))*4+1]+d0[(res*(res-1))*4+2])/3,
    (d0[(res*res-1)*4]+d0[(res*res-1)*4+1]+d0[(res*res-1)*4+2])/3,
  ];
  const avgCorner = corners.reduce((a,b)=>a+b,0)/4;
  const darkBg = avgCorner < 60;

  orbCtx2d.clearRect(0, 0, res, res);
  orbCtx2d.drawImage(img, 0, 0, res, res);
  const dA = orbCtx2d.getImageData(0, 0, res, res).data;
  const pixels = [];

  for (let y = 0; y < res; y++) {
    for (let x = 0; x < res; x++) {
      const i = (y*res+x)*4;
      const r=dA[i], g=dA[i+1], b=dA[i+2], a=dA[i+3];
      const lum = (r*0.299 + g*0.587 + b*0.114);

      let shape = false;
      if (darkBg) {
        if (a > 30 && lum > 40) shape = true;
      } else {
        if (a > 200) shape = lum < 200;
        else if (a > 60) shape = true;
      }
      if (shape) {
        pixels.push({ x, y, r: r/255, g: g/255, b: b/255, lum: lum/255 });
      }
    }
  }
  return { pixels, res };
}

export function morphParticlesToImage(keyword) {
  const fn = KW[keyword];
  if (!fn) return;

  const exts = ['png','jpg','jpeg','webp'];
  let ei = 0;

  function tryExt() {
    if (ei >= exts.length) return;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const { pixels, res } = sampleImage(img);
      if (pixels.length < 50) { ei++; tryExt(); return; }

      morphState = 'image';
      morphTargets = [];

      const count = nodes.length;
      for (let i = 0; i < count; i++) {
        if (i < count * 0.85) {
          const p = pixels[Math.floor(Math.random() * pixels.length)];
          morphTargets.push({
            x: ((p.x/res) - 0.5) * 11,
            y: -((p.y/res) - 0.5) * 11,
            z: (p.lum - 0.5) * 1.8 + (Math.random()-0.5)*0.6,
          });
        } else {
          const angle = Math.random()*Math.PI*2;
          const r = 5.5 + Math.random()*3.0;
          morphTargets.push({
            x: Math.cos(angle)*r,
            y: (Math.random()-0.5)*8,
            z: Math.sin(angle)*r*0.4,
          });
        }
      }

      // Animate
      const proxy = { t: 0 };
      const startPos = nodes.map(n => ({ x: n.x, y: n.y, z: n.z }));
      const startTime = Date.now();
      const duration = 1800;

      function animateMorph() {
        const elapsed = Date.now() - startTime;
        const t = Math.min(elapsed / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3);

        for (let i = 0; i < nodes.length; i++) {
          nodes[i].x = startPos[i].x + (morphTargets[i].x - startPos[i].x) * ease;
          nodes[i].y = startPos[i].y + (morphTargets[i].y - startPos[i].y) * ease;
          nodes[i].z = startPos[i].z + (morphTargets[i].z - startPos[i].z) * ease;
          nodes[i].vx = 0; nodes[i].vy = 0; nodes[i].vz = 0;
        }

        if (pointGeo) {
          const col = pointGeo.attributes.color.array;
          for (let i = 0; i < nodes.length; i++) {
            if (i < count * 0.85) {
              const p = pixels[Math.floor(Math.random() * pixels.length)];
              const tint = 0.12;
              col[i*3]   = (col[i*3]   + p.r*(1-tint)) * 0.5;
              col[i*3+1] = (col[i*3+1] + p.g*(1-tint) + 0.9*tint) * 0.5;
              col[i*3+2] = (col[i*3+2] + p.b*(1-tint) + 1.0*tint) * 0.5;
            } else {
              col[i*3]   = 0;
              col[i*3+1] = 0.7 + Math.random()*0.3;
              col[i*3+2] = 0.8 + Math.random()*0.2;
            }
          }
          pointGeo.attributes.color.needsUpdate = true;
        }

        if (t < 1) requestAnimationFrame(animateMorph);
        else morphTargets = null;
      }
      animateMorph();
    };
    img.onerror = () => { ei++; tryExt(); };
    img.src = ASSET_PATH + fn + '.' + exts[ei];
  }
  tryExt();
}

export function morphParticlesToOrbit() {
  morphState = 'orbit';
  morphTargets = null;

  const proxy = { t: 0 };
  const startPos = nodes.map(n => ({ x: n.x, y: n.y, z: n.z }));
  const dest = nodes.map(() => {
    const onShell = Math.random() < 0.70;
    const phi = Math.acos(2*Math.random()-1), theta = Math.random()*Math.PI*2;
    const r = onShell ? 2.3 + Math.random()*0.5 : 3.5 + Math.random()*3.5;
    return {
      x: r*Math.sin(phi)*Math.cos(theta),
      y: r*Math.sin(phi)*Math.sin(theta),
      z: r*Math.cos(phi),
    };
  });

  const startTime = Date.now();
  const duration = 1400;

  function animate() {
    const elapsed = Date.now() - startTime;
    const t = Math.min(elapsed / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3);

    for (let i = 0; i < nodes.length; i++) {
      nodes[i].x = startPos[i].x + (dest[i].x - startPos[i].x) * ease;
      nodes[i].y = startPos[i].y + (dest[i].y - startPos[i].y) * ease;
      nodes[i].z = startPos[i].z + (dest[i].z - startPos[i].z) * ease;
    }

    if (pointGeo) {
      const col = pointGeo.attributes.color.array;
      for (let i = 0; i < nodes.length; i++) {
        col[i*3]=0; col[i*3+1]=0.75+0.2*t; col[i*3+2]=0.9+0.1*t;
      }
      pointGeo.attributes.color.needsUpdate = true;
    }

    if (t < 1) requestAnimationFrame(animate);
  }
  animate();
}

export function morphParticlesToThink() {
  morphState = 'think';
  morphTargets = null;

  const startPos = nodes.map(n => ({ x: n.x, y: n.y, z: n.z }));
  const dest = nodes.map(() => {
    const onCore = Math.random() < 0.65;
    const a = Math.random() * Math.PI * 2;
    const r = onCore ? 1.5 + Math.random()*1.5 : 2.5 + Math.random()*1.5;
    return {
      x: Math.cos(a) * r,
      y: (Math.random()-0.5) * (onCore ? 0.8 : 2.0),
      z: Math.sin(a) * r,
    };
  });

  const startTime = Date.now();
  const duration = 650;

  function animate() {
    const elapsed = Date.now() - startTime;
    const t = Math.min(elapsed / duration, 1);
    const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;

    for (let i = 0; i < nodes.length; i++) {
      nodes[i].x = startPos[i].x + (dest[i].x - startPos[i].x) * ease;
      nodes[i].y = startPos[i].y + (dest[i].y - startPos[i].y) * ease;
      nodes[i].z = startPos[i].z + (dest[i].z - startPos[i].z) * ease;
    }

    if (pointGeo) {
      const col = pointGeo.attributes.color.array;
      for (let i = 0; i < nodes.length; i++) {
        col[i*3]=0; col[i*3+1]=0.9; col[i*3+2]=1.0;
      }
      pointGeo.attributes.color.needsUpdate = true;
    }

    if (t < 1) requestAnimationFrame(animate);
  }
  animate();
}

// ════════════════════════════════════════════════════════════
//  BURST PARTICLES (preserved from original)
// ════════════════════════════════════════════════════════════
function initBurst() {
  if (!bCanvas || !bCtx) return;
  resizeBurst();
  window.addEventListener('resize', resizeBurst);

  function animateBurst() {
    requestAnimationFrame(animateBurst);
    bCtx.clearRect(0, 0, bCanvas.width, bCanvas.height);
    burstParticles = burstParticles.filter(p => p.life > 0);
    for (const p of burstParticles) {
      p.x    += p.vx;
      p.y    += p.vy;
      p.vx   *= 0.94;
      p.vy   *= 0.94;
      p.life -= p.decay;
      bCtx.beginPath();
      bCtx.arc(p.x, p.y, p.size, 0, Math.PI*2);
      bCtx.fillStyle = `rgba(${p.color},${p.life})`;
      bCtx.fill();
    }
  }
  animateBurst();
}

function resizeBurst() {
  if (!bCanvas) return;
  bCanvas.width  = innerWidth;
  bCanvas.height = innerHeight;
}

export function fireBurst(targetEl) {
  if (!targetEl || !bCanvas) return;
  const orbArea = document.getElementById('orb-area');
  if (!orbArea) return;
  const oRect   = orbArea.getBoundingClientRect();
  const tRect   = targetEl.getBoundingClientRect();

  const sx = oRect.left + oRect.width  * 0.5;
  const sy = oRect.top  + oRect.height * 0.5;
  const tx = tRect.left + tRect.width  * 0.5;
  const ty = tRect.top  + tRect.height * 0.5;

  for (let i = 0; i < 40; i++) {
    const angle = Math.atan2(ty-sy, tx-sx) + (Math.random()-0.5)*0.6;
    const speed = 4 + Math.random()*8;
    burstParticles.push({
      x:sx, y:sy,
      vx: Math.cos(angle)*speed,
      vy: Math.sin(angle)*speed,
      life:1.0,
      decay: 0.018 + Math.random()*0.02,
      size: 1.5 + Math.random()*2.5,
      color: Math.random() > 0.5 ? '0,245,255' : '0,255,157',
    });
  }
}
