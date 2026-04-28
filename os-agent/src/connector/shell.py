"""Shell命令封装模块"""
from typing import List


class ShellCommand:
    """Shell命令构建器"""

    def __init__(self, base_cmd: str):
        self.parts: List[str] = [base_cmd]

    def add_flag(self, flag: str) -> "ShellCommand":
        self.parts.append(flag)
        return self

    def add_arg(self, arg: str) -> "ShellCommand":
        self.parts.append(arg)
        return self

    def add_pipe(self, cmd: str) -> "ShellCommand":
        self.parts.append(f"| {cmd}")
        return self

    def add_redirect(self, target: str, mode: str = ">") -> "ShellCommand":
        self.parts.append(f"{mode} {target}")
        return self

    def build(self) -> str:
        return " ".join(self.parts)
