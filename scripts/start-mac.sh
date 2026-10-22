#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "NIVRA setup failed at line $LINENO. Fix the error above and rerun." >&2' ERR
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo 'Run this launcher on macOS.' >&2; exit 1; }
for tool in uv node npm; do
  command -v "$tool" >/dev/null || { echo "Missing $tool. Install it before continuing (brew install uv node)." >&2; exit 1; }
done
if [[ ! -x service/.venv/bin/python ]]; then
  [[ ! -d service/.venv ]] || { echo 'service/.venv is not a Mac venv. Move it aside before rerunning.' >&2; exit 1; }
  uv venv --python 3.11 service/.venv
fi
service/.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 11), "Use a Python 3.11 venv"'
uv pip install --python service/.venv/bin/python -r service/requirements-mac.txt
export NIVRA_PERSON_MODEL="${NIVRA_PERSON_MODEL:-rtmo}"
export NIVRA_FIGHT_MODEL="${NIVRA_FIGHT_MODEL:-x3d}"
export NIVRA_DEVICE="${NIVRA_DEVICE:-auto}"
export PYTORCH_ENABLE_MPS_FALLBACK=1
service/.venv/bin/python service/prepare_models.py --experimental
node scripts/prepare-models.mjs
npm ci
npm run build
if [[ -f service/state/tls/mac-env.sh ]]; then
  # Generated locally by https-mac.sh; contains paths/origins, never credentials.
  source service/state/tls/mac-env.sh
fi
echo "NIVRA: ${NIVRA_PUBLIC_ORIGIN:-http://localhost:${NIVRA_PORT:-8765}}/wall"
echo 'Keep this terminal open. Ctrl+C stops this service.'
cd service
exec .venv/bin/python -m nivra.server
