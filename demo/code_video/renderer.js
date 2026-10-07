/*
 * CodeVideo — a video rendered entirely by code.
 *
 * Every pixel you see is a pure function of time: renderFrame(ctx, t).
 * No video file, no trained pixels, no randomness at draw time —
 * the same t always produces the exact same frame. This is what makes
 * the output deterministic and therefore exportable as a real video:
 *   - live preview:  requestAnimationFrame loop in index.html
 *   - webm export:   canvas.captureStream() + MediaRecorder (index.html)
 *   - mp4 export:    headless Chrome screenshots at fixed t + ffmpeg (export_mp4.sh)
 */
(function (global) {
  'use strict';

  var W = 1280;
  var H = 720;
  var FPS = 30;
  var DURATION = 16; // seconds
  var TOTAL_FRAMES = FPS * DURATION;

  var CYAN = '#38e1ff';
  var MAGENTA = '#b44cff';
  var AMBER = '#ffc555';

  // ------------------------------------------------------------------
  // Deterministic helpers
  // ------------------------------------------------------------------

  // Small fast seeded PRNG — same seed => same "random" sequence, every run.
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function easeOutCubic(p) { return 1 - Math.pow(1 - p, 3); }
  function easeInOutCubic(p) {
    return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
  }

  // Scene visibility window: eased 0->1->0 ramps of `rIn`/`rOut` seconds.
  // Overlapping windows between neighbours = automatic crossfades.
  function sceneAlpha(t, a, b, rIn, rOut) {
    var fadeIn = rIn <= 0 ? 1 : clamp01((t - a) / rIn);
    var fadeOut = clamp01((b - t) / rOut);
    return Math.min(fadeIn, fadeOut);
  }

  function pad(n, width) {
    var s = String(Math.max(0, Math.floor(n)));
    while (s.length < width) s = '0' + s;
    return s;
  }

  // ------------------------------------------------------------------
  // Precomputed content (built once with the seeded PRNG — deterministic)
  // ------------------------------------------------------------------

  // Starfield for the intro.
  var STARS = (function () {
    var rnd = mulberry32(1337);
    var stars = [];
    for (var i = 0; i < 150; i++) {
      stars.push({
        x: rnd() * W,
        y: rnd() * H,
        r: 0.6 + rnd() * 1.6,
        tw: 0.5 + rnd() * 2.5,      // twinkle speed
        ph: rnd() * Math.PI * 2,    // twinkle phase
        drift: 4 + rnd() * 14       // px/s upward drift
      });
    }
    return stars;
  })();

  // Floating orbs for the waves scene.
  var ORBS = (function () {
    var rnd = mulberry32(4242);
    var orbs = [];
    for (var i = 0; i < 14; i++) {
      orbs.push({
        x: rnd() * W,
        speed: 26 + rnd() * 46,
        radius: 24 + rnd() * 70,
        ph: rnd() * Math.PI * 2,
        off: rnd() * (H + 160),
        tint: rnd()
      });
    }
    return orbs;
  })();

  // Wireframe cube vertices for the tech scene.
  var CUBE = (function () {
    var s = 105;
    var v = [];
    [-1, 1].forEach(function (x) {
      [-1, 1].forEach(function (y) {
        [-1, 1].forEach(function (z) {
          v.push([x * s, y * s, z * s]);
        });
      });
    });
    var edges = [];
    for (var i = 0; i < 8; i++) {
      for (var j = i + 1; j < 8; j++) {
        // edge if vertices differ in exactly one coordinate
        var diff = 0;
        for (var k = 0; k < 3; k++) if (v[i][k] !== v[j][k]) diff++;
        if (diff === 1) edges.push([i, j]);
      }
    }
    return { v: v, e: edges };
  })();

  // Grain tile: one small noise canvas, redrawn at a per-frame offset.
  var GRAIN = (function () {
    if (typeof document === 'undefined') return null;
    var c = document.createElement('canvas');
    c.width = 160; c.height = 160;
    var g = c.getContext('2d');
    var img = g.createImageData(160, 160);
    var rnd = mulberry32(9001);
    for (var i = 0; i < img.data.length; i += 4) {
      var v = Math.floor(rnd() * 255);
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 10; // very subtle
    }
    g.putImageData(img, 0, 0);
    return c;
  })();

  // ------------------------------------------------------------------
  // Scene 1 — Intro (0.0 -> 4.1): starfield + kinetic title + typewriter
  // ------------------------------------------------------------------

  var TITLE = 'JARVIS';

  function drawIntro(ctx, t, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha;

    // deep-space backdrop
    var bg = ctx.createRadialGradient(W / 2, H * 0.42, 60, W / 2, H * 0.42, 620);
    bg.addColorStop(0, '#0b1226');
    bg.addColorStop(1, '#04060d');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    // drifting, twinkling stars
    for (var i = 0; i < STARS.length; i++) {
      var s = STARS[i];
      var y = (s.y - t * s.drift) % H;
      if (y < 0) y += H;
      var tw = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * s.tw + s.ph));
      ctx.globalAlpha = alpha * tw * 0.9;
      ctx.fillStyle = i % 9 === 0 ? CYAN : '#cfe8ff';
      ctx.beginPath();
      ctx.arc(s.x, y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = alpha;

    // kinetic title — letters fly in staggered, tracking tightens
    ctx.textBaseline = 'alphabetic';
    var track0 = 64;                       // extra letter-spacing at t=0
    var trackP = easeOutCubic(clamp01((t - 0.25) / 1.9));
    var track = (1 - trackP) * track0;

    var fs = 148;
    ctx.font = '900 ' + fs + 'px "Segoe UI", Arial, sans-serif';
    var widths = [];
    var total = -track;
    for (var n = 0; n < TITLE.length; n++) {
      var w = ctx.measureText(TITLE[n]).width;
      widths.push(w);
      total += w + track;
    }
    var x = (W - total) / 2;
    var baseY = H * 0.46;

    for (var n2 = 0; n2 < TITLE.length; n2++) {
      var aL = easeOutCubic(clamp01((t - 0.30 - n2 * 0.22) / 0.55));
      if (aL > 0.001) {
        var dy = (1 - aL) * 46;
        ctx.save();
        ctx.globalAlpha = alpha * aL;
        ctx.shadowColor = CYAN;
        ctx.shadowBlur = 26 * aL;
        ctx.fillStyle = '#eef7ff';
        ctx.fillText(TITLE[n2], x, baseY + dy);
        ctx.restore();
      }
      x += widths[n2] + track;
    }

    // thin rule under the title, sweeping outwards
    var ruleP = easeInOutCubic(clamp01((t - 1.35) / 0.8));
    if (ruleP > 0.001) {
      var rw = (W * 0.44) * ruleP;
      var grad = ctx.createLinearGradient(W / 2 - rw / 2, 0, W / 2 + rw / 2, 0);
      grad.addColorStop(0, 'rgba(56,225,255,0)');
      grad.addColorStop(0.5, CYAN);
      grad.addColorStop(1, 'rgba(56,225,255,0)');
      ctx.strokeStyle = grad;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(W / 2 - rw / 2, baseY + 44);
      ctx.lineTo(W / 2 + rw / 2, baseY + 44);
      ctx.stroke();
    }

    // typewriter subtitle with deterministic blinking caret
    var SUB = 'RENDERED ENTIRELY BY CODE';
    var chars = Math.floor(clamp01((t - 1.7) / (SUB.length * 0.045)) * SUB.length);
    var shown = SUB.slice(0, chars);
    ctx.font = '600 26px Consolas, "Courier New", monospace';
    ctx.textAlign = 'center';
    ctx.fillStyle = 'rgba(160, 210, 235, 0.95)';
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.fillText(shown + ((t * 2.4) % 1 < 0.5 ? '\u258C' : ' '), W / 2, baseY + 108);

    ctx.textAlign = 'left';
    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Scene 2 — Waves (3.6 -> 8.7): aurora ribbons + orbs
  // ------------------------------------------------------------------

  function drawWaves(ctx, t, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha;

    var bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#04060d');
    bg.addColorStop(0.55, '#071022');
    bg.addColorStop(1, '#04060d');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    // soft drifting orbs (drawn under the ribbons)
    for (var o = 0; o < ORBS.length; o++) {
      var b = ORBS[o];
      var oy = (H + 160) - ((t * b.speed + b.off) % (H + 160));
      var ox = b.x + 34 * Math.sin(t * 0.6 + b.ph);
      var col = b.tint < 0.5 ? CYAN : MAGENTA;
      var rg = ctx.createRadialGradient(ox, oy, 2, ox, oy, b.radius);
      rg.addColorStop(0, col + '26');
      rg.addColorStop(1, col + '00');
      ctx.fillStyle = rg;
      ctx.beginPath();
      ctx.arc(ox, oy, b.radius, 0, Math.PI * 2);
      ctx.fill();
    }

    // aurora ribbons — layered sine composites
    for (var L = 0; L < 6; L++) {
      var baseY = H * 0.52 + (L - 2.5) * 34 + 18 * Math.sin(t * 0.5 + L);
      var sp = 0.65 + L * 0.13;
      ctx.beginPath();
      for (var px = -40; px <= W + 40; px += 14) {
        var py = baseY
          + 58 * Math.sin(px * 0.006 + t * sp + L * 1.7)
          + 26 * Math.sin(px * 0.0135 - t * 0.9 + L * 0.8);
        if (px === -40) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      var mix = L / 5;
      var r = Math.round(56 + (180 - 56) * mix);
      var g = Math.round(225 - (76 - 225) * mix * 0.2);
      var bl = Math.round(255 - (255 - 255) * mix);
      ctx.strokeStyle = 'rgba(' + r + ',' + g + ',' + bl + ',' + (0.16 + 0.10 * Math.sin(t * 1.3 + L)) + ')';
      ctx.lineWidth = 2.4;
      ctx.shadowColor = mix < 0.5 ? CYAN : MAGENTA;
      ctx.shadowBlur = 16;
      ctx.stroke();
    }
    ctx.shadowBlur = 0;

    // caption chip
    var capP = easeOutCubic(clamp01((t - 4.6) / 0.7));
    if (capP > 0.001) {
      ctx.globalAlpha = alpha * capP;
      ctx.font = '700 22px "Segoe UI", Arial, sans-serif';
      var label = 'M O T I O N   G R A P H I C S';
      var lw = ctx.measureText(label).width;
      var cx = 150, cy = H * 0.8;
      ctx.fillStyle = 'rgba(160,210,235,0.92)';
      ctx.fillText(label, cx, cy);
      var uw = lw * capP;
      ctx.fillStyle = AMBER;
      ctx.fillRect(cx, cy + 10, uw, 2);
    }

    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Scene 3 — Tech (8.2 -> 13.3): HUD rings + wireframe cube + readouts
  // ------------------------------------------------------------------

  function drawTech(ctx, t, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha;

    ctx.fillStyle = '#04070f';
    ctx.fillRect(0, 0, W, H);

    var cx = W / 2, cy = H / 2;

    // rotating dashed rings
    var rings = [
      { r: 148, dash: [46, 22], dir: 1, speed: 0.5, w: 2 },
      { r: 186, dash: [16, 34], dir: -1, speed: 0.32, w: 1.4 },
      { r: 224, dash: [90, 60], dir: 1, speed: 0.2, w: 1 }
    ];
    for (var i = 0; i < rings.length; i++) {
      var R = rings[i];
      ctx.beginPath();
      ctx.setLineDash(R.dash);
      ctx.lineDashOffset = R.dir * t * R.speed * 60;
      ctx.strokeStyle = 'rgba(56,225,255,0.5)';
      ctx.lineWidth = R.w;
      ctx.shadowColor = CYAN;
      ctx.shadowBlur = 10;
      ctx.arc(cx, cy, R.r, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.shadowBlur = 0;

    // tick marks
    ctx.strokeStyle = 'rgba(56,225,255,0.35)';
    ctx.lineWidth = 1;
    for (var k = 0; k < 60; k++) {
      var ang = (k / 60) * Math.PI * 2 + t * 0.05;
      var long = k % 5 === 0;
      var r1 = 148, r2 = long ? 136 : 142;
      ctx.beginPath();
      ctx.moveTo(cx + r1 * Math.cos(ang), cy + r1 * Math.sin(ang));
      ctx.lineTo(cx + r2 * Math.cos(ang), cy + r2 * Math.sin(ang));
      ctx.stroke();
    }

    // wireframe cube, rotated + perspective projected by hand
    var ry = t * 0.85, rx = t * 0.55;
    var cA = Math.cos(ry), sA = Math.sin(ry);
    var cB = Math.cos(rx), sB = Math.sin(rx);
    var proj = [];
    for (var v = 0; v < CUBE.v.length; v++) {
      var p = CUBE.v[v];
      var X = p[0] * cA + p[2] * sA;
      var Z = -p[0] * sA + p[2] * cA;
      var Y = p[1] * cB - Z * sB;
      Z = p[1] * sB + Z * cB;
      var d = 3.4;                       // camera distance
      var sc = 300 / (Z + d);
      proj.push([cx + X * sc, cy + Y * sc]);
    }
    ctx.strokeStyle = CYAN;
    ctx.lineWidth = 1.6;
    ctx.shadowColor = CYAN;
    ctx.shadowBlur = 12;
    for (var e = 0; e < CUBE.e.length; e++) {
      var a = proj[CUBE.e[e][0]], b2 = proj[CUBE.e[e][1]];
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b2[0], b2[1]);
      ctx.stroke();
    }
    ctx.fillStyle = '#eef7ff';
    for (var v2 = 0; v2 < proj.length; v2++) {
      ctx.beginPath();
      ctx.arc(proj[v2][0], proj[v2][1], 2.4, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.shadowBlur = 0;

    // scan line sweeping down
    var sy = ((t * 0.35) % 1) * H;
    var sg = ctx.createLinearGradient(0, sy - 60, 0, sy + 4);
    sg.addColorStop(0, 'rgba(56,225,255,0)');
    sg.addColorStop(1, 'rgba(56,225,255,0.10)');
    ctx.fillStyle = sg;
    ctx.fillRect(0, sy - 60, W, 64);
    ctx.fillStyle = 'rgba(56,225,255,0.28)';
    ctx.fillRect(0, sy, W, 2);

    // corner brackets
    ctx.strokeStyle = 'rgba(56,225,255,0.55)';
    ctx.lineWidth = 2;
    var m = 34, len = 26;
    [[m, m, 1, 1], [W - m, m, -1, 1], [m, H - m, 1, -1], [W - m, H - m, -1, -1]]
      .forEach(function (c) {
        ctx.beginPath();
        ctx.moveTo(c[0] + len * c[2], c[1]);
        ctx.lineTo(c[0], c[1]);
        ctx.lineTo(c[0], c[1] + len * c[3]);
        ctx.stroke();
      });

    // live readouts — the video narrates its own render
    var frame = Math.round(t * FPS);
    ctx.font = '600 17px Consolas, "Courier New", monospace';
    ctx.fillStyle = 'rgba(160,210,235,0.9)';
    ctx.fillText('SYS.RENDERER v5.5', 58, 66);
    ctx.fillText('t = ' + t.toFixed(3) + 's', 58, 92);
    ctx.fillText('frame ' + pad(frame, 4) + ' / ' + pad(TOTAL_FRAMES, 4), 58, 118);
    ctx.fillText('fps 30  (deterministic)', 58, 144);
    ctx.textAlign = 'right';
    ctx.fillText('geometry: pure math', W - 58, 66);
    ctx.fillText('pixels:  ' + (W * H).toLocaleString(), W - 58, 92);
    ctx.fillText('drawn by: renderFrame(ctx, t)', W - 58, 118);
    ctx.textAlign = 'left';

    // caption
    ctx.font = '700 21px "Segoe UI", Arial, sans-serif';
    ctx.fillStyle = 'rgba(160,210,235,0.92)';
    ctx.textAlign = 'center';
    ctx.fillText('E V E R Y   P I X E L   C O M P U T E D', cx, H - 74);
    ctx.textAlign = 'left';

    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Scene 4 — Outro (12.8 -> 16.0): end card, fade to black
  // ------------------------------------------------------------------

  function drawOutro(ctx, t, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha;

    ctx.fillStyle = '#04060d';
    ctx.fillRect(0, 0, W, H);

    var cx = W / 2, cy = H * 0.42;

    // logo mark: circle + orbiting arc
    ctx.strokeStyle = 'rgba(56,225,255,0.85)';
    ctx.lineWidth = 3;
    ctx.shadowColor = CYAN;
    ctx.shadowBlur = 18;
    ctx.beginPath();
    ctx.arc(cx, cy, 46, 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = AMBER;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.arc(cx, cy, 62, t * 1.4, t * 1.4 + Math.PI * 0.8);
    ctx.stroke();
    ctx.shadowBlur = 0;

    ctx.textAlign = 'center';
    ctx.font = '900 64px "Segoe UI", Arial, sans-serif';
    ctx.fillStyle = '#eef7ff';
    ctx.fillText('JARVIS', cx, cy + 130);

    var tagP = easeOutCubic(clamp01((t - 13.9) / 0.8));
    ctx.globalAlpha = alpha * tagP;
    ctx.font = '500 24px "Segoe UI", Arial, sans-serif';
    ctx.fillStyle = 'rgba(160,210,235,0.95)';
    ctx.fillText('every frame is a function call', cx, cy + 172);

    ctx.globalAlpha = alpha * tagP * 0.8;
    ctx.font = '600 18px Consolas, monospace';
    ctx.fillStyle = AMBER;
    ctx.fillText('F I N', cx, cy + 226);

    ctx.textAlign = 'left';
    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Compositor — persistent HUD + grain + vignette on top of the scenes
  // ------------------------------------------------------------------

  function drawOverlay(ctx, t) {
    // progress bar (deterministic from t)
    var p = clamp01(t / DURATION);
    ctx.fillStyle = 'rgba(56,225,255,0.85)';
    ctx.fillRect(0, H - 3, W * p, 3);
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fillRect(W * p, H - 3, W * (1 - p), 3);

    // timecode, bottom-right — proves every frame is addressed by t
    ctx.font = '600 15px Consolas, "Courier New", monospace';
    ctx.textAlign = 'right';
    ctx.fillStyle = 'rgba(160,210,235,0.55)';
    ctx.fillText(
      pad(Math.floor(t / 60), 2) + ':' + pad(Math.floor(t % 60), 2) + '.' + pad(Math.floor((t % 1) * FPS), 2),
      W - 18, H - 16
    );
    ctx.textAlign = 'left';

    // film grain, offset locked to the frame index (deterministic)
    if (GRAIN && ctx.canvas.width === W) {
      var fi = Math.floor(t * FPS);
      var ox = (fi * 61) % 160;
      var oy = (fi * 97) % 160;
      ctx.save();
      ctx.globalAlpha = 0.5;
      for (var gx = -ox; gx < W; gx += 160) {
        for (var gy = -oy; gy < H; gy += 160) {
          ctx.drawImage(GRAIN, gx, gy);
        }
      }
      ctx.restore();
    }

    // vignette
    var vg = ctx.createRadialGradient(W / 2, H / 2, H * 0.45, W / 2, H / 2, H * 0.95);
    vg.addColorStop(0, 'rgba(0,0,0,0)');
    vg.addColorStop(1, 'rgba(0,0,0,0.42)');
    ctx.fillStyle = vg;
    ctx.fillRect(0, 0, W, H);
  }

  // ------------------------------------------------------------------
  // The pure render function — same t, same pixels, always.
  // ------------------------------------------------------------------

  var SCENES = [
    { draw: drawIntro, a: 0.0, b: 4.1, rIn: 0.01, rOut: 0.5 },
    { draw: drawWaves, a: 3.6, b: 8.7, rIn: 0.5, rOut: 0.5 },
    { draw: drawTech, a: 8.2, b: 13.3, rIn: 0.5, rOut: 0.5 },
    { draw: drawOutro, a: 12.8, b: 16.01, rIn: 0.5, rOut: 0.01 }
  ];

  function renderFrame(ctx, t) {
    ctx.save();
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#04060d';
    ctx.fillRect(0, 0, W, H);

    for (var i = 0; i < SCENES.length; i++) {
      var s = SCENES[i];
      if (t >= s.a - 0.001 && t <= s.b + 0.001) {
        var a = sceneAlpha(t, s.a, s.b, s.rIn, s.rOut);
        if (a > 0.001) {
          ctx.save();
          // clip scenes to the video rect so strip mode tiles stay isolated
          ctx.beginPath();
          ctx.rect(0, 0, W, H);
          ctx.clip();
          s.draw(ctx, t, a);
          ctx.restore();
        }
      }
    }

    drawOverlay(ctx, t);
    ctx.restore();
  }

  // Export for the player page, the strip exporter and tests.
  global.CodeVideo = {
    W: W, H: H, FPS: FPS, DURATION: DURATION, TOTAL_FRAMES: TOTAL_FRAMES,
    renderFrame: renderFrame
  };

})(typeof window !== 'undefined' ? window : globalThis);
