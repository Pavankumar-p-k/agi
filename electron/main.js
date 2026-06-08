/**
 * electron/main.js  — JARVIS Dot  (v2 — fixed panel sizing + corner-aware)
 *
 * Changes from v1:
 *  - Panel is a fixed 340px wide, height-capped at 680px (NEVER fullscreen)
 *  - Panel position is corner-aware: opens opposite corner of where dot sits
 *  - Handles 'resize-dot' IPC → resizes dot window for bar mode
 *  - Handles 'apply-dot-cfg' IPC → forwards to dot window
 *  - Handles 'open-panel' IPC → shows panel at correct position + loads view
 */

const {
  app, BrowserWindow, globalShortcut, ipcMain,
  screen, Tray, Menu, nativeImage, shell, dialog,
} = require('electron');
const path = require('path');
const fs   = require('fs');
const os   = require('os');
const https = require('https');
const http  = require('http');
const { spawn, execFile, exec } = require('child_process');

// ─── Config ───────────────────────────────────────────────────────────────────
const JARVIS_URL  = process.env.JARVIS_URL || 'http://localhost:8000';
const DOT_DEFAULT = 56;   // default dot window size (square)
const PANEL_W     = 340;  // panel width — FIXED, never changes
const PANEL_H_MIN = 180;
const PANEL_H_MAX = 680;
const PANEL_GAP   = 14;   // gap between dot/bar edge and panel

let dotWindow   = null;
let panelWindow = null;
let tray        = null;

// Current dot window dimensions + position (tracked manually)
let dotWinW = DOT_DEFAULT;
let dotWinH = DOT_DEFAULT;
let dotWinX = null;
let dotWinY = null;

// ─── Config persistence ───────────────────────────────────────────────────────
const CONFIG_PATH = path.join(os.homedir(), '.jarvis', 'electron-config.json');

function loadConfig() {
  try { if (fs.existsSync(CONFIG_PATH)) return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8')); }
  catch {}
  return {};
}
function saveConfig(data) {
  try { fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true }); fs.writeFileSync(CONFIG_PATH, JSON.stringify(data, null, 2)); }
  catch {}
}

// ─── Create dot window ────────────────────────────────────────────────────────
function createDotWindow() {
  const cfg = loadConfig();
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  dotWinX = cfg.dotX ?? (width  - DOT_DEFAULT - 20);
  dotWinY = cfg.dotY ?? Math.floor(height / 2);

  dotWindow = new BrowserWindow({
    width:  DOT_DEFAULT,
    height: DOT_DEFAULT,
    x: dotWinX, y: dotWinY,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });

  dotWindow.loadFile(path.join(__dirname, 'src', 'dot.html'));
  dotWindow.setAlwaysOnTop(true, 'screen-saver');

  dotWindow.on('moved', () => {
    const [bx, by] = dotWindow.getPosition();
    dotWinX = bx; dotWinY = by;
    saveConfig({ ...loadConfig(), dotX: bx, dotY: by });
  });
  dotWindow.on('closed', () => { dotWindow = null; });
}

// ─── Create panel window ──────────────────────────────────────────────────────
function createPanelWindow() {
  panelWindow = new BrowserWindow({
    width:  PANEL_W,
    height: PANEL_H_MIN,
    show:   false,
    frame:  false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable:   false,
    hasShadow:   true,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });

  panelWindow.loadFile(path.join(__dirname, 'src', 'panel.html'));

  panelWindow.on('blur', () => { if (panelWindow) panelWindow.hide(); });
  panelWindow.on('closed', () => { panelWindow = null; });
}

// ─── Corner-aware panel positioning ──────────────────────────────────────────
// Panel opens OPPOSITE side of where the dot/bar sits.
function calcPanelPosition(panelH) {
  if (!dotWindow) return { px: 100, py: 100 };

  const [dx, dy] = dotWindow.getPosition();
  const [aw, ah] = dotWindow.getSize();   // actual window size
  const disp = screen.getDisplayNearestPoint({ x: dx, y: dy });
  const { width: SW, height: SH } = disp.workArea;

  const leftEdge  = dx;
  const rightEdge = dx + aw;
  const centerX   = dx + aw / 2;

  let px, py;

  if (centerX > SW / 2) {
    px = leftEdge - PANEL_W - PANEL_GAP;      // panel on LEFT of dot
  } else {
    px = rightEdge + PANEL_GAP;               // panel on RIGHT of dot
  }
  py = dy;

  // Clamp to correct display bounds
  px = Math.max(disp.workArea.x + 6, Math.min(px, disp.workArea.x + SW - PANEL_W - 6));
  py = Math.max(disp.workArea.y + 6, Math.min(py, disp.workArea.y + SH - panelH - 6));

  return { px, py };
}

// ─── Dot position presets ────────────────────────────────────────────────────
function calcDotPosition(preset) {
  const { width: SW, height: SH } = screen.getPrimaryDisplay().workAreaSize;
  const dotW = DOT_DEFAULT;
  const dotH = DOT_DEFAULT;
  const margin = 16;

  const positions = {
    'top-left':      { x: margin,              y: margin },
    'top-center':    { x: Math.floor(SW/2 - dotW/2), y: margin },
    'top-right':     { x: SW - dotW - margin,   y: margin },
    'left-middle':   { x: margin,              y: Math.floor(SH/2 - dotH/2) },
    'center':        { x: Math.floor(SW/2 - dotW/2), y: Math.floor(SH/2 - dotH/2) },
    'right-middle':  { x: SW - dotW - margin,   y: Math.floor(SH/2 - dotH/2) },
    'bottom-left':   { x: margin,              y: SH - dotH - margin },
    'bottom-center': { x: Math.floor(SW/2 - dotW/2), y: SH - dotH - margin },
    'bottom-right':  { x: SW - dotW - margin,   y: SH - dotH - margin },
  };
  return positions[preset] || positions['right-middle'];
}

function showPanel(data) {
  if (!panelWindow || !dotWindow) return;
  // First send the data, then show at position
  panelWindow.webContents.send('show-answer', data);
  repositionPanel(PANEL_H_MIN);
  panelWindow.showInactive();
}

function showPanelView(view) {
  if (!panelWindow || !dotWindow) return;
  panelWindow.webContents.send('open-panel', view);
  repositionPanel(PANEL_H_MIN);
  panelWindow.showInactive();
}

function repositionPanel(panelH) {
  const h = Math.min(Math.max(panelH, PANEL_H_MIN), PANEL_H_MAX);
  const { px, py } = calcPanelPosition(h);
  panelWindow.setPosition(px, py);
  panelWindow.setSize(PANEL_W, h);
}

function hidePanel() {
  if (panelWindow) {
    panelWindow.hide();
    // Tell dot to clear active rail button
    if (dotWindow) dotWindow.webContents.send('panel-closed');
  }
}

// ─── Screen understanding ─────────────────────────────────────────────────────
async function doScreenUnderstand(userText = null) {
  if (dotWindow) dotWindow.webContents.send('set-state', 'thinking');
  hidePanel();

  try {
    let screenshot;
    try {
      const sd = require('screenshot-desktop');
      screenshot = await sd({ format: 'png' });
    } catch { screenshot = await fallbackScreenshot(); }

    const b64 = screenshot.toString('base64');
    const body = JSON.stringify({ screenshot_b64: b64, context: userText || null });
    const answer = await postJSON(`${JARVIS_URL}/api/screen/understand`, body);

    if (dotWindow) dotWindow.webContents.send('set-state', 'ready');
    showPanel({ type: 'screen', answer: answer.answer || 'No response', model: answer.model });
    setTimeout(hidePanel, 12000);

  } catch (err) {
    console.error('Screen understand error:', err);
    if (dotWindow) dotWindow.webContents.send('set-state', 'idle');
    showPanel({ type: 'error', answer: `Could not reach JARVIS. Is it running at ${JARVIS_URL}?` });
  }
}

async function fallbackScreenshot() {
  return new Promise((resolve, reject) => {
    const platform = os.platform();
    const tmpFile = path.join(os.tmpdir(), `jarvis-screen-${Date.now()}.png`);
    let cmd, args;
    if (platform === 'linux')  { cmd = 'scrot'; args = [tmpFile]; }
    else if (platform === 'darwin') { cmd = 'screencapture'; args = ['-x', tmpFile]; }
    else if (platform === 'win32') {
      cmd = 'powershell'; args = ['-Command',
        `Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::PrimaryScreen | ForEach-Object { $bmp = New-Object System.Drawing.Bitmap($_.Bounds.Width,$_.Bounds.Height); $g=[System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($_.Bounds.Location,[System.Drawing.Point]::Empty,$_.Bounds.Size); $bmp.Save('${tmpFile}') }`];
    } else { reject(new Error('Unsupported platform')); return; }

    execFile(cmd, args, (err) => {
      if (err) { reject(err); return; }
      try { const data = fs.readFileSync(tmpFile); fs.unlinkSync(tmpFile); resolve(data); }
      catch (e) { reject(e); }
    });
  });
}

// ─── HTTP helper ──────────────────────────────────────────────────────────────
function postJSON(url, body) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const lib = parsed.protocol === 'https:' ? https : http;
    const req = lib.request({
      hostname: parsed.hostname,
      port:     parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path:     parsed.pathname,
      method:   'POST',
      headers:  { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      timeout:  60000,
    }, (res) => {
      let data = '';
      res.on('data', c => (data += c));
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch { reject(new Error('Invalid JSON')); } });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });
    req.write(body); req.end();
  });
}

function getJSON(url) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const lib = parsed.protocol === 'https:' ? https : http;
    const req = lib.request({
      hostname: parsed.hostname,
      port:     parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path:     parsed.pathname + parsed.search,
      method:   'GET',
      headers:  { 'Content-Type': 'application/json' },
      timeout:  15000,
    }, (res) => {
      let data = '';
      res.on('data', c => (data += c));
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch { reject(new Error('Invalid JSON')); } });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });
    req.end();
  });
}

// ─── Directory listing (used by Files panel) ──────────────────────────────────
function listDirectory(dirPath) {
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    return entries
      .filter(e => !e.name.startsWith('.'))
      .map(e => {
        const full = path.join(dirPath, e.name);
        let size = null, mtime = null;
        if (e.isFile()) {
          try { const s = fs.statSync(full); size = formatSize(s.size); mtime = s.mtimeMs; } catch {}
        } else {
          try { const s = fs.statSync(full); mtime = s.mtimeMs; } catch {}
        }
        return {
          name: e.name,
          type: e.isDirectory() ? 'dir' : 'file',
          size,
          mtime,
        };
      })
      .sort((a, b) => {
        if (a.type !== b.type) return a.type === 'dir' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
  } catch {
    return [];
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function getHomeDir() {
  return os.homedir();
}

function getDriveRoots() {
  if (os.platform() === 'win32') {
    const drives = [];
    for (let c = 65; c <= 90; c++) {
      const letter = String.fromCharCode(c);
      try {
        if (fs.readdirSync(letter + ':\\')) drives.push(letter + ':\\');
      } catch {}
    }
    return drives;
  }
  return ['/'];
}

// ─── IPC handlers ─────────────────────────────────────────────────────────────

// --- Panel / Dot core ---

// Window drag (JS-based drag from dot renderer)
ipcMain.on('window-drag', (_e, { x, y }) => {
  if (dotWindow) {
    const dx = Math.round(x) - dotWindow.getPosition()[0];
    const dy = Math.round(y) - dotWindow.getPosition()[1];
    dotWinX = Math.round(x); dotWinY = Math.round(y);
    dotWindow.setPosition(dotWinX, dotWinY);
    // Panel follows dot if visible
    if (panelWindow && panelWindow.isVisible()) {
      const [px, py] = panelWindow.getPosition();
      panelWindow.setPosition(px + dx, py + dy);
    }
  }
});

ipcMain.on('dot-voice-trigger', () => doScreenUnderstand('voice trigger'));

// Move dot to a named preset position
ipcMain.on('move-dot-to', (_e, preset) => {
  if (!dotWindow) return;
  const pos = calcDotPosition(preset);
  dotWinX = pos.x; dotWinY = pos.y;
  dotWindow.setPosition(pos.x, pos.y);
  saveConfig({ ...loadConfig(), dotX: pos.x, dotY: pos.y });
  // Reposition panel if visible
  if (panelWindow && panelWindow.isVisible()) {
    const [, , h] = panelWindow.getSize();
    repositionPanel(h);
  }
});

// Panel close
ipcMain.on('panel-close', () => hidePanel());

// Panel follow-up
ipcMain.on('panel-ask-followup', (_e, question) => doScreenUnderstand(question));

// Open specific panel view (from bar rail buttons)
ipcMain.on('open-panel', (_e, view) => showPanelView(view));

// Open JARVIS web chat
ipcMain.on('open-jarvis-dashboard', () => shell.openExternal(`${JARVIS_URL}/chat`));

// Panel resize (renderer tells us its content height)
ipcMain.on('panel-resize', (_e, { height }) => {
  if (panelWindow && panelWindow.isVisible()) repositionPanel(height);
});

ipcMain.on('resize-dot', (_e, { w, h, mode }) => {
  if (!dotWindow) return;
  dotWinW = w; dotWinH = h;

  const [cx, cy] = dotWindow.getPosition();
  const disp = screen.getDisplayNearestPoint({ x: cx, y: cy });
  const { x: dX, y: dY, width: dW, height: dH } = disp.workArea;

  let newX = cx;
  let newY = cy;

  if (w > 56) {
    const mid = dX + dW / 2;
    newX = cx + 56 - w;  // always left of dot first
    if (newX < dX + 8) newX = dX + 8;                     // too far left
    if (newX + w > dX + dW - 8) newX = dX + dW - w - 8;  // too far right
  }

  if (h > 56) {
    newY = cy + 56 - h;  // always above dot first
    if (newY < dY + 8) newY = dY + 8;
    if (newY + h > dY + dH - 8) newY = dY + dH - h - 8;
  }

  dotWindow.setBounds({ x: Math.round(newX), y: Math.round(newY), width: w, height: h });
  dotWinX = newX; dotWinY = newY;
});

// Screen understand from panel
ipcMain.on('screen-understand', () => doScreenUnderstand());

// Dot lock toggle
ipcMain.on('save-dot-lock', (_e, locked) => {
  saveConfig({ ...loadConfig(), locked });
});

// ─── File system (invoke-based) ──────────────────────────────────────────────

ipcMain.handle('home-dir', () => getHomeDir());

ipcMain.handle('list-dir', (_e, dirPath) => listDirectory(dirPath));

ipcMain.handle('get-drives', () => getDriveRoots());

ipcMain.handle('open-file', (_e, filePath) => {
  try { shell.openPath(filePath); return true; } catch { return false; }
});
ipcMain.on('open-file', (_e, filePath) => {
  try { shell.openPath(filePath); } catch {}
});

// ─── Stocks ──────────────────────────────────────────────────────────────────

ipcMain.handle('get-stocks', async (_e, symbol) => {
  try {
    const data = await getJSON(`http://localhost:8000/api/dot/stocks?symbol=${encodeURIComponent(symbol || 'AAPL')}`);
    return data;
  } catch {
    // Fallback: direct Yahoo Finance scrape
    return { symbol: symbol || 'AAPL', price: '—', change: 'N/A', error: 'Could not reach backend' };
  }
});

// ─── News ────────────────────────────────────────────────────────────────────

ipcMain.handle('get-news', async (_e, topic) => {
  try {
    const data = await getJSON(`http://localhost:8000/api/dot/news?topic=${encodeURIComponent(topic || 'technology')}`);
    return data;
  } catch {
    return { articles: [], error: 'Could not reach backend' };
  }
});

// ─── Music ───────────────────────────────────────────────────────────────────

ipcMain.handle('get-music-status', async () => {
  try {
    return await getJSON(`${JARVIS_URL}/api/media/status`);
  } catch { return { playing: false }; }
});

ipcMain.handle('music-play', async () => {
  try { await postJSON(`${JARVIS_URL}/api/media/play`, '{}'); return true; } catch { return false; }
});

ipcMain.handle('music-pause', async () => {
  try { await postJSON(`${JARVIS_URL}/api/media/pause`, '{}'); return true; } catch { return false; }
});

ipcMain.handle('music-next', async () => {
  try { await postJSON(`${JARVIS_URL}/api/media/next`, '{}'); return true; } catch { return false; }
});
ipcMain.handle('music-prev', async () => {
  try { await postJSON(`${JARVIS_URL}/api/media/prev`, '{}'); return true; } catch { return false; }
});

ipcMain.handle('music-volume', async (_e, vol) => {
  try { await postJSON(`${JARVIS_URL}/api/media/volume/${vol}`, '{}'); return true; } catch { return false; }
});

// ─── Mail ────────────────────────────────────────────────────────────────────

ipcMain.handle('get-mails', async () => {
  try {
    return await getJSON(`${JARVIS_URL}/email/inbox`);
  } catch { return { messages: [] }; }
});

// ─── Apps ────────────────────────────────────────────────────────────────────

ipcMain.handle('get-apps', async () => {
  // Try backend first
  try {
    const data = await getJSON(`${JARVIS_URL}/api/automation/apps/list`);
    if (data?.apps?.length) return data;
  } catch {}
  // Fallback: scan Start Menu programs
  const apps = [];
  const startDirs = [];
  if (os.platform() === 'win32') {
    const common = path.join(process.env.ProgramData || 'C:\\ProgramData', 'Microsoft', 'Windows', 'Start Menu', 'Programs');
    const user = path.join(os.homedir(), 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs');
    startDirs.push(common, user);
  } else {
    startDirs.push('/usr/share/applications', path.join(os.homedir(), '.local', 'share', 'applications'));
  }
  for (const dir of startDirs) {
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const e of entries) {
        if (e.isFile() && (e.name.endsWith('.lnk') || e.name.endsWith('.desktop'))) {
          apps.push({ name: e.name.replace(/\.(lnk|desktop)$/,''), exec: e.name });
        }
      }
    } catch {}
  }
  if (apps.length) return { apps: apps.slice(0, 24) };
  // Ultimate fallback
  return { apps: [
    { name: 'Chrome', exec: 'chrome' },
    { name: 'VS Code', exec: 'code' },
    { name: 'Terminal', exec: 'cmd' },
    { name: 'Notepad', exec: 'notepad' },
    { name: 'Explorer', exec: 'explorer' },
    { name: 'Spotify', exec: 'spotify' },
  ]};
});

ipcMain.handle('open-app', async (_e, appName) => {
  try {
    if (os.platform() === 'win32') {
      spawn('cmd.exe', ['/c', 'start', '', appName], { shell: true });
    } else {
      spawn(appName, [], { shell: true, detached: true });
    }
    return true;
  } catch { return false; }
});

// ─── Terminal ────────────────────────────────────────────────────────────────

ipcMain.handle('open-terminal', () => {
  try {
    const cmd = os.platform() === 'win32' ? 'cmd.exe' : 'x-terminal-emulator';
    spawn(cmd, [], { detached: true, shell: true });
    return true;
  } catch { return false; }
});

ipcMain.handle('exec-command', async (_e, command) => {
  return new Promise((resolve) => {
    try {
      exec(command, { shell: true, timeout: 10000 }, (err, stdout, stderr) => {
        resolve({ stdout: stdout || '', stderr: stderr || '', error: err ? err.message : null });
      });
    } catch (e) {
      resolve({ stdout: '', stderr: '', error: e.message });
    }
  });
});

// ─── Image upload / customization ─────────────────────────────────────────────

ipcMain.handle('pick-image', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'Images', extensions: ['png', 'gif', 'jpg', 'jpeg', 'webp', 'svg'] }],
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle('get-dot-config', () => loadConfig());

ipcMain.handle('save-dot-config', (_e, cfg) => {
  saveConfig({ ...loadConfig(), ...cfg });
  return true;
});

// Dot config changes (from Customize panel)
ipcMain.on('apply-dot-cfg', (_e, cfg) => {
  if (dotWindow) dotWindow.webContents.send('apply-cfg', cfg);
  // Also forward bg/text to panel for theming
  if (panelWindow && panelWindow.webContents) {
    panelWindow.webContents.send('apply-cfg', cfg);
  }
  saveConfig({ ...loadConfig(), ...cfg });
});

// ─── System stats ─────────────────────────────────────────────────────────────
ipcMain.handle('get-sys-stats', async () => {
  try {
    const cpus = os.cpus();
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    // CPU: average of per-core load
    let totalIdle = 0, totalTick = 0;
    for (const cpu of cpus) {
      for (const type in cpu.times) totalTick += cpu.times[type];
      totalIdle += cpu.times.idle;
    }
    const cpuAvg = ((1 - totalIdle / totalTick) * 100).toFixed(0);
    const memUsed = ((totalMem - freeMem) / (1024 * 1024 * 1024)).toFixed(1);
    return { cpu: cpuAvg, mem: memUsed };
  } catch { return { cpu: '—', mem: '—' }; }
});

// ─── Sound volume ────────────────────────────────────────────────────────────
ipcMain.handle('get-sound-volume', () => {
  return loadConfig().soundVolume ?? 50;
});
ipcMain.handle('set-sound-volume', (_e, vol) => {
  saveConfig({ ...loadConfig(), soundVolume: vol });
});

// ─── Pick video file ─────────────────────────────────────────────────────────
ipcMain.handle('pick-video', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'Videos', extensions: ['mp4', 'mkv', 'mov', 'avi', 'webm'] }],
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

// ─── Channels / messages ─────────────────────────────────────────────────────
ipcMain.handle('get-channels', async () => {
  try {
    const data = await getJSON(`${JARVIS_URL}/api/channels`);
    if (data?.channels?.length) return { messages: data.channels.map(c => ({ name: c.name, preview: c.description || '', time: '' })) };
  } catch {}
  return { messages: [
    { name: 'JARVIS Assistant', preview: 'I am ready to help you', time: '' },
    { name: 'System Notifications', preview: 'All systems operational', time: '' },
  ]};
});

// ─── Tray ─────────────────────────────────────────────────────────────────────
function createTray() {
  const trayIcon = nativeImage.createEmpty();
  tray = new Tray(trayIcon);
  tray.setToolTip('JARVIS');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'JARVIS', enabled: false },
    { type: 'separator' },
    { label: 'Open Chat',              click: () => shell.openExternal(`${JARVIS_URL}/chat`) },
    { label: 'Understand Screen (Win+J)',   click: () => doScreenUnderstand() },
    { type: 'separator' },
    { label: 'Show Dot',  click: () => dotWindow?.show() },
    { label: 'Hide Dot',  click: () => dotWindow?.hide() },
    { type: 'separator' },
    { label: 'Quit JARVIS Dot', click: () => app.quit() },
  ]));
}

// ─── Backend auto-launch ──────────────────────────────────────────────────────
let backendProcess = null;

function launchBackend() {
  // Check if backend is already reachable
  getJSON(`${JARVIS_URL}/api/health`).then(() => {
    console.log('[JARVIS Dot] Backend already running.');
  }).catch(() => {
    console.log('[JARVIS Dot] Starting backend server...');
    const jarvisRoot = path.resolve(__dirname, '..');
    const python = process.platform === 'win32' ? 'python' : 'python3';
    backendProcess = spawn(python, ['jarvis.py', 'server', '--port', '8000'], {
      cwd: jarvisRoot,
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: false,
    });
    backendProcess.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
    backendProcess.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
    backendProcess.on('error', (err) => console.error('[JARVIS Dot] Backend spawn failed:', err.message));
    backendProcess.on('exit', (code) => console.log(`[JARVIS Dot] Backend exited (${code})`));
  });
}

// ─── App lifecycle ────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  launchBackend();
  createDotWindow();
  createPanelWindow();
  createTray();

  const hotkey = process.platform === 'darwin' ? 'Cmd+J' : 'Super+J';
  const ok = globalShortcut.register(hotkey, () => doScreenUnderstand());
  if (!ok) {
    console.warn(`[JARVIS] Could not register ${hotkey}. Trying Alt+J.`);
    globalShortcut.register('Alt+J', () => doScreenUnderstand());
  }
  console.log(`[JARVIS Dot] Running. ${hotkey} = understand screen. Backend: ${JARVIS_URL}`);
});

app.on('before-quit', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});

app.on('will-quit', () => globalShortcut.unregisterAll());
app.on('window-all-closed', e => e.preventDefault());
