#!/usr/bin/env bash
# Shared helper: finds Python 3.12 or 3.13. Sets PYEXE and PYVER. Sourced by the other scripts.
PYEXE=""; PYVER=""
for cand in python3.13 python3.12 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    v=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
    case "$v" in 3.12|3.13) PYEXE="$cand"; PYVER="$v"; break;; esac
  fi
done
