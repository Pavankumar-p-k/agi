#!/usr/bin/env bash
# ============================================================================
# export_mp4.sh — render the JS canvas video into a real .mp4 file.
#
# Pipeline (the "code renders the video" approach, fully offline):
#   1. headless Chrome renders ?strip=<start>,<count> pages — each page is a
#      grid of 12 consecutive frames, all drawn by the same deterministic
#      renderFrame(ctx, t)
#   2. one screenshot per strip  (40 screenshots for 480 frames @ 30fps)
#   3. PIL slices each strip back into single frames
#   4. ffmpeg assembles the frames into output.mp4
#
# Usage:  bash export_mp4.sh
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
PY=python
OUT="$SCRIPT_DIR/out"
STRIPS="$OUT/strips"
FRAMES="$OUT/frames"

FPS=30
DURATION=16
TOTAL=$((FPS * DURATION))          # 480
PER_STRIP=12                       # 4 cols x 3 rows grid in index.html
STRIP_W=$((1280 * 4))              # 5120
STRIP_H=$((720 * 3))               # 2160
STRIPS_N=$((TOTAL / PER_STRIP))    # 40

FILE_URL="file:///$(cygpath -m "$SCRIPT_DIR")/index.html"
# Chrome's process cwd is not the bash cwd — screenshot paths must be absolute
SHOT() { cygpath -w "$1"; }

echo "== 1/4 rendering $STRIPS_N strips ($TOTAL frames) with headless Chrome =="
mkdir -p "$STRIPS" "$FRAMES"
rm -f "$STRIPS"/strip_*.png "$FRAMES"/frame_*.png

for s in $(seq 0 $((STRIPS_N - 1))); do
  start=$((s * PER_STRIP))
  idx=$(printf '%03d' "$s")
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --window-size="$STRIP_W,$STRIP_H" --virtual-time-budget=4000 \
    --screenshot="$(SHOT "$STRIPS/strip_$idx.png")" \
    "${FILE_URL}?strip=${start},${PER_STRIP}" 2>/dev/null
  echo "   strip $idx  (frames $start-$((start + PER_STRIP - 1)))"
done

echo "== 2/4 slicing strips into single frames (PIL) =="
"$PY" - "$STRIPS" "$FRAMES" "$TOTAL" "$PER_STRIP" <<'PYEOF'
import sys, os
from PIL import Image
strips_dir, frames_dir, total, per = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
COLS, ROWS = 4, 3
written = 0
for name in sorted(os.listdir(strips_dir)):
    if not name.startswith('strip_'):
        continue
    start = int(name.split('_')[1].split('.')[0]) * per
    img = Image.open(os.path.join(strips_dir, name)).convert('RGB')
    tw, th = 1280, 720
    for i in range(per):
        f = start + i
        if f >= total:
            break
        col, row = i % COLS, i // COLS
        img.crop((col * tw, row * th, (col + 1) * tw, (row + 1) * th)) \
           .save(os.path.join(frames_dir, 'frame_%05d.png' % f))
        written += 1
print('   frames written:', written)
PYEOF

echo "== 3/4 sanity check: frames must not be blank =="
"$PY" - "$FRAMES" "$TOTAL" <<'PYEOF'
import sys, os
from PIL import Image
import math
frames_dir, total = sys.argv[1], int(sys.argv[2])
sample = [0, total // 4, total // 2, (3 * total) // 4, total - 1]
for f in sample:
    img = Image.open(os.path.join(frames_dir, 'frame_%05d.png' % f)).convert('L')
    px = list(img.getdata())
    n = len(px)
    mean = sum(px) / n
    std = math.sqrt(sum((p - mean) ** 2 for p in px) / n)
    bright = sum(1 for p in px if p > 60)
    # the dark opening starfield is legitimate content, not a blank frame:
    # pass only if there is real structure (non-flat pixels AND bright content)
    ok = std > 2.0 and bright > 500
    print('   frame %3d  mean=%6.2f std=%6.2f bright=%5d  %s' % (f, mean, std, bright, 'OK' if ok else 'BLANK?'))
    if not ok:
        sys.exit('frame %d looks blank — renderer problem' % f)
PYEOF

echo "== 4/4 assembling mp4 with ffmpeg =="
ffmpeg -y -framerate "$FPS" -i "$FRAMES/frame_%05d.png" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart \
  "$SCRIPT_DIR/output.mp4" 2>/dev/null

# keep the pipeline clean: drop intermediate strips/frames, keep previews
rm -rf "$STRIPS" "$FRAMES"
for t in 1.0 5.5 9.8 14.0; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --window-size=1280,720 --virtual-time-budget=3000 \
    --screenshot="$(SHOT "$OUT/preview_t${t}.png")" \
    "${FILE_URL}?still=${t}" 2>/dev/null
done

echo "== done =="
ls -la "$SCRIPT_DIR/output.mp4" "$OUT"/preview_*.png
