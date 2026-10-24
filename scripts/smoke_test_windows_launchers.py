"""Static safety contract for the Windows double-click launchers."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    start_cmd = (root / "启动系统.cmd").read_text(encoding="utf-8")
    stop_cmd = (root / "停止系统.cmd").read_text(encoding="utf-8")
    start_script = (root / "scripts" / "start_sleepercloudquant.ps1").read_text(encoding="utf-8")
    stop_script = (root / "scripts" / "stop_sleepercloudquant.ps1").read_text(encoding="utf-8")

    assert "start_sleepercloudquant.ps1" in start_cmd
    assert "stop_sleepercloudquant.ps1" in stop_cmd
    assert "run_formal_web_demo.py" in start_script
    assert "Get-ListenerProcessIds" in start_script
    assert "netstat -ano -p tcp" in start_script
    assert "Test-SleeperCloudQuantPage" in start_script
    assert "-WindowStyle Hidden" in start_script
    assert "Start-Process $webUrl" in start_script
    assert "SCQ_WEB_PORT" in start_script
    assert "listener PID(s)" in start_script
    assert "Multiple verified SleeperCloudQuant instances" in start_script
    assert "CheckOnly" in stop_script
    assert 'CommandLine -notmatch "run_formal_web_demo\\.py"' in stop_script
    assert "isExpectedCommand -and $isExpectedPage" in stop_script
    assert "Stop-Process -Id $processIds" in stop_script
    assert "Stop-Process -Name python" not in stop_script

    print("Windows double-click launcher smoke passed")


if __name__ == "__main__":
    main()
