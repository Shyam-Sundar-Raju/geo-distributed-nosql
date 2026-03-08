#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
	echo "Usage: $0 <machine1|machine2|machine3|all>"
	exit 1
fi

./stop-cluster.sh "$1"