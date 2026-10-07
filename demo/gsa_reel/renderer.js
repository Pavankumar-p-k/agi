/*
 * GSA Reel — "POV: you turn a random idea into a full brand in under a minute"
 * A 30s vertical (1080x1920, 30fps) social reel rendered entirely by code —
 * every frame is renderFrame(ctx, t); same t => same pixels, always.
 *
 * Scenes (per the approved script structure):
 *   1 HOOK    0.0–4.0   phone glow, thumbs typing "random idea..." at 2:47 AM
 *   2 BUILD   3.5–11.0  Gemini Chat fast-cuts: name -> tagline -> market -> USP
 *   3 REVEAL 10.5–19.5 logo + packaging + stall cards zoom-set (money shot)
 *   4 CTA    19.0–25.5 "Google AI Plus is FREE for students"
 *   5 TAG    25.0–30.0 "Tag someone..." + end card
 */
(function (global) {
  'use strict';

  var W = 1080, H = 1920, FPS = 30, DURATION = 30;
  var TOTAL_FRAMES = FPS * DURATION;

  // GSA palette
  var BLUE = '#4285F4';
  var RED = '#EA4335';
  var YELLOW = '#FBBC05';
  var GREEN = '#34A853';
  var CREAM = '#FFF8EE';
  var INK = '#1F1A14';
  var MINT = '#7FE7C4';
  var GOOGLE_FONTS = '"Product Sans", "Segoe UI", Arial, sans-serif';

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function easeOutCubic(p) { return 1 - Math.pow(1 - p, 3); }
  function easeInOutCubic(p) { return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; }
  function easeOutBack(p) { var c = 1.70158; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); }
  function sceneAlpha(t, a, b, ri, ro) {
    return Math.min(ri <= 0 ? 1 : clamp01((t - a) / ri), clamp01((b - t) / ro));
  }
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function pad(n, w) { var s = String(Math.max(0, Math.floor(n))); while (s.length < w) s = '0' + s; return s; }

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function fitText(ctx, text, maxW, startPx, weight) {
    var px = startPx;
    for (; px > 12; px -= 2) {
      ctx.font = weight + ' ' + px + 'px ' + GOOGLE_FONTS;
      if (ctx.measureText(text).width <= maxW) break;
    }
    return px;
  }

  function star(ctx, cx, cy, spikes, outer, inner, color, rot) {
    ctx.fillStyle = color;
    ctx.beginPath();
    for (var i = 0; i < spikes * 2; i++) {
      var rr2 = i % 2 === 0 ? outer : inner;
      var a = rot + (Math.PI * i) / spikes;
      var px = cx + rr2 * Math.cos(a), py = cy + rr2 * Math.sin(a);
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fill();
  }

  // ------------------------------------------------------------------
  // Precomputed (deterministic) content
  // ------------------------------------------------------------------
  var BOKEH = (function () {
    var rnd = mulberry32(2026);
    var arr = [];
    for (var i = 0; i < 26; i++) {
      arr.push({ x: rnd() * W, y: rnd() * H, r: 30 + rnd() * 90, a: 0.04 + rnd() * 0.10,
                 sp: 8 + rnd() * 26, ph: rnd() * 6.28 });
    }
    return arr;
  })();

  var CONFETTI = (function () {
    var rnd = mulberry32(4844);
    var cols = [BLUE, RED, YELLOW, GREEN, MINT];
    var arr = [];
    for (var i = 0; i < 80; i++) {
      arr.push({ x: rnd() * W, w: 8 + rnd() * 14, h: 12 + rnd() * 18,
                 vy: 160 + rnd() * 260, vx: -60 + rnd() * 120, rot: rnd() * 6.28,
                 vr: -3 + rnd() * 6, c: cols[Math.floor(rnd() * cols.length)] });
    }
    return arr;
  })();

  // ------------------------------------------------------------------
  // Scene 1 — HOOK (0.0-4.0)
  // ------------------------------------------------------------------
  function drawHook(ctx, t, alpha) {
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.fillStyle = '#0E1420'; ctx.fillRect(0, 0, W, H);

    // room bokeh (late night desk)
    for (var i = 0; i < BOKEH.length; i++) {
      var b = BOKEH[i];
      var y = (b.y - t * b.sp) % (H + 200);
      if (y < -100) y += H + 200;
      ctx.globalAlpha = alpha * b.a * (0.7 + 0.3 * Math.sin(t * 0.9 + b.ph));
      ctx.fillStyle = b.ph % 2 > 1 ? YELLOW : BLUE;
      ctx.beginPath(); ctx.arc(b.x + 18 * Math.sin(t * 0.4 + b.ph), y, b.r, 0, 6.2832); ctx.fill();
    }
    ctx.globalAlpha = alpha;

    // "phone" rectangle glowing in the center
    var ph = { x: W / 2 - 270, y: 560, w: 540, h: 800 };
    var glow = ctx.createRadialGradient(W / 2, ph.y + ph.h / 2, 80, W / 2, ph.y + ph.h / 2, 700);
    glow.addColorStop(0, 'rgba(66,133,244,0.20)');
    glow.addColorStop(1, 'rgba(66,133,244,0)');
    ctx.fillStyle = glow; ctx.fillRect(0, 0, W, H);

    rr(ctx, ph.x, ph.y, ph.w, ph.h, 48);
    ctx.fillStyle = '#0A0F18'; ctx.fill();
    ctx.strokeStyle = 'rgba(66,133,244,0.55)'; ctx.lineWidth = 4; ctx.stroke();

    // status bar clock 2:47 AM
    ctx.font = '600 30px ' + GOOGLE_FONTS;
    ctx.fillStyle = 'rgba(255,255,255,0.75)';
    ctx.fillText('2:47 AM', ph.x + 36, ph.y + 64);
    ctx.textAlign = 'right';
    ctx.fillText('🔋 38%', ph.x + ph.w - 36, ph.y + 64);
    ctx.textAlign = 'left';

    // typing "random idea..." with deterministic caret
    var idea = 'random idea: sneaker brand for campus?';
    var chars = Math.floor(clamp01((t - 0.6) / 2.2) * idea.length);
    ctx.font = '500 34px ' + GOOGLE_FONTS;
    ctx.fillStyle = '#EAF2FF';
    ctx.fillText(idea.slice(0, chars) + ((t * 2.2) % 1 < 0.5 ? '▍' : ''), ph.x + 36, ph.y + 200);

    // send button appears late in scene
    var sb = easeOutBack(clamp01((t - 2.9) / 0.6));
    if (sb > 0.01) {
      ctx.save();
      ctx.translate(ph.x + ph.w - 100, ph.y + 300);
      ctx.scale(sb, sb);
      ctx.beginPath(); ctx.arc(0, 0, 40, 0, 6.2832);
      ctx.fillStyle = BLUE; ctx.fill();
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 5;
      ctx.beginPath(); ctx.moveTo(-14, 0); ctx.lineTo(10, 0); ctx.moveTo(2, -10); ctx.lineTo(12, 0); ctx.lineTo(2, 10);
      ctx.stroke();
      ctx.restore();
    }

    // POV caption
    var capP = easeOutCubic(clamp01((t - 0.25) / 0.55));
    ctx.save();
    ctx.translate(W / 2, 260);
    ctx.globalAlpha = alpha * capP;
    fitText(ctx, 'POV: you turn a random', 940, 84, '800');
    ctx.fillStyle = '#fff'; ctx.textAlign = 'center';
    ctx.fillText('POV: you turn a random', 0, 0);
    fitText(ctx, 'idea into a full brand', 940, 84, '800');
    ctx.fillStyle = YELLOW;
    ctx.fillText('idea into a full brand', 0, 100);
    ctx.font = '600 36px ' + GOOGLE_FONTS;
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.fillText('in under a minute', 0, 172);
    ctx.restore();

    ctx.textAlign = 'left';
    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Scene 2 — BUILD with Gemini (3.5-11.0): fast-cut chat cards
  // ------------------------------------------------------------------
  var BUILD_STEPS = [
    { icon: '✏️', label: 'BRAND NAME',   value: 'KICKS',                a: 4.3 },
    { icon: '💬', label: 'TAGLINE',      value: '"Own the campus."',    a: 5.9 },
    { icon: '🎯', label: 'TARGET MARKET',value: 'College sneakerheads', a: 7.5 },
    { icon: '⚡', label: 'USP',          value: 'Custom colorways, 48h delivery', a: 9.1 }
  ];

  function drawBuild(ctx, t, alpha) {
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.fillStyle = '#F6F1E7'; ctx.fillRect(0, 0, W, H);

    // subtle grid texture (deterministic)
    ctx.strokeStyle = 'rgba(31,26,20,0.05)'; ctx.lineWidth = 1;
    for (var gx = 0; gx <= W; gx += 72) { ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke(); }
    for (var gy = 0; gy <= H; gy += 72) { ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke(); }

    // header: Gemini spark + title
    var sparkA = easeOutBack(clamp01((t - 3.6) / 0.7));
    ctx.save();
    ctx.translate(W / 2, 300);
    ctx.scale(sparkA, sparkA);
    // four-point Gemini spark
    ctx.fillStyle = BLUE;
    ctx.beginPath();
    ctx.moveTo(0, -84); ctx.quadraticCurveTo(12, -12, 84, 0);
    ctx.quadraticCurveTo(12, 12, 0, 84);
    ctx.quadraticCurveTo(-12, 12, -84, 0);
    ctx.quadraticCurveTo(-12, -12, 0, -84);
    ctx.fill();
    ctx.fillStyle = MINT;
    ctx.beginPath();
    ctx.moveTo(0, -40); ctx.quadraticCurveTo(6, -6, 40, 0);
    ctx.quadraticCurveTo(6, 6, 0, 40);
    ctx.quadraticCurveTo(-6, 6, -40, 0);
    ctx.quadraticCurveTo(-6, -6, 0, -40);
    ctx.fill();
    ctx.restore();

    var hP = easeOutCubic(clamp01((t - 3.8) / 0.6));
    if (hP > 0.01) {
      ctx.globalAlpha = alpha * hP;
      ctx.textAlign = 'center';
      fitText(ctx, 'GEMINI CHAT', 900, 64, '800');
      ctx.fillStyle = INK;
      ctx.fillText('GEMINI CHAT', W / 2, 448);
      ctx.font = '600 32px ' + GOOGLE_FONTS;
      ctx.fillStyle = 'rgba(31,26,20,0.6)';
      ctx.fillText('idea ➜ brand in four answers', W / 2, 502);
      ctx.globalAlpha = alpha;
      ctx.textAlign = 'left';
    }

    // chat cards pop in sequence (fast-cut feel)
    for (var s = 0; s < BUILD_STEPS.length; s++) {
      var st = BUILD_STEPS[s];
      var p = easeOutBack(clamp01((t - st.a) / 0.55));
      if (p <= 0.01) continue;
      var y = 590 + s * 300;
      ctx.save();
      ctx.translate(W / 2, y);
      ctx.scale(p, p);
      ctx.globalAlpha = alpha * Math.min(1, p);
      rr(ctx, -460, -120, 920, 240, 34);
      ctx.fillStyle = '#FFFFFF'; ctx.fill();
      ctx.strokeStyle = 'rgba(66,133,244,0.25)'; ctx.lineWidth = 3; ctx.stroke();
      ctx.fillStyle = BLUE;
      rr(ctx, -460, -120, 14, 240, 7); ctx.fill();
      ctx.font = '46px "Segoe UI Emoji", ' + GOOGLE_FONTS;
      ctx.fillText(st.icon, -400, -38);
      ctx.font = '700 30px ' + GOOGLE_FONTS;
      ctx.fillStyle = 'rgba(31,26,20,0.55)';
      ctx.fillText(st.label, -320, -40);
      var vw = fitText(ctx, st.value, 720, 52, '800');
      ctx.fillStyle = INK;
      ctx.font = '800 ' + vw + 'px ' + GOOGLE_FONTS;
      ctx.fillText(st.value, -320, 46);
      ctx.restore();
    }

    // progress dots
    ctx.textAlign = 'center';
    for (var d = 0; d < 4; d++) {
      ctx.beginPath();
      ctx.arc(W / 2 - 54 + d * 36, 1830, d <= Math.floor((t - 4.3) / 1.6) ? 10 : 7, 0, 6.2832);
      ctx.fillStyle = d <= Math.floor((t - 4.3) / 1.6) ? BLUE : 'rgba(31,26,20,0.2)';
      ctx.fill();
    }
    ctx.textAlign = 'left';
    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Scene 3 — REVEAL (10.5-19.5): logo, packaging, stall (money shot)
  // ------------------------------------------------------------------
  function drawReveal(ctx, t, alpha) {
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.fillStyle = '#0B1220'; ctx.fillRect(0, 0, W, H);

    // spotlight
    var sp = ctx.createRadialGradient(W / 2, 880, 60, W / 2, 880, 980);
    sp.addColorStop(0, 'rgba(66,133,244,0.16)');
    sp.addColorStop(1, 'rgba(66,133,244,0)');
    ctx.fillStyle = sp; ctx.fillRect(0, 0, W, H);

    // slow zoom on the whole board
    var zoom = 1.04 + 0.05 * easeInOutCubic(clamp01(t / 9));
    ctx.save();
    ctx.translate(W / 2, H / 2); ctx.scale(zoom, zoom); ctx.translate(-W / 2, -H / 2);

    // 3 reveal cards: logo -> packaging -> stall
    var cards = [
      { y: 560, label: 'LOGO', a: 10.9 },
      { y: 980, label: 'PACKAGING', a: 12.5 },
      { y: 1400, label: 'STALL SETUP', a: 14.1 }
    ];
    for (var c = 0; c < cards.length; c++) {
      var cd = cards[c];
      var p = easeOutBack(clamp01((t - cd.a) / 0.7));
      if (p <= 0.01) continue;
      ctx.save();
      ctx.translate(W / 2, cd.y);
      ctx.scale(p, p);
      ctx.globalAlpha = alpha * Math.min(1, p);

      rr(ctx, -440, -190, 880, 380, 40);
      ctx.fillStyle = CREAM; ctx.fill();
      ctx.strokeStyle = 'rgba(66,133,244,0.35)'; ctx.lineWidth = 4; ctx.stroke();

      // faux logo art (sneaker mark), packaging box art, stall awning art
      if (c === 0) {
        // sneaker glyph built from paths
        ctx.fillStyle = BLUE;
        rr(ctx, -300, -60, 300, 130, 24); ctx.fill();
        ctx.fillStyle = '#fff';
        rr(ctx, -288, 8, 276, 52, 18); ctx.fill();
        ctx.fillStyle = RED;
        ctx.beginPath();
        ctx.moveTo(-290, 20); ctx.quadraticCurveTo(-180, -60, -40, 26);
        ctx.lineTo(-40, 48); ctx.quadraticCurveTo(-180, -8, -290, 44);
        ctx.closePath(); ctx.fill();
        ctx.fillStyle = INK;
        ctx.font = '800 44px ' + GOOGLE_FONTS;
        ctx.fillText('KICKS', 40, 20);
        ctx.font = '600 26px ' + GOOGLE_FONTS;
        ctx.fillStyle = 'rgba(31,26,20,0.55)';
        ctx.fillText('designed by Nano Banana', 40, 66);
      } else if (c === 1) {
        // packaging box
        ctx.fillStyle = YELLOW;
        rr(ctx, -280, -110, 240, 220, 20); ctx.fill();
        ctx.fillStyle = INK;
        rr(ctx, -280, -110, 240, 56, 20); ctx.fill();
        ctx.fillStyle = CREAM;
        ctx.font = '800 34px ' + GOOGLE_FONTS;
        ctx.fillText('KICKS', -250, -68);
        // box sides
        ctx.fillStyle = '#E3A900';
        ctx.beginPath(); ctx.moveTo(-40, -110); ctx.lineTo(40, -150); ctx.lineTo(40, 70); ctx.lineTo(-40, 110); ctx.closePath(); ctx.fill();
        ctx.fillStyle = '#C68F00';
        ctx.beginPath(); ctx.moveTo(-280, 110); ctx.lineTo(-40, 110); ctx.lineTo(40, 70); ctx.lineTo(-280, 70); ctx.closePath(); ctx.fill();
        ctx.font = '600 30px ' + GOOGLE_FONTS;
        ctx.fillStyle = 'rgba(31,26,20,0.6)';
        ctx.fillText('unboxing-ready', 120, 0);
        ctx.fillText('mailers & tissue', 120, 46);
      } else {
        // stall: awning + counter + sign
        var stripes = [BLUE, '#fff', RED, '#fff'];
        for (var sI = 0; sI < 6; sI++) {
          ctx.fillStyle = stripes[sI % 4];
          ctx.fillRect(-330 + sI * 110, -150, 110, 70);
        }
        ctx.fillStyle = GREEN;
        rr(ctx, -330, -80, 660, 40, 8); ctx.fill();
        ctx.fillStyle = '#8B5A2B';
        rr(ctx, -300, -40, 600, 200, 14); ctx.fill();
        ctx.fillStyle = CREAM;
        rr(ctx, -260, -10, 520, 110, 12); ctx.fill();
        ctx.fillStyle = INK;
        ctx.font = '800 40px ' + GOOGLE_FONTS;
        ctx.textAlign = 'center';
        ctx.fillText('KICKS — campus pop-up', 0, 52);
        ctx.textAlign = 'left';
      }

      // label chip
      ctx.fillStyle = INK;
      rr(ctx, -440, -230, 250, 66, 33); ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = '800 28px ' + GOOGLE_FONTS;
      ctx.fillText(cd.label, -410, -188);
      ctx.restore();
    }
    ctx.restore();

    // "NANO BANANA" title
    var nbP = easeOutCubic(clamp01((t - 10.7) / 0.7));
    if (nbP > 0.01) {
      ctx.globalAlpha = alpha * nbP;
      ctx.textAlign = 'center';
      fitText(ctx, 'NANO BANANA', 900, 76, '900');
      ctx.fillStyle = '#fff';
      ctx.fillText('NANO BANANA', W / 2, 260);
      ctx.font = '600 34px ' + GOOGLE_FONTS;
      ctx.fillStyle = YELLOW;
      ctx.fillText('the visuals ✨', W / 2, 330);
      ctx.textAlign = 'left';
      ctx.globalAlpha = alpha;
    }
    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Scene 4 — CTA (19.0-25.5): FREE for students
  // ------------------------------------------------------------------
  function drawCTA(ctx, t, alpha) {
    ctx.save(); ctx.globalAlpha = alpha;
    // Google 4-color diagonal sweep background
    var bands = [BLUE, RED, YELLOW, GREEN];
    var bandH = H / 4;
    for (var b = 0; b < 4; b++) {
      ctx.fillStyle = bands[b];
      var off = (easeOutCubic(clamp01((t - 19.1 - b * 0.12) / 0.7)) - 1) * W;
      ctx.fillRect(off, b * bandH, W, bandH + 1);
    }

    // center card
    var cardP = easeOutBack(clamp01((t - 19.9) / 0.8));
    if (cardP > 0.01) {
      ctx.save();
      ctx.translate(W / 2, H / 2);
      ctx.scale(cardP, cardP);
      rr(ctx, -440, -460, 880, 920, 56);
      ctx.fillStyle = '#FFFFFF'; ctx.fill();
      ctx.shadowColor = 'rgba(0,0,0,0.25)'; ctx.shadowBlur = 40; ctx.shadowOffsetY = 12;
      ctx.fill();
      ctx.shadowColor = 'transparent';

      ctx.textAlign = 'center';
      ctx.fillStyle = INK;
      ctx.font = '800 52px ' + GOOGLE_FONTS;
      ctx.fillText('Google AI Plus', 0, -330);
      ctx.font = '600 34px ' + GOOGLE_FONTS;
      ctx.fillStyle = 'rgba(31,26,20,0.6)';
      ctx.fillText('is', 0, -270);

      var freeP = easeOutBack(clamp01((t - 20.6) / 0.7));
      ctx.save();
      ctx.translate(0, -80);
      ctx.scale(freeP, freeP);
      fitText(ctx, 'FREE', 760, 190, '900');
      var fg = ctx.createLinearGradient(-200, 0, 200, 0);
      fg.addColorStop(0, BLUE); fg.addColorStop(0.35, RED); fg.addColorStop(0.7, YELLOW); fg.addColorStop(1, GREEN);
      ctx.fillStyle = fg;
      ctx.fillText('FREE', 0, 60);
      ctx.restore();

      ctx.font = '700 40px ' + GOOGLE_FONTS;
      ctx.fillStyle = INK;
      ctx.fillText('for students right now', 0, 130);

      // pill list
      var pills = ['Gemini Chat', 'Nano Banana', 'NotebookLM'];
      for (var p2 = 0; p2 < pills.length; p2++) {
        var pillP = easeOutBack(clamp01((t - 21.2 + p2 * 0.25) / 0.5));
        ctx.save();
        ctx.translate(-170 + p2 * 200, 240);
        ctx.scale(pillP, pillP);
        ctx.globalAlpha = Math.min(1, pillP);
        rr(ctx, -90, -34, 180, 68, 34);
        ctx.fillStyle = 'rgba(66,133,244,0.10)'; ctx.fill();
        ctx.strokeStyle = 'rgba(66,133,244,0.4)'; ctx.lineWidth = 2; ctx.stroke();
        ctx.fillStyle = BLUE;
        ctx.font = '700 24px ' + GOOGLE_FONTS;
        ctx.textAlign = 'center';
        ctx.fillText(pills[p2], 0, 9);
        ctx.restore();
      }

      ctx.font = '600 30px ' + GOOGLE_FONTS;
      ctx.fillStyle = 'rgba(31,26,20,0.6)';
      ctx.fillText('No excuse not to try this 🚀', 0, 380);
      ctx.textAlign = 'left';
      ctx.restore();
    }

    // small print
    ctx.globalAlpha = alpha * 0.85;
    ctx.font = '600 26px ' + GOOGLE_FONTS;
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.textAlign = 'center';
    ctx.fillText('Google AI Plus — student offer, India', W / 2, 1850);
    ctx.textAlign = 'left';
    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Scene 5 — TAG (25.0-30.0): challenge + end card
  // ------------------------------------------------------------------
  function drawTag(ctx, t, alpha) {
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.fillStyle = '#0E1420'; ctx.fillRect(0, 0, W, H);

    // falling confetti (deterministic loop)
    for (var i = 0; i < CONFETTI.length; i++) {
      var c = CONFETTI[i];
      var yy = (c.y + t * c.vy) % (H + 120) - 60;
      var xx = (c.x + t * c.vx) % W;
      ctx.save();
      ctx.translate(xx, yy);
      ctx.rotate(c.rot + t * c.vr);
      ctx.globalAlpha = alpha * 0.85;
      ctx.fillStyle = c.c;
      ctx.fillRect(-c.w / 2, -c.h / 2, c.w, c.h);
      ctx.restore();
    }

    ctx.textAlign = 'center';
    var line1P = easeOutBack(clamp01((t - 25.2) / 0.6));
    ctx.save();
    ctx.translate(W / 2, 700);
    ctx.scale(line1P, line1P);
    ctx.fillStyle = '#fff';
    fitText(ctx, 'Tag someone who’s got', 920, 74, '800');
    ctx.fillText('Tag someone who’s got', 0, 0);
    ctx.fillStyle = YELLOW;
    fitText(ctx, 'a business idea', 920, 74, '800');
    ctx.fillText('a business idea', 0, 92);
    ctx.fillStyle = '#fff';
    fitText(ctx, 'sitting in their notes app', 920, 74, '800');
    ctx.fillText('sitting in their notes app', 0, 184);
    ctx.fillStyle = MINT;
    fitText(ctx, 'doing nothing!', 920, 74, '800');
    ctx.fillText('doing nothing!', 0, 276);
    ctx.restore();

    // end card
    var endP = easeOutBack(clamp01((t - 27.0) / 0.8));
    if (endP > 0.01) {
      ctx.save();
      ctx.translate(W / 2, 1350);
      ctx.scale(endP, endP);
      rr(ctx, -380, -170, 760, 340, 44);
      ctx.fillStyle = 'rgba(255,255,255,0.06)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(66,133,244,0.5)'; ctx.lineWidth = 3; ctx.stroke();
      ctx.fillStyle = '#fff';
      ctx.font = '900 60px ' + GOOGLE_FONTS;
      ctx.fillText('KICKS × GEMINI', 0, -40);
      ctx.font = '600 32px ' + GOOGLE_FONTS;
      ctx.fillStyle = 'rgba(255,255,255,0.75)';
      ctx.fillText('made in under a minute', 0, 30);
      ctx.fillStyle = YELLOW;
      ctx.font = '800 30px ' + GOOGLE_FONTS;
      ctx.fillText('#GoogleStudentAmbassador #GSA2026', 0, 100);
      ctx.restore();
    }

    // GID chip
    ctx.globalAlpha = alpha * 0.9;
    rr(ctx, W / 2 - 90, 1800, 180, 64, 32);
    ctx.fillStyle = 'rgba(255,255,255,0.10)'; ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.font = '700 28px ' + GOOGLE_FONTS;
    ctx.textAlign = 'center';
    ctx.fillText('GID 4844', W / 2, 1842);
    ctx.textAlign = 'left';
    ctx.restore();
  }

  // ------------------------------------------------------------------
  // Persistent overlay: progress bar + timecode
  // ------------------------------------------------------------------
  function drawOverlay(ctx, t) {
    var p = clamp01(t / DURATION);
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.fillRect(0, H - 8, W * p, 8);
  }

  // ------------------------------------------------------------------
  // Compositor
  // ------------------------------------------------------------------
  var SCENES = [
    { draw: drawHook,   a: 0.0,  b: 4.01,  ri: 0.01, ro: 0.5 },
    { draw: drawBuild,  a: 3.5,  b: 11.01, ri: 0.5,  ro: 0.5 },
    { draw: drawReveal, a: 10.5, b: 19.51, ri: 0.5,  ro: 0.5 },
    { draw: drawCTA,    a: 19.0, b: 25.51, ri: 0.5,  ro: 0.5 },
    { draw: drawTag,    a: 25.0, b: 30.01, ri: 0.5,  ro: 0.01 }
  ];

  function renderFrame(ctx, t) {
    ctx.save();
    ctx.clearRect(0, 0, W, H);
    for (var i = 0; i < SCENES.length; i++) {
      var s = SCENES[i];
      if (t >= s.a - 0.001 && t <= s.b + 0.001) {
        var a = sceneAlpha(t, s.a, s.b, s.ri, s.ro);
        if (a > 0.001) {
          ctx.save();
          ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip();
          s.draw(ctx, t, a);
          ctx.restore();
        }
      }
    }
    drawOverlay(ctx, t);
    ctx.restore();
  }

  global.CodeReel = { W: W, H: H, FPS: FPS, DURATION: DURATION, TOTAL_FRAMES: TOTAL_FRAMES, renderFrame: renderFrame };
})(typeof window !== 'undefined' ? window : globalThis);
