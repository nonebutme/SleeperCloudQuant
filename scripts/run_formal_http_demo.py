"""Run the stdlib demo HTTP server for the formal local API shell."""

from __future__ import annotations

import argparse
from _project_bootstrap import ensure_project_root_on_sys_path



def main() -> None:
    parser = argparse.ArgumentParser(description="纯 API 开发调试服务；日常 Web 与 API 统一使用 8010")
    parser.add_argument("--developer-mode", action="store_true", help="显式启动独立 API 调试服务（8000）")
    args = parser.parse_args()
    if not args.developer_mode:
        parser.error("日常请双击根目录 启动系统.cmd；纯 API 开发测试须显式指定 --developer-mode")
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
