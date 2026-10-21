"""Starts the ReelVault PC workspace.

Usage: python launcher/run_server.py [--data-dir DIR] [--port N] [--lan] [--no-browser]
Localhost only by default. LAN access is enabled from Settings (or --lan) and binds to all
interfaces while a middleware rejects any client outside private network ranges.
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reelvault import __version__  # noqa: E402
from reelvault.app import create_app  # noqa: E402
from reelvault.config import DEFAULT_PORT, default_data_dir  # noqa: E402
from reelvault.netutil import lan_ip  # noqa: E402
from reelvault.workspace import Workspace  # noqa: E402


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler = logging.handlers.RotatingFileHandler(log_dir / "reelvault.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = [handler, console]
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ReelVault PC workspace")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--lan", action="store_true", help="bind to all interfaces (private networks only)")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    ws = Workspace(data_dir)
    setup_logging(ws.paths.logs)
    log = logging.getLogger("reelvault")
    if ws.applied_migrations:
        log.info("applied schema migrations: %s", ws.applied_migrations)

    port = args.port or int(ws.setting("port") or DEFAULT_PORT)
    lan = args.lan or bool(ws.setting("lan_enabled", False)) or os.environ.get("REELVAULT_LAN") == "1"
    host = "0.0.0.0" if lan else "127.0.0.1"
    app = create_app(data_dir, port=port, lan_enabled=lan, workspace=ws)

    ip = lan_ip()
    print("=" * 64)
    print(f" ReelVault {__version__}")
    print(f" Data folder : {ws.paths.data_dir}")
    print(f" Media folder: {ws.media_dir()}")
    print(f" Workspace   : http://127.0.0.1:{port}/")
    if lan:
        print(f" LAN access  : ENABLED  ->  phone uses host {ip or '<your LAN IP>'} port {port}")
    else:
        print(" LAN access  : off (enable it in Settings so the phone can sync, then restart)")
    print("=" * 64, flush=True)

    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()

    import uvicorn
    try:
        uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)
    except OSError as e:
        print(f"Could not start on port {port}: {e}. Is ReelVault already running?")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
