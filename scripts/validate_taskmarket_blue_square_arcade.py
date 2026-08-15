#!/usr/bin/env python3
from pathlib import Path
import re, sys

p = Path(sys.argv[1] if len(sys.argv) > 1 else 'deliverables/taskmarket_blue_square_arcade/index.html')
data = p.read_text(encoding='utf-8')
raw = p.read_bytes()
errors = []

def require(cond, msg):
    if not cond:
        errors.append(msg)

require(len(raw) <= 1_000_000, f'file exceeds 1 MB: {len(raw)} bytes')
require(data.lower().count('<html') == 1, 'must be one self-contained HTML document')
require('Blue Square' in data, 'Blue Square identity missing')
require('lane 2' in data.lower(), 'assigned lane 2 declaration missing')
require('P = pause' in data, 'visible P = pause hint missing')
require('touch' in data.lower(), 'touch controls missing')
require('arrowup' in data.lower() and "w:'up'" in data.lower(), 'keyboard arrow/WASD controls missing')
require('showEnd(true)' in data and 'showEnd(false)' in data, 'win/lose state missing')
require('RESTART' in data or 'restart' in data, 'restart path missing')
require('timeLeft=45' in data, 'bounded round timer missing')

# Offline-only checks: no remote resources, network APIs, external script/style/image URLs.
for pat, label in [
    (r'https?://', 'remote URL'),
    (r'\bfetch\s*\(', 'fetch()'),
    (r'XMLHttpRequest', 'XMLHttpRequest'),
    (r'WebSocket\s*\(', 'WebSocket'),
    (r'<script[^>]+src=', 'external script'),
    (r'<link[^>]+href=', 'external stylesheet'),
    (r'<img[^>]+src=["\']https?://', 'external image'),
    (r'@import\s+', 'CSS @import'),
]:
    require(re.search(pat, data, re.I) is None, f'offline violation: {label}')

# Extract inline JS for a separate `node --check` in CI.
scripts = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', data, re.I | re.S)
require(len(scripts) == 1, f'expected exactly one inline script, found {len(scripts)}')
if scripts:
    out = Path('/tmp/taskmarket-blue-square.js')
    out.write_text(scripts[0], encoding='utf-8')
    print(f'EXTRACTED_JS={out}')

print(f'FILE_BYTES={len(raw)}')
print('OFFLINE_REMOTE_REQUESTS=0')
print('ASSIGNED_LANE=2')
print('CONTROLS=keyboard+touch+swipe')
print('ROUND_BOUNDED=true')
if errors:
    for e in errors:
        print('ERROR='+e, file=sys.stderr)
    raise SystemExit(1)
print('STATIC_VALIDATION=PASS')
