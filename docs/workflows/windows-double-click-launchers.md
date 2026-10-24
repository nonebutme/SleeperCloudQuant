# 统一入口：Windows 双击启动与停止

日常仅使用根目录 `启动系统.cmd`，统一访问 `http://127.0.0.1:8010/`。数据中心、因子、策略数据集、策略与回测、报告及设置均由页面导航进入。

内部调用链：`启动系统.cmd` → `scripts/start_sleepercloudquant.ps1` → `scripts/run_formal_web_demo.py` → Web/API。`index.html` 是服务加载的页面，无需单独打开。

## 日常使用

- 双击项目根目录的 `启动系统.cmd`：
  - 若 8010 已是 SleeperCloudQuant，只打开浏览器，不重复启动。
  - 若 8010 被其他程序占用，停止并提示错误，不会结束其他程序。
  - 否则在后台启动 Web/API，健康检查通过后打开 `http://127.0.0.1:8010/`。
  - 页面、`/api/system/health` 和进程身份均核对后才报告就绪。旧服务不满足健康检查时提示停止后重启。
- 双击项目根目录的 `停止系统.cmd`：
  - 仅当 8010 的监听进程和页面都能确认为 SleeperCloudQuant 时才停止。
  - 关闭浏览器页面不会停止后端；需要使用停止入口。

## 日志与进程记录

- 标准输出：`var/runtime/web-8010.stdout.log`
- 错误输出：`var/runtime/web-8010.stderr.log`
- 实际监听 PID：`var/runtime/web-8010.pid`

## 诊断参数

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_sleepercloudquant.ps1 -NoBrowser
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/stop_sleepercloudquant.ps1 -CheckOnly
```

开发诊断可使用 `-Port` 临时更换端口；日常不需要此参数。

## 开发候选

仅开发测试时显式运行：

```powershell
python scripts/run_formal_http_demo.py --developer-mode
python scripts/run_strategy_studio_web_demo.py --developer-mode
```

两者分别使用 8000、8020，缺少开发参数即退出。候选代码保留，主导航不展示候选入口；从主服务误开候选页面会回到正式策略页。候选页提供“返回正式系统”链接。
