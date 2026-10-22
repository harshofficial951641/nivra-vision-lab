#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"
if [[ ! -x service/.venv/bin/python ]]; then
  print 'NIVRA needs its local installation completed on this Mac.'
  exit 1
fi
service/.venv/bin/python scripts/deploy/local_host_service.py start
print 'Opening NIVRA. Join the same Wi-Fi router on this Mac and your iPhones. Internet is not needed.'
open http://127.0.0.1:8870/local
