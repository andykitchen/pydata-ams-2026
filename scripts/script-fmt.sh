#!/bin/bash

set -euo pipefail

for arg in "$@"; do
	sed -E '/\[\w+\]/b;s/^[^[:space:]]+/@fmt &/' "$arg" | fmt -p "@fmt " | sed -E 's/^@fmt //' > "${arg}.tmp"
	mv "${arg}.tmp" "$arg"
done
