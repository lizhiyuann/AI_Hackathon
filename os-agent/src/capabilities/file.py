"""文件和目录操作能力 - 支持多发行版"""
import re
import sys
from typing import Dict, Any

from src.capabilities.base import BaseCapability
from src.agent.models import RiskLevel, Environment, CapabilityResult
from src.connector.local import LocalExecutor
from src.utils.logger import log


class FileCapability(BaseCapability):
    """文件和目录操作能力"""

    name = "file"
    description = "文件和目录操作"
    supported_actions = ["list", "search", "view", "create_dir", "create_file", "delete", "copy", "move"]
    risk_level = RiskLevel.MEDIUM

    @staticmethod
    def _resolve_path(path: str) -> str:
        """将用户路径转为绝对路径

        - 以 / 或 ~ 或盘符开头 → 已是绝对路径，直接返回
        - . 或 ./ 开头 → 基于用户 home 目录
        - 其他 → 相对于用户 home 目录
        """
        import os
        if not path:
            return path
        path = path.strip()
        if path.startswith("/") or path.startswith("~") or (len(path) >= 2 and path[1] == ":"):
            return os.path.abspath(os.path.expanduser(path))
        if path == ".":
            return os.path.expanduser("~")
        if path.startswith("./"):
            return os.path.join(os.path.expanduser("~"), path[2:])
        # 用户说"project/aaa"，意思通常是 ~/project/aaa
        return os.path.abspath(os.path.join(os.path.expanduser("~"), path))

    def execute(self, action: str, parameters: Dict[str, Any], env: Environment, executor=None) -> CapabilityResult:
        """执行文件操作"""
        executor = executor or LocalExecutor()
        is_windows = env.os_name == "Windows"

        if action == "list":
            return self._list_directory(parameters, executor, env, is_windows)
        elif action == "search":
            return self._search_file(parameters, executor, env, is_windows)
        elif action == "view":
            return self._view_file(parameters, executor, env, is_windows)
        elif action == "create_dir":
            return self._create_dir(parameters, executor, env, is_windows)
        elif action == "create_file":
            return self._create_file(parameters, executor, env, is_windows)
        elif action == "delete":
            return self._delete_file(parameters, executor, env, is_windows)
        elif action == "copy":
            return self._copy_file(parameters, executor, env, is_windows)
        elif action == "move":
            return self._move_file(parameters, executor, env, is_windows)
        else:
            return CapabilityResult(success=False, error=f"不支持的操作: {action}")

    def _list_directory(self, params: Dict, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """列出目录内容"""
        path = self._resolve_path(params.get("path", "."))
        if is_windows:
            cmd = f'dir "{path}" 2>nul'
            result = executor.execute(cmd)
            if not result.success:
                return CapabilityResult(success=False, error=f"无法列出目录: {result.output}", commands_executed=[cmd], risk_level=RiskLevel.LOW)
            return CapabilityResult(
                success=True,
                output=f"目录 {path} 内容:\n\n{result.output}",
                raw_output=result.output,
                commands_executed=[cmd],
                risk_level=RiskLevel.LOW,
            )
        else:
            # Linux通用命令
            cmd = f'ls -la "{path}" 2>&1'
            result = executor.execute(cmd)
            if not result.success:
                return CapabilityResult(success=False, error=f"无法列出目录: {result.output}")
            return CapabilityResult(
                success=True,
                output=f"目录 {path} 内容:\n\n{self._format_ls_output(result.output)}",
                raw_output=result.output,
                commands_executed=[cmd],
                risk_level=RiskLevel.LOW,
            )

    def _search_file(self, params: Dict, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """搜索文件"""
        name = (
            params.get("name")
            or params.get("keyword")
            or params.get("pattern")
            or params.get("file_name")
            or ""
        )
        raw_input = params.get("raw_input", "")
        path = self._resolve_path(params.get("path", "."))

        # "查找 /tmp/a/b/c" —— 用户只给了路径没给文件名
        if not name and params.get("path"):
            name = params["path"].strip("/").rsplit("/", 1)[-1]
            # name 就是 path 末段 → 搜索上级目录
            if path.rstrip("/").endswith("/" + name):
                path = path.rstrip("/").rsplit("/", 1)[0] or "/"

        if not name:
            m = re.search(r"搜索\s*(?:名叫|叫做|叫|名为)?\s*[\"']?([^\s\"']+)", raw_input)
            if m:
                name = m.group(1)
        if not name:
            return CapabilityResult(success=False, error="请指定文件名")
        
        if is_windows:
            cmd = f'dir /s /b "{path}\*{name}*" 2>nul'
            timeout = 30
        else:
            from src.guardian.rules import SecurityRules
            rules = SecurityRules()
            max_results = rules.get_search_limit()
            cmd = f'find "{path}" -name "*{name}*" -type f 2>/dev/null | head -{max_results}'
            timeout = 30
        
        result = executor.execute(cmd, timeout=timeout)
        if not result.output.strip():
            return CapabilityResult(
                success=True,
                output=f"未找到匹配的文件: {name}",
                commands_executed=[cmd],
                risk_level=RiskLevel.LOW,
            )
        
        # 将搜索结果格式化为 Markdown 列表，避免路径挤在一行
        paths = [p for p in result.output.strip().split("\n") if p.strip()]
        list_text = "\n".join(f"- `{p}`" for p in paths)

        return CapabilityResult(
            success=True,
            output=f"搜索结果（共 {len(paths)} 个匹配）:\n\n{list_text}",
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _view_file(self, params: Dict, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """查看文件或目录内容"""
        path = self._resolve_path(params.get("path", ""))
        lines = params.get("lines", 50)
        if not path:
            return CapabilityResult(success=False, error="请指定文件路径")

        # 先检测路径类型
        check_cmd = f'test -d "{path}" && echo "IS_DIR" || (test -f "{path}" && echo "IS_FILE" || echo "NOT_FOUND")'
        check_result = executor.execute(check_cmd)
        path_type = check_result.output.strip() if check_result.success else ""

        if path_type == "NOT_FOUND":
            return CapabilityResult(
                success=False,
                error=f"路径不存在: {path}",
                commands_executed=[check_cmd],
                risk_level=RiskLevel.LOW,
            )

        if path_type == "IS_DIR":
            # 目录 → 用 ls -la 列出内容
            cmd = f'ls -la "{path}" 2>&1'
            result = executor.execute(cmd)
            if not result.success:
                return CapabilityResult(success=False, error=f"无法列出目录: {result.output}")
            return CapabilityResult(
                success=True,
                output=f"目录 {path} 内容:\n\n{self._format_ls_output(result.output)}",
                raw_output=result.output,
                commands_executed=[cmd],
                risk_level=RiskLevel.LOW,
            )

        # 文件 → 读取内容
        if is_windows:
            cmd = f'type "{path}" 2>nul'
            if lines:
                cmd = f'powershell -Command "Get-Content "{path}" -Head {lines}" 2>nul'
        else:
            if lines:
                cmd = f'head -n {lines} "{path}" 2>&1'
            else:
                cmd = f'cat "{path}" 2>&1'

        result = executor.execute(cmd)
        if not result.success:
            return CapabilityResult(success=False, error=f"无法读取文件: {result.output}")

        output = result.output
        max_chars = 5000
        if len(output) > max_chars:
            output = output[:max_chars] + f"\n\n... (已截断，仅显示前 {max_chars} 字符)"

        return CapabilityResult(
            success=True,
            output=f"文件 {path} 内容:\n\n{output}",
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _create_dir(self, params: Dict, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """创建目录"""
        raw = params.get("raw_input", "")
        name = params.get("name", "")
        path = params.get("path", "")
        
        if not path and name:
            path = name
        if not path and raw:
            import re
            # "创建一个11111的文件夹"
            m = re.search(r'(?:创建|新建|建个?|建一个?)\s*(?:一个?)?\s*["\']?([^\s"\'的这个]+?)["\']?\s*(?:的|这个)?\s*(?:文件夹|目录|folder)', raw)
            if m:
                path = m.group(1)
            else:
                # "创建文件夹11111"
                m = re.search(r'(?:创建|新建|建个?)\s*(?:一个?)?\s*(?:文件夹|目录|folder)\s*[叫名为]?\s*["\']?([^\s"\']+?)["\']?\s*$', raw)
                if m:
                    path = m.group(1)
        if not path:
            return CapabilityResult(success=False, error="请指定目录路径")
        
        path = self._resolve_path(path)
        if is_windows:
            cmd = f'mkdir "{path}" 2>&1'
        else:
            cmd = f'mkdir -p "{path}" 2>&1'
        
        result = executor.execute(cmd)
        if result.success:
            return CapabilityResult(
                success=True,
                output=f"目录已创建: {path}",
                commands_executed=[cmd],
                risk_level=RiskLevel.MEDIUM,
                verification_command=f'test -d "{path}" && echo "EXISTS" || echo "NOT_FOUND"',
            )
        else:
            return CapabilityResult(success=False, error=f"创建目录失败: {result.output}")

    def _create_file(self, params: Dict, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """创建文件"""
        path = params.get("path", "")
        content = params.get("content", "")
        if not path:
            return CapabilityResult(success=False, error="请指定文件路径")
        
        path = self._resolve_path(path)
        if is_windows:
            if content:
                cmd = f'echo {content} > "{path}" 2>&1'
            else:
                cmd = f'type nul > "{path}" 2>&1'
        else:
            if content:
                cmd = f'echo "{content}" > "{path}" 2>&1'
            else:
                cmd = f'touch "{path}" 2>&1'
        
        result = executor.execute(cmd)
        if result.success:
            if content:
                # 带内容的创建 → 验证时读取内容
                verify_cmd = f'test -f "{path}" && echo "EXISTS" && echo "---CONTENT_START---" && cat "{path}" && echo "---CONTENT_END---" || echo "NOT_FOUND"'
            else:
                verify_cmd = f'test -f "{path}" && echo "EXISTS" || echo "NOT_FOUND"'
            return CapabilityResult(
                success=True,
                output=f"文件已创建: {path}",
                commands_executed=[cmd],
                risk_level=RiskLevel.MEDIUM,
                verification_command=verify_cmd,
            )
        else:
            return CapabilityResult(success=False, error=f"创建文件失败: {result.output}", commands_executed=[cmd], risk_level=RiskLevel.MEDIUM)

    def _delete_file(self, params: Dict, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """删除文件或目录"""
        path = params.get("path", "")
        if not path:
            return CapabilityResult(success=False, error="请指定路径")

        path = self._resolve_path(path)
        # 安全检查
        protected_paths = ["/", "/etc", "/bin", "/sbin", "/usr", "/var", "C:\\", "C:\\Windows"]
        for protected in protected_paths:
            if path == protected or path.startswith(protected + "/") or path.startswith(protected + "\\"):
                return CapabilityResult(
                    success=False,
                    error=f"受保护的路径，禁止删除: {path}",
                    risk_level=RiskLevel.CRITICAL,
                )

        # 批量操作限制检查
        from src.guardian.rules import SecurityRules
        rules = SecurityRules()
        raw_input = params.get("raw_input", "")
        if rules.check_batch_limit(path) or rules.check_batch_limit(raw_input):
            return CapabilityResult(
                success=False,
                error=f"批量删除操作超出安全限制（上限 {rules.get_batch_limit()} 个）。"
                      f"请缩小操作范围，明确指定要删除的文件路径。",
                risk_level=RiskLevel.HIGH,
            )
        
        if is_windows:
            cmd = f'rmdir /s /q "{path}" 2>&1 || del /q "{path}" 2>&1'
        else:
            cmd = f'rm -rf "{path}" 2>&1'
        
        result = executor.execute(cmd)
        if result.success:
            return CapabilityResult(
                success=True,
                output=f"已删除: {path}",
                commands_executed=[cmd],
                risk_level=RiskLevel.HIGH,
                verification_command=f'test ! -e "{path}" && echo "DELETED" || echo "STILL_EXISTS"',
                verification_expect_success=False,
            )
        else:
            return CapabilityResult(success=False, error=f"删除失败: {result.output}")

    def _copy_file(self, params: Dict, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """复制文件"""
        source = self._resolve_path(params.get("source", ""))
        dest = self._resolve_path(params.get("dest", ""))
        if not source or not dest:
            return CapabilityResult(success=False, error="请指定源路径和目标路径")
        
        if is_windows:
            cmd = f'copy "{source}" "{dest}" 2>&1'
        else:
            # Linux通用
            cmd = f'cp -r "{source}" "{dest}" 2>&1'
        
        result = executor.execute(cmd)
        if result.success:
            return CapabilityResult(
                success=True,
                output=f"已复制: {source} -> {dest}",
                commands_executed=[cmd],
                risk_level=RiskLevel.MEDIUM,
            )
        else:
            return CapabilityResult(success=False, error=f"复制失败: {result.output}")

    def _move_file(self, params: Dict, executor, env: Environment, is_windows: bool) -> CapabilityResult:
        """移动文件"""
        source = self._resolve_path(params.get("source", ""))
        dest = self._resolve_path(params.get("dest", ""))
        if not source or not dest:
            return CapabilityResult(success=False, error="请指定源路径和目标路径")
        
        if is_windows:
            cmd = f'move "{source}" "{dest}" 2>&1'
        else:
            cmd = f'mv "{source}" "{dest}" 2>&1'
        
        result = executor.execute(cmd)
        if result.success:
            return CapabilityResult(
                success=True,
                output=f"已移动: {source} -> {dest}",
                commands_executed=[cmd],
                risk_level=RiskLevel.MEDIUM,
            )
        else:
            return CapabilityResult(success=False, error=f"移动失败: {result.output}")

    def _format_ls_output(self, raw: str, max_rows: int = 15) -> str:
        """格式化ls -la输出为Markdown表格"""
        lines = raw.strip().split("\n")
        table_lines = [
            "| 权限 | 链接数 | 所有者 | 所属组 | 大小 | 日期 | 文件名 |",
            "| --- | ---: | --- | --- | ---: | --- | --- |",
        ]
        count = 0
        perm_pattern = re.compile(r'^[dl-][rwxst-]{9}[+@]?')
        for line in lines:
            if not line.strip():
                continue
            parts = line.split()
            if not parts:
                continue
            if parts[0].startswith("total"):
                continue
            if count >= max_rows:
                table_lines.append(
                    "| ... | ... | ... | ... | ... | ... | 还有 "
                    f"{len(lines) - max_rows} 个条目未显示 |"
                )
                break
            if perm_pattern.match(parts[0]):
                # 标准 ls -la: perms links owner group size month day time/name
                if len(parts) >= 9:
                    perms = parts[0]
                    links = parts[1]
                    owner = parts[2]
                    group = parts[3]
                    size = parts[4]
                    date = " ".join(parts[5:8])
                    name = " ".join(parts[8:])
                elif len(parts) >= 6:
                    perms = parts[0]
                    links = parts[1] if len(parts) > 1 else "-"
                    owner = "-"
                    group = "-"
                    size = parts[2] if len(parts) > 2 else "-"
                    date = " ".join(parts[3:6]) if len(parts) >= 6 else "-"
                    name = " ".join(parts[6:]) if len(parts) > 6 else "-"
                else:
                    perms = parts[0]
                    links = "-"
                    owner = "-"
                    group = "-"
                    size = "-"
                    date = "-"
                    name = " ".join(parts[1:])
                table_lines.append(
                    f"| {perms} | {links} | {owner} | {group} | {size} | {date} | {name} |"
                )
                count += 1
            else:
                table_lines.append(f"| - | - | - | - | - | - | {line.strip()} |")
                count += 1
        return "\n".join(table_lines)
