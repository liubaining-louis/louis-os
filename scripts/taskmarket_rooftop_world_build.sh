#!/usr/bin/env bash
set -euo pipefail

TOOLS='/var/lib/louis-os/tools'
VENV="$TOOLS/taskmarket-video-venv"
OUT='/var/lib/louis-os/results/taskmarket-rooftop-world'
GEN='/tmp/taskmarket_rooftop_world_video.py'
FINAL='/tmp/world-of-base-rooftop-2030.mp4'
mkdir -p "$TOOLS" "$OUT"
rm -rf "$OUT/frames"
mkdir -p "$OUT/frames"

ensure_pkg() {
  local cmd="$1" pkg="$2"
  if command -v "$cmd" >/dev/null 2>&1; then return 0; fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq "$pkg"
}

ensure_pkg ffmpeg ffmpeg
ensure_pkg python3 python3
if ! python3 -m venv --help >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3-venv
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --disable-pip-version-check 'Pillow>=10,<12'

[[ -s "$GEN" ]] || { echo 'GENERATOR_MISSING'; exit 70; }
"$VENV/bin/python" "$GEN" --frames "$OUT/frames" --audio "$OUT/ambient.wav" | tee "$OUT/generator.log"

frame_count=$(find "$OUT/frames" -maxdepth 1 -type f -name 'frame_*.png' | wc -l)
echo "FRAME_COUNT=$frame_count"
[[ "$frame_count" -eq 180 ]] || { echo 'FRAME_COUNT_MISMATCH'; exit 71; }
[[ -s "$OUT/ambient.wav" ]] || { echo 'AUDIO_MISSING'; exit 72; }

# Encode a square 1080p MP4 with an original stereo soundscape normalized near -17 LUFS.
ffmpeg -hide_banner -loglevel warning -y \
  -framerate 30 -i "$OUT/frames/frame_%04d.png" \
  -i "$OUT/ambient.wav" \
  -vf 'scale=1080:1080:flags=lanczos,format=yuv420p' \
  -af 'loudnorm=I=-17:LRA=7:TP=-2' \
  -t 6 -r 30 \
  -c:v libx264 -preset medium -crf 18 -movflags +faststart \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -metadata title='Rooftop Commons, 2030' \
  -metadata comment='Lane 2 — rooftop gardens above the city. Style: mid-century gouache cut-paper diorama. Original procedural world and sound design.' \
  -shortest "$FINAL"

[[ -s "$FINAL" ]] || { echo 'FINAL_MP4_MISSING'; exit 73; }
bytes=$(wc -c < "$FINAL")
echo "FINAL_BYTES=$bytes"
[[ "$bytes" -le 60000000 ]] || { echo 'FINAL_TOO_LARGE'; exit 74; }

ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -of json "$FINAL" > "$OUT/ffprobe.json"
cat "$OUT/ffprobe.json"

python3 - "$OUT/ffprobe.json" "$FINAL" <<'PY'
import json, os, subprocess, sys
p, final = sys.argv[1:]
d=json.load(open(p))
fmt=d.get('format') or {}
streams=d.get('streams') or []
try: duration=float(fmt.get('duration') or 0)
except Exception: duration=0
video=[s for s in streams if s.get('codec_type')=='video']
audio=[s for s in streams if s.get('codec_type')=='audio']
print(f'DURATION_SECONDS={duration:.3f}')
print('VIDEO_STREAMS='+str(len(video)))
print('AUDIO_STREAMS='+str(len(audio)))
if not (5.0 <= duration <= 10.0): raise SystemExit('DURATION_GATE_FAIL')
if len(video)!=1: raise SystemExit('VIDEO_STREAM_GATE_FAIL')
if len(audio)<1: raise SystemExit('AUDIO_STREAM_GATE_FAIL')
v=video[0]
if int(v.get('width') or 0) < 1080 or int(v.get('height') or 0) < 1080: raise SystemExit('RESOLUTION_GATE_FAIL')
if v.get('codec_name') not in {'h264','hevc','av1','vp9'}: raise SystemExit('VIDEO_CODEC_GATE_FAIL')
print('RESOLUTION='+str(v.get('width'))+'x'+str(v.get('height')))
print('VIDEO_CODEC='+str(v.get('codec_name')))
print('AUDIO_CODEC='+str(audio[0].get('codec_name')))
print('AUDIO_CHANNELS='+str(audio[0].get('channels')))
print('VALIDATION=PASS')
print('SHA256='+subprocess.check_output(['sha256sum', final], text=True).split()[0])
PY

# Loudness evidence is diagnostic; encoding already applied EBU R128 loudnorm.
set +e
ffmpeg -hide_banner -nostats -i "$FINAL" -filter_complex ebur128=peak=true -f null - 2> "$OUT/ebur128.log"
set -e
tail -n 25 "$OUT/ebur128.log" || true

# Keep the final artifact; remove bulky frame intermediates after validation.
rm -rf "$OUT/frames"
echo "FINAL_MP4=$FINAL"
echo 'BUILD_AND_VALIDATION=PASS'
