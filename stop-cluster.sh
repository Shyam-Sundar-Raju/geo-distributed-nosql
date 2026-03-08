#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <machine1|machine2|machine3|all>"
  exit 1
fi

ROLE="$1"

stop_nodes() {
  docker rm -f "$@" >/dev/null 2>&1 || true
}

case "$ROLE" in
  machine1)
    stop_nodes mumbai chennai bangalore
    ;;
  machine2)
    stop_nodes virginia newyork wasdc
    ;;
  machine3)
    stop_nodes set3a set3b set3c
    ;;
  all)
    stop_nodes mumbai chennai bangalore virginia newyork wasdc set3a set3b set3c
    ;;
  *)
    echo "Invalid role: $ROLE"
    echo "Valid roles: machine1, machine2, machine3, all"
    exit 1
    ;;
esac

echo "[OK] Stopped containers for role: $ROLE"
