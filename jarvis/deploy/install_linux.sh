#!/usr/bin/env sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute como root apenas para preparar usuario, firewall e diretorios." >&2
  exit 1
fi

install -d -m 0750 -o jarvis -g jarvis /opt/golden-jarvis/data /opt/golden-jarvis/uploads /opt/golden-jarvis/backups /opt/golden-jarvis/logs /opt/golden-jarvis/deploy
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 8780/tcp
ufw deny 5432/tcp
ufw deny 11434/tcp
echo "Diretorios e regras Jarvis preparados. Revise e proteja a porta SSH antes de ativar o firewall."
