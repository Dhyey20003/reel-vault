#!/usr/bin/env bash
# Restores a database backup made by upgrade_v2.sh and checks out the v1 code.
# Usage: bash scripts/rollback_v2.sh <path to pre-v2-*.db> [--data-dir DIR]
cd "$(dirname "$0")/.." || exit 1
[ -n "${1:-}" ] || { echo "usage: $0 <backup.db> [--data-dir DIR]"; ls ~/Library/Application\ Support/ReelVault/Data/backups/pre-v2-*.db 2>/dev/null; exit 1; }
B="$1"; shift
.venv/bin/python tools/upgrade_db.py rollback --backup "$B" "$@" || exit 1
echo "Database restored. Now switch the code back to v1 and restart:"
echo "   git checkout claude/intelligent-lovelace-pfg5bg   (or unzip ReelVault_v1.0.0.zip over this folder)"
echo "   bash scripts/run_server.sh"
