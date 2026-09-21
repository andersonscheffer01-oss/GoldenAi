#!/usr/bin/env sh
set -eu
echo "OS: $(uname -a)"
[ -r /etc/os-release ] && cat /etc/os-release
echo "CPU:"; getconf _NPROCESSORS_ONLN
echo "RAM:"; (free -h || true)
echo "DISK:"; df -h /
echo "PUBLIC IP:"; (curl -fsS https://api.ipify.org || echo unavailable)
echo; echo "LISTENING PORTS:"; (ss -lntup || netstat -an || true)
echo "DOCKER:"; (docker --version || true)
echo "COMPOSE:"; (docker compose version || true)
echo "PYTHON:"; (python3 --version || true)
echo "POSTGRESQL:"; (psql --version || true)
echo "FIREWALL:"; (ufw status || firewall-cmd --list-all || true)
