"""系统信息能力 - 支持多发行版"""
import sys
from typing import Dict, Any

from src.capabilities.base import BaseCapability
from src.agent.models import RiskLevel, Environment, CapabilityResult
from src.connector.local import LocalExecutor
from src.utils.logger import log


def _to_markdown_table(headers: list, rows: list) -> str:
    """将表头和数据行转为Markdown表格"""
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join([":---:" for _ in headers]) + " |\n"
    for row in rows:
        md += "| " + " | ".join(str(c) for c in row) + " |\n"
    return md


class SystemCapability(BaseCapability):
    """系统信息查询能力 - 支持多发行版命令适配"""

    name = "system"
    description = "系统基本信息查询"
    supported_actions = ["info", "uptime", "memory", "cpu", "network"]
    risk_level = RiskLevel.LOW

    def execute(self, action: str, parameters: Dict[str, Any], env: Environment, executor=None) -> CapabilityResult:
        executor = executor or LocalExecutor()
        
        if action == "info":
            return self._system_info(executor, env)
        elif action == "uptime":
            return self._uptime(executor, env)
        elif action == "memory":
            return self._memory(executor, env)
        elif action == "cpu":
            return self._cpu(executor, env)
        elif action == "network":
            return self._network(executor, env)
        else:
            return CapabilityResult(success=False, error=f"不支持的操作: {action}")

    def _system_info(self, executor, env: Environment) -> CapabilityResult:
        """查看系统信息"""
        is_windows = env.os_name == "Windows"
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-CimInstance Win32_OperatingSystem | Select-Object @{N=\'操作系统\';E={$_.Caption}}, @{N=\'版本\';E={$_.Version}}, @{N=\'架构\';E={$_.OSArchitecture}}, @{N=\'构建号\';E={$_.BuildNumber}} | ConvertTo-Csv -NoTypeInformation"'
            result = executor.execute(cmd)
            output = self._parse_csv_output(result.output)
        else:
            cmd = self.get_command("info", env=env)
            if not cmd:
                return CapabilityResult(success=False, error="无法获取系统信息命令")
            result = executor.execute(cmd)
            output = f"```\n{result.output}\n```"
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _uptime(self, executor, env: Environment) -> CapabilityResult:
        """查看运行时间"""
        cmd = self.get_command("uptime", env=env)
        if not cmd:
            return CapabilityResult(success=False, error="无法获取运行时间命令")
        
        result = executor.execute(cmd)
        if result.output.strip():
            headers = ["项目", "信息"]
            rows = [["运行时间", result.output.strip()]]
            output = _to_markdown_table(headers, rows)
        else:
            output = "无法获取运行时间"
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _memory(self, executor, env: Environment) -> CapabilityResult:
        """查看内存使用"""
        is_windows = env.os_name == "Windows"
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-CimInstance Win32_OperatingSystem | Select-Object @{N=\'总内存(GB)\';E={[math]::Round($_.TotalVisibleMemorySize/1MB,2)}}, @{N=\'可用(GB)\';E={[math]::Round($_.FreePhysicalMemory/1MB,2)}}, @{N=\'已用(GB)\';E={[math]::Round(($_.TotalVisibleMemorySize-$_.FreePhysicalMemory)/1MB,2)}} | ConvertTo-Csv -NoTypeInformation"'
            result = executor.execute(cmd)
            output = self._parse_csv_output(result.output)
        else:
            cmd = "free -h"
            result = executor.execute(cmd)
            output = self._format_memory_linux(result.output)
        
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _cpu(self, executor, env: Environment) -> CapabilityResult:
        """查看CPU状态"""
        is_windows = env.os_name == "Windows"
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-CimInstance Win32_Processor | Select-Object @{N=\'名称\';E={$_.Name}}, @{N=\'核心数\';E={$_.NumberOfCores}}, @{N=\'逻辑处理器\';E={$_.NumberOfLogicalProcessors}}, @{N=\'最大频率(MHz)\';E={$_.MaxClockSpeed}} | ConvertTo-Csv -NoTypeInformation"'
            result = executor.execute(cmd)
            output = self._parse_csv_output(result.output)
        else:
            cmd = self.get_command("cpu", env=env)
            if not cmd:
                return CapabilityResult(success=False, error="无法获取CPU命令")
            result = executor.execute(cmd)
            output = f"```\n{result.output}\n```"
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _network(self, executor, env: Environment) -> CapabilityResult:
        """查看网络配置"""
        is_windows = env.os_name == "Windows"
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike \'*Loopback*\'} | Select-Object @{N=\'网卡\';E={$_.InterfaceAlias}}, @{N=\'IP地址\';E={$_.IPAddress}} | ConvertTo-Csv -NoTypeInformation"'
            result = executor.execute(cmd)
            output = self._parse_csv_output(result.output)
        else:
            cmd = self.get_command("network", env=env)
            if not cmd:
                return CapabilityResult(success=False, error="无法获取网络命令")
            result = executor.execute(cmd)
            output = f"```\n{result.output}\n```"
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

    def _format_memory_linux(self, raw: str) -> str:
        """格式化Linux内存信息"""
        lines = raw.strip().split("\n")
        if len(lines) < 2:
            return f"```\n{raw}\n```"

        headers = ["指标", "总计", "已用", "可用", "共享", "缓存", "可用"]
        rows = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 7:
                rows.append(parts[:7])
        return _to_markdown_table(headers, rows) if rows else f"```\n{raw}\n```"
