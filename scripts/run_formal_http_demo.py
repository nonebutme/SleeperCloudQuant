"""Run the stdlib demo HTTP server for the formal local API shell."""

from __future__ import annotations

from _project_bootstrap import ensure_project_root_on_sys_path



def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, create_http_server

    app = build_demo_app()
    server = create_http_server(app, host="127.0.0.1", port=8000)
    print("formal demo HTTP server listening on http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
