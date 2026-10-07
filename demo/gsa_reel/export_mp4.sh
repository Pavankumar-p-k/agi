#!/usr/bin/env bash
# ============================================================================
# export_mp4.sh — render the GSA reel (code-rendered) into gsa_reel.mp4
# WITH the synthesized soundtrack.
#
#   1. headless Chrome renders ?strip=<start>,6 pages (2x3 grid @1080x1920)
#   2. one screenshot per strip  (150 screenshots for 900 frames @ 30fps)
#   3. PIL slices strips into single 1080x1920 frames
#   4. ffmpeg assembles video + muxes soundtrack.wav -> gsa_reel.mp4
#
# Usage: bash export_mp4.sh
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
PY=python
OUT="$SCRIPT_DIR/out"
STRIPS="$OUT/strips"
FRAMES="$OUT/frames"

FPS=30
DURATION=30
TOTAL=$((FPS * DURATION))        # 900
PER_STRIP=6                      # 2 cols x 3 rows
STRIP_W=$((1080 * 2))            # 2160
STRIP_H=$((1920 * 3))            # 5760
STRIPS_N=$((TOTAL / PER_STRIP))  # 150

FILE_URL="file:///$(cygpath -m "$SCRIPT_DIR")/index.html"
SHOT() { cygpath -w "$1"; }      # Chrome needs absolute Windows paths

echo "== 1/4 rendering $STRIPS_N strips ($TOTAL frames) =="
mkdir -p "$STRIPS" "$FRAMES"
rm -f "$STRIPS"/strip_*.png "$FRAMES"/frame_*.png

for s in $(seq 0 $((STRIPS_N - 1))); do
  start=$((s * PER_STRIP))
  idx=$(printf '%03d' "$s")
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --window-size="$STRIP_W,$STRIP_H" --virtual-time-budget=5000 \
    --screenshot="$(SHOT "$STRIPS/strip_$idx.png")" \
    "${FILE_URL}?strip=${start},${PER_STRIP}" 2>/dev/null
  if (( s % 10 == 0 )); then echo "   strip $idx  (frames $start-$((start+PER_STRIP-1)))"; fi
done

echo "== 2/4 slicing strips into 1080x1920 frames (PIL) =="
"$PY" - "$STRIPS" "$FRAMES" "$TOTAL" "$PER_STRIP" <<'PYEOF'
import sys, os
from PIL import Image
strips_dir, frames_dir = sys.argv[1], sys.argv[2]
total, per = int(sys.argv[3]), int(sys.argv[4])
COLS, ROWS, TW, TH = 2, 3, 1080, 1920
written = 0
for name in sorted(os.listdir(strips_dir)):
    if not name.startswith('strip_'):
        continue
    start = int(name.split('_')[1].split('.')[0]) * per
    img = Image.open(os.path.join(strips_dir, name)).convert('RGB')
    for i in range(per):
        f = start + i
        if f >= total:
            break
        col, row = i % COLS, i // COLS
        img.crop((col*TW, row*TH, (col+1)*TW, (row+1)*TH)) \
           .save(os.path.join(frames_dir, 'frame_%05d.png' % f))
        written += 1
print('   frames written:', written)
PYEOF

echo "== 3/4 sanity check: sampled frames must not be blank =="
"$PY" - "$FRAMES" "$TOTAL" <<'PYEOF'
import sys, os, math
from PIL import Image
frames_dir, total = sys.argv[1], int(sys.argv[2])
sample = [0, total // 6, total // 3, total // 2, (2 * total) // 3, (5 * total) // 6, total - 1]
fail = False
for f in sample:
    img = Image.open(os.path.join(frames_dir, 'frame_%05d.png' % f)).convert('L')
    px = list(img.getdata())
    n = len(px)
    mean = sum(px) / n
    std = math.sqrt(sum((p - mean) ** 2 for p in px) / n)
    bright = sum(1 for p in px if p > 60)
    ok = std > 2.0 and bright > 500
    print('   frame %3d  mean=%6.2f std=%6.2f bright=%6d  %s' % (f, mean, std, bright, 'OK' if ok else 'BLANK?'))
    fail = fail or not ok
sys.exit(1 if fail else 0)
PYEOF

echo "== 4/4 assembling mp4 + muxing soundtrack =="
ffmpeg -y -framerate "$FPS" -i "$FRAMES/frame_%05d.png" \
  -i "$SCRIPT_DIR/soundtrack.wav" \
  -c:v libx264 -pix_fmt yuv420p -crf 19 -preset medium -movflags +faststart \
  -c:a aac -b:a 192k -shortest \
  "$SCRIPT_DIR/gsa_reel.mp4" 2>/dev/null

rm -rf "$STRIPS" "$FRAMES"

echo "== previews =="
for t in 1.5 6.5 13.0 21.0 27.5; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --window-size=1080,1920 --virtual-time-budget=3000 \
    --screenshot="$(SHOT "$OUT/preview_t${t}.png")" \
    "${FILE_URL}?still=${t}" 2>/dev/null
done

echo "== done =="
ls -la "$SCRIPT_DIR/gsa_reel.mp4" "$OUT"/preview_*.png
