"""工具函数模块"""
import re
from typing import Dict, Any, Optional


def parse_command_template(template: str, variables: Dict[str, Any]) -> str:
    """解析命令模板，替换变量"""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def extract_variables_from_template(template: str) -> list:
    """提取模板中的变量名"""
    return re.findall(r'\{(\w+)\}', template)


def sanitize_path(path: str) -> str:
    """清理路径，防止路径遍历攻击"""
    # 规范化路径
    clean = path.replace("../", "").replace("..\\", "")
    return clean


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def truncate_output(output: str, max_lines: int = 50, max_chars: int = 2000) -> str:
    """截断过长的输出"""
    lines = output.splitlines()
    if len(lines) > max_lines:
        output = "\n".join(lines[:max_lines]) + f"\n... (共 {len(lines)} 行，已截断)"
    if len(output) > max_chars:
        output = output[:max_chars] + "\n... (内容过长，已截断)"
    return output
