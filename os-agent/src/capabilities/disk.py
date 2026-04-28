"""磁盘管理能力 - 支持多发行版"""
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


class DiskCapability(BaseCapability):
    """磁盘管理能力"""

    name = "disk"
    description = "磁盘使用情况监测与分析"
    supported_actions = ["check_usage", "check_inode", "check_io", "check_mount"]
    risk_level = RiskLevel.LOW

    def execute(self, action: str, parameters: Dict[str, Any], env: Environment, executor=None) -> CapabilityResult:
        """执行磁盘管理操作"""
        executor = executor or LocalExecutor()
        is_windows = env.os_name == "Windows"

        if action == "check_usage":
            return self._check_usage(executor, env, is_windows)
        elif action == "check_inode":
            return self._check_inode(executor, env, is_windows)
        elif action == "check_io":
            return self._check_io(executor, env, is_windows)
        elif action == "check_mount":
            return self._check_mount(executor, env, is_windows)
        else:
            return CapabilityResult(success=False, error=f"不支持的操作: {action}")

    def _check_usage(self, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """查看磁盘使用率"""
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-PSDrive -PSProvider FileSystem | Select-Object @{N=\'盘符\';E={$_.Name}}, @{N=\'已用(GB)\';E={[math]::Round($_.Used/1GB,2)}}, @{N=\'可用(GB)\';E={[math]::Round($_.Free/1GB,2)}}, @{N=\'总计(GB)\';E={[math]::Round(($_.Used+$_.Free)/1GB,2)}} | ConvertTo-Csv -NoTypeInformation"'
            result = executor.execute(cmd)
            output = self._parse_csv_output(result.output, "磁盘使用情况")
        else:
            cmd = "df -h"
            result = executor.execute(cmd)
            output = self._parse_df_output(result.output)
        
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _check_inode(self, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """查看inode使用情况"""
        if is_windows:
            return CapabilityResult(
                success=True,
                output="inode查询仅在Linux系统上支持。Windows使用NTFS文件系统，不需要inode管理。",
                commands_executed=[],
                risk_level=RiskLevel.LOW,
            )
        
        cmd = "df -i"
        result = executor.execute(cmd)
        lines = result.output.strip().split('\n')
        if len(lines) >= 2:
            headers = lines[0].split()
            rows = [line.split() for line in lines[1:] if line.strip()]
            output = _to_markdown_table(headers, rows)
        else:
            output = result.output
        return CapabilityResult(
            success=result.success,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _check_io(self, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """查看磁盘IO状态"""
        if is_windows:
            cmd = 'typeperf "\\PhysicalDisk(*)\\Disk Bytes/sec" -sc 1 2>nul'
            result = executor.execute(cmd)
            return CapabilityResult(
                success=True,
                output=f"```\n{result.output}\n```" if result.output.strip() else "磁盘IO监控不可用",
                raw_output=result.output,
                commands_executed=[cmd],
                risk_level=RiskLevel.LOW,
            )
        
        cmd = "iostat -x 1 1 2>/dev/null"
        result = executor.execute(cmd)
        
        if result.return_code != 0 or "command not found" in result.output.lower():
            cmd = "cat /proc/diskstats 2>/dev/null || echo 'IO信息不可用'"
            result = executor.execute(cmd)
        
        return CapabilityResult(
            success=True,
            output=f"```\n{result.output}\n```" if result.output.strip() else "磁盘IO监控不可用",
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _check_mount(self, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """查看挂载点"""
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-PSDrive -PSProvider FileSystem | Select-Object @{N=\'盘符\';E={$_.Name}}, @{N=\'描述\';E={$_.Description}}, @{N=\'根路径\';E={$_.Root}} | ConvertTo-Csv -NoTypeInformation"'
        else:
            cmd = "mount 2>/dev/null | grep '^/dev/' | column -t 2>/dev/null || mount | grep '^/dev/'"
        
        result = executor.execute(cmd)
        if is_windows and result.output.strip().startswith('"'):
            output = self._parse_csv_output(result.output, "挂载点信息")
        else:
            output = f"```\n{result.output}\n```"
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _parse_csv_output(self, raw: str, title: str = "") -> str:
        """解析CSV输出为Markdown表格"""
        lines = [l.strip() for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return raw

        headers = [h.strip('"') for h in lines[0].split(',')]
        rows = []
        for line in lines[1:]:
            cells = [c.strip('"') for c in line.split(',')]
            rows.append(cells)

        prefix = f"**{title}**\n\n" if title else ""
        return prefix + _to_markdown_table(headers, rows)

    def _parse_df_output(self, raw: str) -> str:
        """解析Linux df -h输出"""
        lines = raw.strip().split("\n")
        if len(lines) < 2:
            return f"```\n{raw}\n```"

        headers = ["文件系统", "容量", "已用", "可用", "使用率", "挂载点"]
        rows = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 6:
                rows.append(parts[:6])
        return _to_markdown_table(headers, rows)
