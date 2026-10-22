#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "TLS setup failed at line $LINENO. Fix the error above and rerun." >&2' ERR
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo 'Run this script on macOS.' >&2; exit 1; }
command -v mkcert >/dev/null || { echo 'Install mkcert first: brew install mkcert' >&2; exit 1; }
ips=()
for interface in $(networksetup -listallhardwareports | awk '/Device:/ {print $2}'); do
  ip=$(ipconfig getifaddr "$interface" 2>/dev/null || true)
  [[ -z "$ip" ]] || ips+=("$ip")
done
[[ ${#ips[@]} -gt 0 ]] || { echo 'No LAN IPv4 address found. Connect to Wi-Fi first.' >&2; exit 1; }
umask 077
directory="$PWD/service/state/tls"
mkdir -p "$directory"
mkcert -install
mkcert -cert-file "$directory/mac.pem" -key-file "$directory/mac-key.pem" nivra.local localhost 127.0.0.1 ::1 "${ips[@]}"
port="${NIVRA_PORT:-8443}"
origin="https://${ips[0]}:$port"
origins="https://nivra.local:$port,https://localhost:$port,https://127.0.0.1:$port"
for ip in "${ips[@]}"; do origins="$origins,https://$ip:$port"; done
{
  printf 'export NIVRA_TLS_CERT=%q\n' "$directory/mac.pem"
  printf 'export NIVRA_TLS_KEY=%q\n' "$directory/mac-key.pem"
  printf 'export NIVRA_PORT=%q\n' "$port"
  printf 'export NIVRA_PUBLIC_ORIGIN=%q\n' "$origin"
  printf 'export NIVRA_ALLOWED_ORIGINS=%q\n' "${NIVRA_ALLOWED_ORIGINS:+$NIVRA_ALLOWED_ORIGINS,}$origins"
} > "$directory/mac-env.sh"
ca="$(mkcert -CAROOT)/rootCA.pem"
echo "Open $origin/wall after running bash scripts/start-mac.sh"
echo "CA certificate to transfer to phones: $ca"
echo 'Never share rootCA-key.pem or mac-key.pem.'
echo 'iPhone: install the certificate profile, then Settings > General > About > Certificate Trust Settings > enable full trust.'
echo 'Android: Settings > Security > Encryption & credentials > Install a certificate > CA certificate (wording varies).'
echo 'nivra.local only works if the network resolves that name; use the printed LAN IP otherwise.'
