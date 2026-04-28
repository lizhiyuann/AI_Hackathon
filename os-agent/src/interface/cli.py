"""命令行界面 - Typer + Rich"""
import asyncio
import readline 
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from src.agent.core import OSIntelligentAgent
from src.agent.config import ConfigManager
from src.agent.models import RiskLevel
from loguru import logger

app = typer.Typer(
    name="os-agent",
    help="操作系统智能代理 - 自然语言驱动的Linux服务器管理",
    add_completion=False,
)
console = Console()


def _setup_cli_logging():
    """配置CLI模式下的日志 - 完全移除stderr handler，只保留文件输出

    Windows下loguru写stderr会干扰终端输入（退格键显示为^H），
    CLI模式下必须彻底移除stderr handler。
    """
    logger.remove()
    logger.add(
        "data/logs/app.log",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        encoding="utf-8",
    )


def _prompt() -> str:
    """读取用户输入 - 使用input()而非Rich Prompt

    Windows PowerShell下Rich的Prompt.ask()无法正确处理退格键（显示^H），
    改用Python内置input()确保所有终端兼容性。
    """
    console.print("[bold blue]os-agent[/bold blue]", end=" ")
    return input()


def get_agent() -> OSIntelligentAgent:
    """获取代理实例"""
    return OSIntelligentAgent()


def format_response(response):
    """格式化代理响应"""
    if response.success:
        console.print(Panel(
            response.message,
            title="[green]执行结果[/green]",
            border_style="green",
        ))
    else:
        console.print(Panel(
            response.message,
            title="[red]错误[/red]",
            border_style="red",
        ))


def format_risk_warning(response):
    """格式化风险警告"""
    if response.needs_confirmation:
        risk_style = {
            RiskLevel.HIGH: "yellow",
            RiskLevel.CRITICAL: "red",
        }
        style = risk_style.get(response.risk_level, "yellow")
        console.print(Panel(
            response.message,
            title=f"[{style}]风险警告 - {response.risk_level.value.upper()}[/{style}]",
            border_style=style,
        ))
        return True
    return False


@app.command()
def chat():
    """交互式聊天模式"""
    _setup_cli_logging()
    agent = get_agent()

    # 显示 ASCII 艺术
    ascii_art = """
                      OS Agent - 操作系统智能代理
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                      ┃
┃                         /\\_/\\         /\\_/\\                         ┃
┃                        ( ●.● )   ◆   ( ●.● )                        ┃
┃                        (> ◇ <)───────(> ◇ <)                        ┃
┃                         /     \\       /     \\                        ┃
┃                        /  ╭─╮  \\     /  ╭─╮  \\                       ┃
┃                       ◇   │◆│   ◇   ◇   │◆│   ◇                   ┃
┃                          ╰─╯             ╰─╯                         ┃
┃                                                                      ┃
┃                                                                      ┃
┃                       ══════════════════════                         ┃
┃                         OS AGENT 守护系统                            ┃
┃                       ══════════════════════                         ┃
┃                                                                      ┃
┃                    言出即行驱万机，Agent护佑永无虞。                   ┃
┃                    自检风险安如山，智能解析意如溪。                    ┃
┃                    学习渐深技艺精，复合任务一气成。                    ┃
┃                    代码千行稳如磐，运维万里任驰骋。                    ┃
┃                                                                     ┃
┃                          ◆智能守护 永无BUG◆                          ┃
┃                                                                      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
"""
    console.print(ascii_art)
    
    console.print(Panel(
        "[bold blue]OS Agent[/bold blue] - 操作系统智能代理\n\n"
        "支持自然语言驱动的Linux服务器管理\n"
        "输入 'exit' 或 'quit' 退出\n"
        "输入 'help' 查看帮助",
        title="[bold]欢迎使用[/bold]",
        border_style="blue",
    ))

    while True:
        try:
            user_input = _prompt()
            
            if user_input.lower() in ['exit', 'quit']:
                console.print("[yellow]再见！[/yellow]")
                break
            
            if user_input.lower() == 'help':
                show_help()
                continue
            
            if user_input.lower() == 'clear':
                agent.clear_memory()
                console.print("[green]对话历史已清空[/green]")
                continue
            
            # 处理用户输入
            response = asyncio.run(agent.process(user_input))
            
            # 显示风险警告
            if format_risk_warning(response):
                # 如果需要确认，询问用户
                console.print("[yellow]是否继续执行？(y/N)[/yellow]", end=" ")
                confirm = input().strip().lower()
                if confirm.lower() in ['y', 'yes']:
                    response = asyncio.run(agent.process(user_input, confirmed=True))
                    format_response(response)
                else:
                    console.print("[yellow]操作已取消[/yellow]")
            else:
                format_response(response)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]用户中断，退出程序[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]错误: {str(e)}[/red]")


@app.command()
def exec(
    command: str = typer.Argument(..., help="要执行的自然语言指令"),
):
    """执行单次命令"""
    _setup_cli_logging()
    agent = get_agent()
    
    # 显示 ASCII 艺术
    ascii_art = """
                      OS Agent - 操作系统智能代理
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                      ┃
┃                         /\\_/\\         /\\_/\\                         ┃
┃                        ( ●.● )   ◆   ( ●.● )                        ┃
┃                        (> ◇ <)───────(> ◇ <)                        ┃
┃                         /     \\       /     \\                        ┃
┃                        /  ╭─╮  \\     /  ╭─╮  \\                       ┃
┃                       ◇   │◆│   ◇   ◇   │◆│   ◇                   ┃
┃                          ╰─╯             ╰─╯                         ┃
┃                                                                      ┃
┃                                                                      ┃
┃                       ══════════════════════                         ┃
┃                         OS AGENT 守护系统                            ┃
┃                       ══════════════════════                         ┃
┃                                                                      ┃
┃                    言出即行驱万机，Agent护佑永无虞。                   ┃
┃                    自检风险安如山，智能解析意如溪。                    ┃
┃                    学习渐深技艺精，复合任务一气成。                    ┃
┃                    代码千行稳如磐，运维万里任驰骋。                    ┃
┃                                                                     ┃
┃                          ◆智能守护 永无BUG◆                          ┃
┃                                                                      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
"""
    console.print(ascii_art)
    
    response = asyncio.run(agent.process(command))
    format_response(response)


@app.command()
def server(
    host: Optional[str] = typer.Option(None, help="监听主机"),
    port: Optional[int] = typer.Option(None, help="监听端口"),
):
    """启动Web服务"""
    import uvicorn
    cm = ConfigManager()
    bind_host = host or cm.interface.web_host
    bind_port = port or cm.interface.web_port
    
    # 显示 ASCII 艺术
    ascii_art = """
                      OS Agent - 操作系统智能代理
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                      ┃
┃                         /\\_/\\         /\\_/\\                         ┃
┃                        ( ●.● )   ◆   ( ●.● )                        ┃
┃                        (> ◇ <)───────(> ◇ <)                        ┃
┃                         /     \\       /     \\                        ┃
┃                        /  ╭─╮  \\     /  ╭─╮  \\                       ┃
┃                       ◇   │◆│   ◇   ◇   │◆│   ◇                   ┃
┃                          ╰─╯             ╰─╯                         ┃
┃                                                                      ┃
┃                                                                      ┃
┃                       ══════════════════════                         ┃
┃                         OS AGENT 守护系统                            ┃
┃                       ══════════════════════                         ┃
┃                                                                      ┃
┃                    言出即行驱万机，Agent护佑永无虞。                   ┃
┃                    自检风险安如山，智能解析意如溪。                    ┃
┃                    学习渐深技艺精，复合任务一气成。                    ┃
┃                    代码千行稳如磐，运维万里任驰骋。                    ┃
┃                                                                     ┃
┃                          ◆智能守护 永无BUG◆                          ┃
┃                                                                      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
"""
    console.print(ascii_art)
    
    console.print(Panel(
        f"[bold blue]OS Agent Web服务[/bold blue]\n\n"
        f"访问地址: http://{bind_host}:{bind_port}\n"
        f"API文档: http://{bind_host}:{bind_port}/docs",
        title="[bold]启动Web服务[/bold]",
        border_style="blue",
    ))
    
    uvicorn.run(
        "src.interface.server:app",
        host=bind_host,
        port=bind_port,
        reload=False,
    )


@app.command()
def capabilities():
    """查看可用能力"""
    agent = get_agent()
    caps = agent.get_capabilities()
    
    table = Table(title="可用能力")
    table.add_column("名称", style="cyan")
    table.add_column("描述", style="green")
    table.add_column("支持操作", style="yellow")
    
    for cap in caps:
        actions = ", ".join(cap["actions"])
        table.add_row(cap["name"], cap["description"], actions)
    
    console.print(table)


@app.command()
def config():
    """查看当前配置"""
    cm = ConfigManager()
    
    table = Table(title="当前配置")
    table.add_column("配置项", style="cyan")
    table.add_column("值", style="green")
    
    table.add_row("应用名称", cm.app.name)
    table.add_row("版本", cm.app.version)
    table.add_row("语言", cm.app.language)
    table.add_row("日志级别", cm.app.log_level)
    table.add_row("连接模式", cm.connector.mode)
    table.add_row("Web服务", f"{cm.interface.web_host}:{cm.interface.web_port}")
    table.add_row("LLM厂商", cm.llm.active_provider)
    
    console.print(table)


def show_help():
    """显示帮助信息"""
    help_text = """
# OS Agent 使用指南

## 基本命令
- `os-agent chat` - 启动交互式聊天模式
- `os-agent exec "指令"` - 执行单次命令
- `os-agent server` - 启动Web服务
- `os-agent capabilities` - 查看可用能力
- `os-agent config` - 查看当前配置

## 支持的自然语言示例
- 查看磁盘使用情况
- 列出当前目录的文件
- 查看运行中的进程
- 检查端口8080占用情况
- 查看系统用户
- 查看内存使用情况
- 查看CPU状态
- 查看网络配置

## Web界面
启动Web服务后，访问 http://localhost:8000 使用图形界面

## 特殊命令
- `help` - 显示此帮助信息
- `clear` - 清空对话历史
- `exit` 或 `quit` - 退出程序
    """
    console.print(Markdown(help_text))


if __name__ == "__main__":
    app()
