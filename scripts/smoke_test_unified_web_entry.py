"""本机临时端口验证正式 Web/API 同源、候选跳转及开发入口限制；不装配业务库。"""
from _project_bootstrap import ensure_project_root_on_sys_path
ensure_project_root_on_sys_path()

from contextlib import redirect_stderr
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import run_formal_http_demo
import run_formal_web_demo
import run_strategy_studio_web_demo


class ProbeServer(ThreadingHTTPServer):
    def __init__(self, address, handler):
        assert address == ('127.0.0.1', 8010)
        super().__init__(('127.0.0.1', 0), handler)

    def serve_forever(self):
        worker = threading.Thread(target=lambda: super(ProbeServer, self).serve_forever(poll_interval=0.05))
        worker.start()
        def get(path):
            connection = HTTPConnection('127.0.0.1', self.server_port, timeout=5)
            try:
                connection.request('GET', path)
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()
        try:
            status, _, body = get('/')
            assert status == 200 and b'SleeperCloudQuant' in body
            assert b'data-page="market"' in body and b'data-page="backtest"' in body
            assert b'data-page="factor"' in body and b'data-page="ai"' in body
            assert b'data-route-page="reporting"' in body and b'data-route-page="report-management"' in body
            status, _, body = get('/api/system/health')
            health = json.loads(body)
            assert status == 200 and health['entrypoint'] == 'main-web' and health['status'] == 'ready'
            status, _, body = get('/api/entry-probe')
            assert status == 200 and json.loads(body) == {'probe': 'same-origin'}
            for path in ('/strategy-studio.html', '/./strategy-studio.html', '/strategy-studio.html?from=old-link'):
                status, headers, _ = get(path)
                assert status == 302 and headers['Location'] == '/?page=backtest'
            assert get('/?page=backtest')[0] == 200
            assert get('/../manifest.md')[0] == 404
        finally:
            self.shutdown()
            worker.join(5)


def main():
    for module in (run_formal_http_demo, run_strategy_studio_web_demo):
        with patch('sys.argv', [module.__name__]), patch.object(module, 'ensure_project_root_on_sys_path') as bootstrap:
            with redirect_stderr(io.StringIO()) as stderr:
                try:
                    module.main()
                except SystemExit as error:
                    assert error.code == 2
                else:
                    raise AssertionError('development server started without explicit mode')
            assert '--developer-mode' in stderr.getvalue()
            bootstrap.assert_not_called()
    app = SimpleNamespace(routes=[])
    with patch('app.runtime.build_demo_app', return_value=app), patch('app.runtime.dispatch_request', return_value=(200, {'probe':'same-origin'})), \
            patch.object(run_formal_web_demo, 'ThreadingHTTPServer', ProbeServer), patch.dict('os.environ', {'SCQ_WEB_PORT':'8010'}):
        run_formal_web_demo.main()
    print('unified web entry: same-origin Web/API, readiness, candidate redirect and developer opt-in passed')


if __name__ == '__main__':
    main()
