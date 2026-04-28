"""用户管理能力"""
import random
import string
from typing import Dict, Any

from src.capabilities.base import BaseCapability
from src.agent.models import RiskLevel, Environment, CapabilityResult
from src.connector.local import LocalExecutor


def _hash_password_sha512(password: str) -> str:
    """在本地生成 SHA-512 密码哈希，兼容 Linux /etc/shadow 标准格式

    优先级：crypt 模块 > mkpasswd 命令 > openssl 命令
    """
    # 方法1：Python crypt 模块（Linux 标准，Python 3.12 及以下可用）
    try:
        import crypt
        salt = crypt.mksalt(crypt.METHOD_SHA512)
        return crypt.crypt(password, salt)
    except (ImportError, AttributeError):
        pass

    # 方法2：mkpasswd 命令（大多数 Linux 发行版预装）
    import subprocess as _sp
    try:
        result = _sp.run(
            ["mkpasswd", "-m", "sha-512", password],
            capture_output=True, timeout=5
        )
        if result.returncode == 0 and result.stdout:
            hashed = result.stdout.decode().strip()
            if hashed.startswith("$6$"):
                return hashed
    except (FileNotFoundError, _sp.TimeoutExpired):
        pass

    # 方法3：openssl passwd -6 命令
    try:
        result = _sp.run(
            ["openssl", "passwd", "-6", "-stdin"],
            input=password.encode(), capture_output=True, timeout=5
        )
        if result.returncode == 0 and result.stdout:
            hashed = result.stdout.decode().strip()
            if hashed.startswith("$6$"):
                return hashed
    except (FileNotFoundError, _sp.TimeoutExpired):
        pass

    # 所有方法都不可用时，返回一个会提示错误的哈希
    import secrets
    import hashlib
    salt = secrets.token_hex(8)
    fallback = hashlib.sha512((password + salt).encode()).hexdigest()[:16]
    return f'$6${salt}${fallback}'


def _to_markdown_table(headers: list, rows: list) -> str:
    """将表头和数据行转为Markdown表格"""
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join([":---:" for _ in headers]) + " |\n"
    for row in rows:
        md += "| " + " | ".join(str(c) for c in row) + " |\n"
    return md


def _validate_username(username: str) -> str:
    """校验用户名合法性，防止命令注入。返回错误消息，空字符串表示合法。"""
    import re
    if not username:
        return "用户名不能为空"
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_-]{0,31}$', username):
        return f"用户名 '{username}' 不合法：仅允许字母、数字、下划线和连字符，且以字母或下划线开头"
    return ""


class UserCapability(BaseCapability):
    """用户管理能力"""

    name = "user"
    description = "用户账号管理"
    supported_actions = ["list", "info", "create", "delete", "modify"]
    risk_level = RiskLevel.MEDIUM

    def execute(self, action: str, parameters: Dict[str, Any], env: Environment, executor=None) -> CapabilityResult:
        executor = executor or LocalExecutor()
        is_windows = env.os_name == "Windows"

        if action == "list":
            return self._list_users(executor, is_windows)
        elif action == "info":
            return self._user_info(parameters, executor, is_windows, env)
        elif action == "create":
            return self._create_user(parameters, executor, is_windows)
        elif action == "delete":
            return self._delete_user(parameters, executor, is_windows)
        elif action == "modify":
            return self._modify_password(parameters, executor, is_windows, env)
        else:
            return CapabilityResult(success=False, error=f"不支持的操作: {action}")

    def _list_users(self, executor, is_windows: bool) -> CapabilityResult:
        """查看用户列表"""
        if is_windows:
            cmd = 'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-LocalUser | Select-Object Name, Enabled, LastLogon | ConvertTo-Csv -NoTypeInformation"'
        else:
            cmd = "cat /etc/passwd | grep -v nologin | grep -v false"
        result = executor.execute(cmd)
        output = self._format_user_list(result.output, is_windows)
        return CapabilityResult(
            success=True,
            output=output,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.LOW,
        )

    def _user_info(self, params: Dict, executor, is_windows: bool, env=None) -> CapabilityResult:
        """查看用户信息 — 完整收集，不做关键词二次判断

        设计原则：
        - LLM 已经判断了意图（action="info"），代码层信任这个结果
        - LLM 没返回 username → 查当前用户（通过 executor 在目标机器上 whoami）
        - sudo 状态是用户信息的一部分，始终收集
        """
        username = params.get("username", "")

        # 如果 LLM 没返回 username，通过 executor 在目标机器上获取当前执行用户
        # 不用关键词判断，不依赖本地环境变量
        if not username:
            whoami_result = executor.execute("whoami")
            if whoami_result.success and whoami_result.output:
                username = whoami_result.output.strip()
            elif env and env.current_user:
                username = env.current_user
            else:
                import os
                username = os.environ.get("USER", os.environ.get("USERNAME", ""))
            if not username:
                return CapabilityResult(success=False, error="无法确定当前用户，请指定用户名")

        # 对于 root 用户，信息中自动包含 sudo 状态
        # 对于非 root 用户，也会检查 sudo 权限并附在结果中
        sudo_info = self._collect_sudo_status(executor, username, env)

        if is_windows:
            cmd = f'powershell -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-LocalUser -Name {username} | Select-Object Name, Enabled, LastLogon, Description | ConvertTo-Csv -NoTypeInformation"'
            result = executor.execute(cmd)
            if result.output.strip().startswith('"'):
                output = self._parse_csv_output(result.output)
            else:
                output = result.output
            return CapabilityResult(
                success=True, output=output, raw_output=result.output,
                commands_executed=[cmd], risk_level=RiskLevel.LOW,
            )

        # 收集完整用户信息
        commands = []
        parts = {}

        # 1. 基本信息 (id)
        cmd_id = f"id {username} 2>&1"
        r = executor.execute(cmd_id)
        commands.append(cmd_id)
        if "no such user" in r.output.lower() or not r.success:
            return CapabilityResult(
                success=False,
                error=f"用户 {username} 不存在",
                commands_executed=commands,
                risk_level=RiskLevel.LOW,
            )
        parts["id"] = r.output

        # 2. passwd 条目（包含家目录、shell 等）
        cmd_passwd = f"getent passwd {username} 2>&1"
        r2 = executor.execute(cmd_passwd)
        commands.append(cmd_passwd)
        if r2.success and r2.output:
            fields = r2.output.strip().split(":")
            if len(fields) >= 7:
                parts["home"] = fields[5]
                parts["shell"] = fields[6]

        # 3. 用户组信息
        cmd_groups = f"groups {username} 2>&1"
        r3 = executor.execute(cmd_groups)
        commands.append(cmd_groups)
        if r3.success:
            parts["groups"] = r3.output

        # 4. 最近登录
        cmd_last = f"last -n 3 {username} 2>/dev/null | head -4"
        r4 = executor.execute(cmd_last)
        commands.append(cmd_last)
        if r4.success and r4.output:
            parts["last_login"] = r4.output

        # 5. 密码状态（需 sudo）
        cmd_pw = f"passwd -S {username} 2>/dev/null"
        r5 = executor.execute(cmd_pw)
        commands.append(cmd_pw)
        if r5.success and r5.output:
            pw_fields = r5.output.strip().split()
            if len(pw_fields) >= 2:
                pw_status_map = {"P": "已设置密码", "L": "已锁定", "NP": "无密码"}
                parts["pw_status"] = pw_status_map.get(pw_fields[1], pw_fields[1])

        # 6. 账号过期时间
        cmd_expire = f"chage -l {username} 2>/dev/null | grep '密码过期' || chage -l {username} 2>/dev/null | grep 'Password expires'"
        r6 = executor.execute(cmd_expire)
        commands.append(cmd_expire)
        if r6.success and r6.output:
            parts["pw_expire"] = r6.output.strip().split(":")[-1].strip() if ":" in r6.output else r6.output.strip()

        # 7. 家目录大小
        home_dir = parts.get("home", "")
        if home_dir:
            cmd_du = f"du -sh {home_dir} 2>/dev/null"
            r7 = executor.execute(cmd_du)
            commands.append(cmd_du)
            if r7.success and r7.output:
                parts["home_size"] = r7.output.split("\t")[0]

        # 格式化为 Markdown
        lines = [f"| 项目 | 值 |", f"| :--- | :--- |"]
        lines.append(f"| 用户名 | **{username}** |")
        if "pw_status" in parts:
            lines.append(f"| 密码状态 | {parts['pw_status']} |")
        if "id" in parts:
            id_parts = parts["id"]
            import re
            uid_m = re.search(r'uid=(\d+)', id_parts)
            gid_m = re.search(r'gid=(\d+)\(([^)]+)\)', id_parts)
            if uid_m:
                lines.append(f"| UID | {uid_m.group(1)} |")
            if gid_m:
                lines.append(f"| 主组 | {gid_m.group(2)} (GID: {gid_m.group(1)}) |")
        if "groups" in parts:
            lines.append(f"| 所属组 | {parts['groups'].split(':',1)[-1].strip() if ':' in parts['groups'] else parts['groups'].strip()} |")
        if "home" in parts:
            lines.append(f"| 家目录 | `{parts['home']}` |")
        if "shell" in parts:
            lines.append(f"| 默认Shell | `{parts['shell']}` |")
        if "home_size" in parts:
            lines.append(f"| 家目录大小 | {parts['home_size']} |")
        if "last_login" in parts:
            last_clean = parts["last_login"].strip().replace("\n", " | ")
            lines.append(f"| 最近登录 | {last_clean[:80]} |")
        if "pw_expire" in parts:
            lines.append(f"| 密码过期 | {parts['pw_expire']} |")

        # 附加 sudo 权限状态（始终收集，是用户信息的一部分）
        if sudo_info:
            lines.append(f"| 权限状态 | {sudo_info['status']} |")

        output = "\n".join(lines)

        # 附加 sudo 提示
        if sudo_info and sudo_info.get("tip"):
            output += f"\n\n> {sudo_info['tip']}"

        return CapabilityResult(
            success=True, output=output, raw_output=str(parts),
            commands_executed=commands, risk_level=RiskLevel.LOW,
        )

    @staticmethod
    def _collect_sudo_status(executor, username: str, env=None) -> dict:
        """收集指定用户的 sudo 权限状态（通过 executor 在目标机器上执行）

        返回 dict，包含 status 和 tip 字段；不需要 sudo 权限时也可能返回空 dict。
        """
        result = {"status": "", "tip": ""}
        is_root = (username == "root")

        if is_root:
            result["status"] = "root 用户，拥有最高管理员权限"
            result["tip"] = "无需 sudo 密码，可直接执行所有管理操作。"
            return result

        # 检查所属组
        groups_result = executor.execute(f"groups {username} 2>&1")
        groups_str = groups_result.output if groups_result.success and groups_result.output else ""
        in_sudo_group = "sudo" in groups_str.lower() or "wheel" in groups_str.lower()

        # 检查是否能免密 sudo
        sudo_n_result = executor.execute("sudo -n true 2>&1")
        has_nopasswd = sudo_n_result.success

        if in_sudo_group and has_nopasswd:
            result["status"] = "有 sudo 权限（免密）"
            result["tip"] = "可直接执行管理操作，无需输入密码。"
        elif in_sudo_group:
            result["status"] = "有 sudo 权限（需要密码）"
            result["tip"] = "执行管理操作时需要 sudo 密码。"
        else:
            result["status"] = "没有 sudo 权限"
            result["tip"] = "无法执行需要管理员权限的操作（如创建用户、删除用户）。"

        return result

    def _create_user(self, params: Dict, executor, is_windows: bool) -> CapabilityResult:
        """创建用户"""
        username = params.get("username", "")
        if not username:
            return CapabilityResult(success=False, error="请指定用户名")
        err = _validate_username(username)
        if err:
            return CapabilityResult(success=False, error=err)

        # 优先使用用户指定的密码，没有则生成随机密码
        user_password = params.get("password", "")
        if user_password:
            password = user_password
        else:
            import random
            import string
            chars = string.ascii_letters + string.digits
            password = ''.join(random.choices(chars, k=12))

        if is_windows:
            cmd = f"net user {username} /add 2>&1"
            set_pw_cmd = f"net user {username} {password} 2>&1"
            result = executor.execute(cmd)
            if result.success:
                pw_result = executor.execute(set_pw_cmd)
                if pw_result.success:
                    if user_password:
                        output = f"用户 {username} 创建成功\n密码: {password}"
                    else:
                        output = f"用户 {username} 创建成功\n初始密码: {password}"
                else:
                    output = f"用户 {username} 创建成功，但设置密码失败: {pw_result.error or pw_result.output}"
                return CapabilityResult(
                    success=True, output=output, raw_output=result.output,
                    commands_executed=[cmd, set_pw_cmd], risk_level=RiskLevel.HIGH,
                    verification_command=f"net user {username}",
                )
        else:
            # Linux: 用 useradd -p 一次性完成创建+设置密码（只用一次 sudo）
            hashed = _hash_password_sha512(password)
            cmd = f"sudo useradd -m -s /bin/bash -p '{hashed}' {username} 2>&1"
            result = executor.execute(cmd)
            if result.success:
                if user_password:
                    output = f"用户 {username} 创建成功\n密码: {password}"
                else:
                    output = f"用户 {username} 创建成功\n初始密码: {password}"
                return CapabilityResult(
                    success=True, output=output, raw_output=result.output,
                    commands_executed=[cmd], risk_level=RiskLevel.HIGH,
                    verification_command=f"id {username}",
                )

        error_msg = result.error or result.output or "权限不足或用户已存在"
        if "sudo" in error_msg.lower() or "permission" in error_msg.lower() or "超时" in error_msg:
            error_msg = f"创建用户失败: {error_msg}\n提示：请在页面左上角点击「设置 sudo 密码」后重试"
        else:
            error_msg = f"创建用户失败: {error_msg}"
        return CapabilityResult(
            success=False, output=error_msg, error=error_msg,
            raw_output=result.output, commands_executed=[cmd], risk_level=RiskLevel.HIGH,
        )

    def _delete_user(self, params: Dict, executor, is_windows: bool) -> CapabilityResult:
        """删除用户"""
        username = params.get("username", "")
        if not username:
            return CapabilityResult(success=False, error="请指定用户名")
        err = _validate_username(username)
        if err:
            return CapabilityResult(success=False, error=err)
        if username == "root" or username.lower() == "administrator":
            return CapabilityResult(success=False, error=f"不允许删除 {username} 用户")
        if is_windows:
            cmd = f"net user {username} /delete 2>&1"
        else:
            cmd = f"sudo userdel {username} 2>&1"
        result = executor.execute(cmd)
        if result.success:
            verify_cmd = f"id {username} 2>&1" if not is_windows else f"net user {username} 2>&1"
            return CapabilityResult(
                success=True,
                output=f"用户 {username} 已删除",
                raw_output=result.output,
                commands_executed=[cmd],
                risk_level=RiskLevel.CRITICAL,
                verification_command=verify_cmd,
                verification_expect_success=False,
            )
        error_msg = result.error or result.output or "用户不存在或权限不足"
        return CapabilityResult(
            success=False,
            output=f"删除用户失败: {error_msg}",
            error=f"删除用户失败: {error_msg}",
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.CRITICAL,
        )

    def _modify_password(self, params: Dict, executor, is_windows: bool, env=None) -> CapabilityResult:
        """修改用户密码"""
        username = params.get("username", "")
        new_password = params.get("new_password") or params.get("password") or ""

        # 兜底：如果 LLM 没返回 username（不应该发生），从 env 获取当前用户
        if not username and env and env.current_user:
            username = env.current_user

        if not username:
            return CapabilityResult(success=False, error="请指定用户名")

        err = _validate_username(username)
        if err:
            return CapabilityResult(success=False, error=err)

        if not new_password:
            return CapabilityResult(success=False, error="请指定新密码")

        if username in ("root", "administrator"):
            return CapabilityResult(success=False, error=f"不允许修改 {username} 的密码")

        # 先检查用户是否存在
        if not is_windows:
            check_cmd = f"id {username} 2>&1"
            check_result = executor.execute(check_cmd)
            if not check_result.success or "no such user" in check_result.output.lower():
                return CapabilityResult(
                    success=False,
                    error=f"用户 {username} 不存在，请先创建用户或检查用户名是否正确",
                    commands_executed=[check_cmd],
                    risk_level=RiskLevel.HIGH,
                )

        if is_windows:
            cmd = f'net user {username} {new_password} 2>&1'
        else:
            # 用 usermod -p 修改密码（命令行参数传哈希，避免 stdin 冲突）
            # chpasswd 从 stdin 读数据，会和 sudo -S 的 stdin 密码注入冲突
            # usermod -p 直接接收命令行参数，与 _wrap_sudo 完全兼容
            hashed = _hash_password_sha512(new_password)
            escaped_hash = hashed.replace("'", "'\\''")
            cmd = f"sudo usermod -p '{escaped_hash}' {username} 2>&1"

        result = executor.execute(cmd)
        if result.success:
            return CapabilityResult(
                success=True,
                output=f"用户 {username} 的密码已修改成功",
                raw_output=result.output,
                commands_executed=[cmd],
                risk_level=RiskLevel.HIGH,
            )

        error_msg = result.error or result.output or "权限不足"
        # 如果已经是 "sudo 密码错误"，直接透传（LocalExecutor 已经精确判断了）
        if "密码错误" in error_msg:
            error_msg = f"修改密码失败: sudo 密码错误，请重新输入"
        elif "需要 sudo 密码" in error_msg:
            error_msg = f"修改密码失败: {error_msg}"
        elif "sudo" in error_msg.lower() or "permission" in error_msg.lower() or "超时" in error_msg:
            error_msg = f"修改密码失败: {error_msg}\n提示：请在页面左上角点击「设置 sudo 密码」后重试"
        else:
            error_msg = f"修改密码失败: {error_msg}"
        return CapabilityResult(
            success=False,
            output=error_msg,
            error=error_msg,
            raw_output=result.output,
            commands_executed=[cmd],
            risk_level=RiskLevel.HIGH,
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

    def _format_user_list(self, raw: str, is_windows: bool) -> str:
        """格式化用户列表"""
        if is_windows:
            if raw.strip().startswith('"'):
                return self._parse_csv_output(raw)
            # 旧格式 net user 输出
            lines = raw.strip().split("\n")
            users = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith("-") and not line.startswith("The command") and "成功" not in line:
                    parts = line.split()
                    users.extend(parts)
            rows = [[u] for u in users]
            return _to_markdown_table(["用户名"], rows) if rows else raw
        else:
            lines = raw.strip().split("\n")
            if not lines or not lines[0]:
                return "未找到可登录用户"
            headers = ["用户名", "UID", "GID", "主目录", "Shell"]
            rows = []
            for line in lines:
                parts = line.split(":")
                if len(parts) >= 7:
                    rows.append([parts[0], parts[2], parts[3], parts[5], parts[6]])
            return _to_markdown_table(headers, rows) if rows else raw
