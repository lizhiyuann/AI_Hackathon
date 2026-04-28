"""进程管理能力"""
import sys
from typing import Dict, Any

from src.capabilities.base import BaseCapability
from src.agent.models import RiskLevel, Environment, CapabilityResult
from src.connector.local import LocalExecutor


def _to_markdown_table(headers: list, rows: list) -> str:
    """将表头和数据行转为Markdown表格"""
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join([":---:" for _ in headers]) + " |\n"
    for row in rows:
        md += "| " + " | ".join(str(c) for c in row) + " |\n"
    return md


class ProcessCapability(BaseCapability):
    """进程管理能力"""

    name = "process"
    description = "进程及端口状态查询"
    supported_actions = ["list", "search", "kill", "check_port", "check_service"]
    risk_level = RiskLevel.LOW

    def execute(self, action: str, parameters: Dict[str, Any], env: Environment, executor=None) -> CapabilityResult:
        executor = executor or LocalExecutor()
        is_windows = env.os_name == "Windows"

        if action == "list":
            return self._list_processes(executor, is_windows)
        elif action == "search":
            return self._search_process(parameters, executor, is_windows)
        elif action == "kill":
            return self._kill_process(parameters, executor, is_windows)
        elif action == "check_port":
            return self._check_port(parameters, executor, is_windows)
        elif action == "check_service":
            return self._check_service(parameters, executor, is_windows)
        else:
            return CapabilityResult(success=False, error=f"不支持的操作: {action}")

    def _list_processes(self, executor, is_windows: bool) -> CapabilityResult:
        """查看进程列表"""
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 15 @{N=\'进程名\';E={$_.Name}}, @{N=\'PID\';E={$_.Id}}, @{N=\'CPU(秒)\';E={[math]::Round($_.CPU,2)}}, @{N=\'内存(MB)\';E={[math]::Round($_.WorkingSet64/1MB,2)}} | ConvertTo-Csv -NoTypeInformation"'
        else:
            cmd = "ps aux --sort=-%mem 2>/dev/null || ps aux"
        result = executor.execute(cmd)
        output = self._format_process_list(result.output, is_windows)
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _search_process(self, params: Dict, executor, is_windows: bool) -> CapabilityResult:
        """搜索进程"""
        keyword = params.get("keyword", "")
        if not keyword:
            return CapabilityResult(success=False, error="请指定搜索关键词")
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Process | Where-Object {$_.Name -like \'*' + keyword + '*\'} | Select-Object -First 20 @{N=\'进程名\';E={$_.Name}}, @{N=\'PID\';E={$_.Id}}, @{N=\'CPU(秒)\';E={[math]::Round($_.CPU,2)}}, @{N=\'内存(MB)\';E={[math]::Round($_.WorkingSet64/1MB,2)}} | ConvertTo-Csv -NoTypeInformation"'
        else:
            cmd = f"ps aux | grep '{keyword}' | grep -v grep"
        result = executor.execute(cmd)
        if is_windows and result.output.strip().startswith('"'):
            output = self._parse_csv_output(result.output)
        else:
            output = result.output if result.output.strip() else f"未找到与 '{keyword}' 相关的进程"
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _kill_process(self, params: Dict, executor, is_windows: bool) -> CapabilityResult:
        """终止进程"""
        pid = params.get("pid", "")
        keyword = params.get("keyword", "")
        signal = params.get("signal", "")

        # 如果提供了关键词但没有 PID，先搜索进程
        if keyword and not pid:
            search_result = self._search_process(params, executor, is_windows)
            if search_result.success and search_result.output and "未找到" not in search_result.output:
                return CapabilityResult(
                    success=False,
                    error=f"请先确认要终止的进程，找到以下匹配进程：\n{search_result.output}\n\n请指定 PID 来终止进程",
                    risk_level=RiskLevel.HIGH,
                )
            return CapabilityResult(
                success=False,
                error=f"未找到与 '{keyword}' 相关的进程",
                risk_level=RiskLevel.HIGH,
            )

        if not pid:
            return CapabilityResult(success=False, error="请指定进程 PID 或进程名")

        # 校验 PID 是否为合法数字
        try:
            pid_int = int(pid)
            if pid_int <= 0:
                return CapabilityResult(success=False, error="PID 必须为正整数")
        except ValueError:
            return CapabilityResult(success=False, error=f"无效的 PID: {pid}")

        # 阻止终止 PID 1 (init)
        if pid_int == 1:
            return CapabilityResult(success=False, error="不允许终止 init 进程 (PID 1)")

        if is_windows:
            cmd = f"taskkill /PID {pid} /F 2>&1"
        else:
            kill_signal = f"-{signal} " if signal else ""
            cmd = f"kill {kill_signal}{pid} 2>&1"

        result = executor.execute(cmd)
        if result.success:
            return CapabilityResult(
                success=True,
                output=f"进程 {pid} 已终止",
                raw_output=result.output,
                commands_executed=[cmd],
                risk_level=RiskLevel.HIGH,
                verification_command=f"ps -p {pid} -o pid= 2>/dev/null || echo 'NOT_FOUND'" if not is_windows else f"tasklist /FI \"PID eq {pid}\" 2>nul",
            )

        error_msg = result.error or result.output or "终止进程失败"
        if "Operation not permitted" in error_msg or "不允许" in error_msg:
            error_msg = f"终止进程 {pid} 失败: 权限不足，可能需要 sudo 权限"
        elif "No such process" in error_msg:
            error_msg = f"终止进程 {pid} 失败: 进程不存在"
        else:
            error_msg = f"终止进程 {pid} 失败: {error_msg}"
        return CapabilityResult(
            success=False,
            error=error_msg,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.HIGH,
        )

    def _check_port(self, params: Dict, executor, is_windows: bool) -> CapabilityResult:
        """检查端口占用"""
        port = params.get("port", "")
        if not port:
            return CapabilityResult(success=False, error="请指定端口号")
        if is_windows:
            cmd = f'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, State, OwningProcess | ConvertTo-Csv -NoTypeInformation"'
        else:
            cmd = f"ss -tlnp 2>/dev/null | grep ':{port} ' || netstat -tlnp 2>/dev/null | grep ':{port} ' || echo 'Port {port} not found'"
        result = executor.execute(cmd)
        if is_windows and result.output.strip().startswith('"'):
            output = self._parse_csv_output(result.output)
        else:
            output = result.output if result.output.strip() else f"端口 {port} 未被占用"
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _check_service(self, params: Dict, executor, is_windows: bool) -> CapabilityResult:
        """检查服务状态"""
        service = params.get("service", "")
        if not service:
            return CapabilityResult(success=False, error="请指定服务名称")
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Service -Name \'*' + service + '*\' | Select-Object Name, DisplayName, Status | ConvertTo-Csv -NoTypeInformation"'
        else:
            cmd = f"systemctl status {service} 2>&1 | head -20"
        result = executor.execute(cmd)
        if is_windows and result.output.strip().startswith('"'):
            output = self._parse_csv_output(result.output)
        else:
            output = result.output
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _parse_csv_output(self, raw: str) -> str:
        """解析CSV输出为Markdown表格"""
        lines = [l.strip() for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return raw
        headers = [h.strip('"') for h in lines[0].split(',')]
        rows = []
        for line in lines[1:]:
            cells = [c.strip('"') for c in line.split(',')]
            rows.append(cells)
        return _to_markdown_table(headers, rows)

    def _format_process_list(self, raw: str, is_windows: bool) -> str:
        """格式化进程列表"""
        lines = raw.strip().split("\n")
        if not lines or not lines[0]:
            return "无法获取进程列表"

        if is_windows:
            # CSV格式解析
            if lines[0].strip().startswith('"'):
                return self._parse_csv_output(raw)
            # 纯文本格式
            headers = ["进程名", "PID", "内存使用"]
            rows = []
            for line in lines[:15]:
                parts = line.split()
                if len(parts) >= 2:
                    rows.append(parts[:3])
            return _to_markdown_table(headers, rows) if rows else raw
        else:
            # Linux ps aux格式
            headers = ["USER", "PID", "CPU%", "MEM%", "COMMAND"]
            rows = []
            for line in lines[1:16]:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    rows.append([parts[0], parts[1], parts[2], parts[3], parts[10][:40]])
            return _to_markdown_table(headers, rows) if rows else raw
