"""结果格式化模块 - 将执行结果转换为自然语言"""
from src.agent.models import CapabilityResult, AgentResponse
from src.utils.logger import log


class ResponseFormatter:
    """响应格式化器"""

    def format(self, result: CapabilityResult) -> AgentResponse:
        """格式化执行结果"""
        if not result.success:
            return AgentResponse(
                success=False,
                message=self._format_error(result),
                commands_executed=result.commands_executed,
                risk_level=result.risk_level,
            )

        return AgentResponse(
            success=True,
            message=result.output,
            commands_executed=result.commands_executed,
            risk_level=result.risk_level,
        )

    def _format_error(self, result: CapabilityResult) -> str:
        """格式化错误信息"""
        error_msg = result.error or "执行失败"
        return f"执行出错: {error_msg}"

    def format_disk_info(self, raw_output: str) -> str:
        """格式化磁盘信息"""
        lines = raw_output.strip().split("\n")
        if len(lines) < 2:
            return raw_output

        header = lines[0]
        result = "磁盘使用情况:\n\n"

        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 6:
                filesystem = parts[0]
                size = parts[1]
                used = parts[2]
                avail = parts[3]
                use_percent = parts[4]
                mount = parts[5]
                result += f"  {mount}\n"
                result += f"    文件系统: {filesystem}\n"
                result += f"    总容量: {size} | 已用: {used} | 可用: {avail} | 使用率: {use_percent}\n\n"

        return result

    def format_process_info(self, raw_output: str) -> str:
        """格式化进程信息"""
        lines = raw_output.strip().split("\n")
        if len(lines) < 2:
            return raw_output

        result = "进程列表 (按内存使用排序):\n\n"
        result += f"  {'PID':<8} {'USER':<10} {'CPU%':<8} {'MEM%':<8} {'COMMAND':<20}\n"
        result += "  " + "-" * 60 + "\n"

        for line in lines[1:11]:  # 只显示前10个
            parts = line.split(None, 10)
            if len(parts) >= 11:
                pid = parts[1]
                user = parts[0]
                cpu = parts[2]
                mem = parts[3]
                cmd = parts[10][:20]
                result += f"  {pid:<8} {user:<10} {cpu:<8} {mem:<8} {cmd:<20}\n"

        return result
