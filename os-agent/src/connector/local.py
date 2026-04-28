"""本地命令执行器 - 支持 sudo 密码注入"""
import subprocess
import os
from dataclasses import dataclass
from typing import Optional

from src.utils.logger import log


@dataclass
class ExecutionResult:
    """命令执行结果"""
    success: bool
    output: str
    error: str = ""
    return_code: int = 0


class LocalExecutor:
    """本地命令执行器"""

    # 全局共享的 sudo 密码（由 API 层设置）
    _sudo_password: Optional[str] = None
    # 以指定用户身份执行命令（通过 sudo -u）
    _run_as_user: Optional[str] = None

    def __init__(self, timeout: int = 30, run_as_user: Optional[str] = None):
        self.timeout = timeout
        self.run_as_user = run_as_user or self._run_as_user

    @classmethod
    def set_sudo_password(cls, password: str):
        """设置 sudo 密码"""
        cls._sudo_password = password

    @classmethod
    def clear_sudo_password(cls):
        """清除 sudo 密码"""
        cls._sudo_password = None

    @classmethod
    def check_sudo(cls) -> dict:
        """检测当前 sudo 状态"""
        user = os.environ.get("USER", os.environ.get("USERNAME", ""))
        if os.geteuid() == 0:
            return {"has_sudo": True, "is_root": True, "user": user, "message": "当前是 root 用户，无需 sudo"}

        # 已有密码时用 sudo -S true 快速验证（~1.5秒）
        if cls._sudo_password:
            try:
                result = subprocess.run(
                    ["sudo", "-S", "true"],
                    input=(cls._sudo_password + "\n").encode(),
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    return {"has_sudo": True, "is_root": False, "user": user, "message": "sudo 密码已验证"}
                else:
                    combined = (result.stdout + result.stderr).decode(errors="replace")
                    if "incorrect password" in combined or "Sorry" in combined:
                        return {"has_sudo": False, "is_root": False, "user": user, "message": "sudo 密码错误，请重新输入"}
                    return {"has_sudo": False, "is_root": False, "user": user, "message": "sudo 密码验证失败"}
            except subprocess.TimeoutExpired:
                return {"has_sudo": False, "is_root": False, "user": user, "message": "sudo 验证超时"}
            except Exception as e:
                return {"has_sudo": False, "is_root": False, "user": user, "message": f"sudo 检测失败: {e}"}

        return {"has_sudo": False, "is_root": False, "user": user, "message": "需要 sudo 密码"}

    def execute(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """执行命令，对 sudo 命令自动注入密码并快速返回"""
        timeout = timeout or self.timeout

        # 如果设置了 run_as_user，且当前不是该用户，则用 sudo -u 包装普通命令
        # 管理操作（已有 sudo 前缀）保持不变，仍以 root 执行
        if self.run_as_user and os.geteuid() != 0:
            current_user = os.environ.get("USER", os.environ.get("USERNAME", ""))
            if current_user != self.run_as_user and not command.startswith("sudo "):
                # 将普通命令包装为 sudo -u {user} bash -c '...' 以切换身份
                escaped = command.replace("'", "'\\''")
                command = f"sudo -u {self.run_as_user} bash -c '{escaped}'"

        needs_sudo = "sudo " in command and os.geteuid() != 0

        # 没有密码 → 立即失败（前端弹窗）
        if needs_sudo and not self._sudo_password:
            log.warning("命令需要 sudo 密码，但未设置")
            return ExecutionResult(
                success=False, output="",
                error="需要 sudo 密码：请在页面左上角点击「设置 sudo 密码」后重试",
                return_code=1,
            )

        # 有密码的 sudo 命令 → 走专用路径（不走 shell 管道）
        if needs_sudo and self._sudo_password:
            return self._execute_with_sudo(command, timeout)

        # 普通命令 → 直接执行
        return self._execute_normal(command, timeout)

    def _execute_with_sudo(self, command: str, timeout: int) -> ExecutionResult:
        """执行 sudo 命令：先验证密码，再通过 stdin 传密码执行"""
        log.debug(f"执行 sudo 命令: {command}")

        # 第一步：快速验证 sudo 密码（~1.5秒）
        # 比直接执行 30 秒超时快 20 倍
        try:
            check = subprocess.run(
                ["sudo", "-S", "true"],
                input=(self._sudo_password + "\n").encode(),
                capture_output=True, timeout=5
            )
            if check.returncode != 0:
                combined = self._decode_output(check.stdout) + "\n" + self._decode_output(check.stderr)
                if "incorrect" in combined.lower() or "sorry" in combined.lower():
                    log.warning("sudo 密码错误")
                    return ExecutionResult(
                        success=False, output=combined,
                        error="sudo 密码错误，请重新输入",
                        return_code=1,
                    )
                log.warning(f"sudo 验证失败: {combined}")
                return ExecutionResult(
                    success=False, output=combined,
                    error=f"sudo 验证失败: {combined}",
                    return_code=1,
                )
        except subprocess.TimeoutExpired:
            log.warning("sudo 密码验证超时")
            return ExecutionResult(
                success=False, output="",
                error="sudo 密码验证超时（5秒），请检查系统 sudo 配置",
                return_code=-1,
            )
        except Exception as e:
            log.warning(f"sudo 验证异常: {e}")
            return ExecutionResult(
                success=False, output="",
                error=f"sudo 验证失败: {e}",
                return_code=-1,
            )

        # 第二步：密码验证通过，执行真实命令
        # 用 sudo -S + Popen + stdin 传密码（不用 shell 管道，不挂住）
        # 把 sudo 替换为 sudo -S 让它从 stdin 读密码
        sudo_cmd = command.replace("sudo ", "sudo -S ", 1)

        try:
            proc = subprocess.Popen(
                sudo_cmd, shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            out, err = proc.communicate(
                input=(self._sudo_password + "\n").encode(),
                timeout=timeout
            )

            output = self._decode_output(out)
            error = self._decode_output(err)

            success = proc.returncode == 0
            if not success and error:
                log.warning(f"sudo 命令执行失败: {error}")
            else:
                log.debug(f"sudo 命令执行成功，输出长度: {len(output)}")

            return ExecutionResult(
                success=success,
                output=output,
                error=error,
                return_code=proc.returncode,
            )

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return ExecutionResult(
                success=False, output="",
                error=f"命令执行超时 ({timeout}秒)",
                return_code=-1,
            )
        except Exception as e:
            return ExecutionResult(
                success=False, output="",
                error=str(e),
                return_code=-1,
            )

    def _execute_normal(self, command: str, timeout: int) -> ExecutionResult:
        """执行普通命令（无 sudo）"""
        log.debug(f"执行命令: {command}")
        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, timeout=timeout,
            )

            success = result.returncode == 0
            output = self._decode_output(result.stdout)
            error = self._decode_output(result.stderr)

            if not success and error:
                log.warning(f"命令执行失败: {error}")
            else:
                log.debug(f"命令执行成功，输出长度: {len(output)}")

            return ExecutionResult(
                success=success,
                output=output,
                error=error,
                return_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False, output="",
                error=f"命令执行超时 ({timeout}秒)",
                return_code=-1,
            )
        except Exception as e:
            return ExecutionResult(
                success=False, output="",
                error=str(e),
                return_code=-1,
            )

    def _decode_output(self, data: bytes) -> str:
        """尝试多种编码解码输出"""
        if not data:
            return ""

        encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']

        for encoding in encodings:
            try:
                return data.decode(encoding).strip()
            except (UnicodeDecodeError, LookupError):
                continue

        return data.decode('utf-8', errors='replace').strip()
