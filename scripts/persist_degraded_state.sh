#!/usr/bin/env bash
set -euo pipefail
git config user.name 'louis-os[bot]'
git config user.email 'louis-os[bot]@users.noreply.github.com'
test -d results/degraded || exit 0
# Only the isolated runtime state is written; canonical revenue is untouched.
git add -f results/degraded/
if ! git diff --cached --quiet; then
  git commit -m 'Record VM-independent Louis runtime evidence'
fi
for attempt in 1 2 3; do
  if git pull --rebase origin main && git push origin HEAD:main; then
    exit 0
  fi
  git rebase --abort || true
done
echo 'Degraded state checkpoint failed; external submission must remain blocked.' >&2
exit 1
