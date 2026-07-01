/**
 * electron/preload.js  — JARVIS Dot context bridge
 *
 * Exposes a controlled API to both renderers via contextBridge.
 * Replaces require('electron').ipcRenderer directly.
 * Security: contextIsolation=true, nodeIntegration=false
 */
const { contextBridge, ipcRenderer } = require('electron');

const ALLOWED_SEND = new Set([
  'open-panel', 'panel-close', 'dot-voice-trigger', 'open-jarvis-dashboard',
  'apply-dot-cfg', 'resize-dot', 'window-drag', 'save-dot-lock',
  'panel-resize', 'screen-understand', 'panel-ask-followup', 'move-dot-to',
]);

const ALLOWED_INVOKE = new Set([
  'get-dot-config', 'get-sys-stats', 'home-dir', 'list-dir', 'get-drives',
  'get-music-status', 'music-play', 'music-pause', 'music-next', 'music-prev', 'music-volume',
  'pick-video', 'get-stocks', 'get-news', 'get-mails', 'get-channels',
  'get-apps', 'open-app', 'exec-command', 'get-sound-volume', 'set-sound-volume',
  'pick-image', 'get-activities', 'get-activity-counts', 'get-activity-tree',
  'get-activity-summary', 'pause-activity', 'resume-activity', 'cancel-activity',
]);

const ALLOWED_ON = new Set([
  'set-state', 'panel-closed', 'apply-cfg', 'open-panel', 'show-answer',
]);

contextBridge.exposeInMainWorld('jarvis', {
  send(ch, ...args) {
    if (ALLOWED_SEND.has(ch)) {
      ipcRenderer.send(ch, ...args);
    }
  },
  invoke(ch, ...args) {
    if (ALLOWED_INVOKE.has(ch)) {
      return ipcRenderer.invoke(ch, ...args);
    }
    return Promise.reject(new Error(`IPC channel "${ch}" not allowed`));
  },
  on(ch, fn) {
    if (ALLOWED_ON.has(ch)) {
      const cb = (_event, ...args) => fn(...args);
      ipcRenderer.on(ch, cb);
      return () => ipcRenderer.removeListener(ch, cb);
    }
  },
});
