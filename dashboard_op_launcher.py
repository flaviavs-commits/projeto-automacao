from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn


def _open_dashboard(url: str, delay_seconds: float) -> None:
    time.sleep(max(0.0, delay_seconds))
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Central OP de Mensagens - FC VIP",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host do servidor local")
    parser.add_argument("--port", type=int, default=8766, help="Porta do servidor local")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Nao abre navegador automaticamente",
    )
    args = parser.parse_args()

    dashboard_url = f"http://{args.host}:{args.port}/dashboard/op"
    if not args.no_browser:
        thread = threading.Thread(
            target=_open_dashboard,
            args=(dashboard_url, 1.2),
            daemon=True,
        )
        thread.start()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
