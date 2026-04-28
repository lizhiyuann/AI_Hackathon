"""Web API路由 - 支持多服务器连接配置"""
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from src.agent.core import OSIntelligentAgent
from src.agent.config import ConfigManager
from src.connector.probe import EnvironmentProbe
from src.connector.local import LocalExecutor
from src.connector.remote import RemoteExecutor
from src.utils.logger import log
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"

router = APIRouter(prefix="/api", tags=["OS Agent"])

# 全局状态
_agents: Dict[str, OSIntelligentAgent] = {}
_remote_executors: Dict[str, RemoteExecutor] = {}
_local_executor = LocalExecutor()
_probe = None
_servers_info: Dict[str, Dict] = {
    "local": {
        "id": "local",
        "name": "本地服务器",
        "host": "localhost",
        "port": 22,
        "username": "",
        "auth_type": "password",
        "key_path": "",
        "status": "connected",
        "os_name": "",
        "distro_name": "",
    }
}


def get_agent(server_id: str = "local") -> OSIntelligentAgent:
    """获取或创建代理实例"""
    global _agents
    if server_id not in _agents:
        # 获取对应服务器的执行器
        executor = get_executor(server_id)
        _agents[server_id] = OSIntelligentAgent(executor=executor)
    return _agents[server_id]


def parse_powershell_table(raw_output: str) -> tuple:
    """通用解析PowerShell Format-Table -AutoSize输出，返回(列名列表, 数据行列表)"""
    lines = raw_output.strip().split('\n')
    data_lines = []
    header_line = None
    sep_found = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("----") or stripped.startswith("---"):
            sep_found = True
            continue
        if not sep_found and header_line is None:
            header_line = stripped
            continue
        if sep_found:
            data_lines.append(stripped)

    # 解析表头（PowerShell Format-Table 列名用连续空格分隔）
    headers = header_line.split() if header_line else []

    # 如果没有找到分隔线，可能只有一行数据
    if not sep_found and header_line:
        data_lines = [header_line]
        headers = []

    return headers, data_lines


def _is_csv_output(raw_output: str) -> bool:
    """检测输出是否是CSV格式（ConvertTo-Csv输出）"""
    lines = raw_output.strip().split('\n')
    if len(lines) >= 2:
        first = lines[0].strip()
        if first.startswith('"') and first.endswith('"'):
            return True
    return False


def _csv_to_markdown(raw_output: str) -> str:
    """将CSV格式转为Markdown表格"""
    lines = [l.strip() for l in raw_output.strip().split('\n') if l.strip()]
    if len(lines) < 2:
        return raw_output

    # 解析CSV表头
    headers = [h.strip('"') for h in lines[0].split(',')]
    # 解析数据行
    rows = []
    for line in lines[1:]:
        cells = [c.strip('"') for c in line.split(',')]
        rows.append(cells)

    # 构建Markdown表格
    markdown = "| " + " | ".join(headers) + " |\n"
    markdown += "| " + " | ".join([":---:" for _ in headers]) + " |\n"
    for row in rows:
        # 补齐列数
        while len(row) < len(headers):
            row.append("-")
        markdown += "| " + " | ".join(row) + " |\n"

    return markdown


def format_to_markdown_table(raw_output: str, command: str) -> str:
    """将命令输出格式化为Markdown表格"""
    try:
        lines = raw_output.strip().split('\n')
        if not lines:
            return raw_output

        # 检测CSV格式（Windows ConvertTo-Csv输出）
        if _is_csv_output(raw_output):
            return _csv_to_markdown(raw_output)

        # Linux命令输出
        if "df -h" in command:
            return _format_linux_df(lines)
        elif "ps aux" in command:
            return _format_linux_ps(lines)
        elif "free -h" in command:
            return _format_linux_free(lines)
        elif "ip addr" in command:
            return _format_linux_ip(lines)
        elif "whoami" in command:
            return _format_linux_whoami(lines)
        elif "uname" in command:
            return _format_linux_uname(lines)

        return raw_output
    except Exception as e:
        log.error(f"格式化输出失败: {e}")
        return raw_output


def _format_linux_df(lines: list) -> str:
    """格式化Linux df命令输出"""
    if len(lines) < 2:
        return "\n".join(lines)
    headers = ["文件系统", "容量", "已用", "可用", "已用%", "挂载点"]
    markdown = "| " + " | ".join(headers) + " |\n"
    markdown += "| " + " | ".join([":---:" for _ in headers]) + " |\n"
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 6:
            markdown += "| " + " | ".join(parts[:6]) + " |\n"
    return markdown


def _format_linux_ps(lines: list) -> str:
    """格式化Linux ps命令输出"""
    if len(lines) < 2:
        return "\n".join(lines)
    headers = ["USER", "PID", "%CPU", "%MEM", "VSZ", "RSS", "COMMAND"]
    markdown = "| " + " | ".join(headers) + " |\n"
    markdown += "| " + " | ".join([":---:" for _ in headers]) + " |\n"
    for line in lines[1:]:
        parts = line.split(None, 10)
        if len(parts) >= 7:
            markdown += "| " + " | ".join(parts[:7]) + " |\n"
    return markdown


def _format_linux_free(lines: list) -> str:
    """格式化Linux free命令输出"""
    if len(lines) < 2:
        return "\n".join(lines)
    markdown = "| 指标 | 总计 | 已用 | 可用 | 共享 | 缓存 | 可用(含缓存) |\n"
    markdown += "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 7:
            markdown += "| " + " | ".join(parts[:7]) + " |\n"
    return markdown


def _format_linux_ip(lines: list) -> str:
    """格式化Linux ip addr输出"""
    entries = []
    iface = None
    for line in lines:
        if line and line[0].isdigit():
            parts = line.split(': ', 2)
            if len(parts) >= 2:
                iface = parts[1].split(':')[0]
        elif "inet " in line and iface:
            ip = line.strip().split()[1]
            entries.append((iface, ip))
    if not entries:
        return "\n".join(lines)
    markdown = "| 网卡 | IP地址 |\n|:---:|:---:|\n"
    for iface, ip in entries:
        markdown += f"| {iface} | {ip} |\n"
    return markdown


def _format_linux_whoami(lines: list) -> str:
    """格式化Linux whoami/hostname输出"""
    if len(lines) >= 2:
        return f"| 项目 | 信息 |\n|:---:|:---:|\n| 用户名 | {lines[0].strip()} |\n| 主机名 | {lines[1].strip()} |\n"
    return "\n".join(lines)


def _format_linux_uname(lines: list) -> str:
    """格式化Linux uname -a输出"""
    if lines:
        parts = lines[0].split()
        if len(parts) >= 3:
            return f"| 项目 | 信息 |\n|:---:|:---:|\n| 系统 | {parts[0]} |\n| 主机名 | {parts[1]} |\n| 内核 | {parts[2]} |\n"
    return "\n".join(lines)


def get_executor(server_id: str):
    """获取执行器"""
    if server_id == "local":
        return _local_executor
    return _remote_executors.get(server_id)


def execute_command(server_id: str, msg: str):
    """执行常见命令"""
    executor = get_executor(server_id)
    if not executor:
        return None, None, "服务器未连接"
    
    msg_lower = msg.lower()
    cmd = None
    is_windows = server_id == "local" and executor == _local_executor
    
    utf8_cmd = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    
    if "磁盘" in msg_lower or "disk" in msg_lower:
        if is_windows:
            cmd = 'powershell -Command "' + utf8_cmd + "Get-PSDrive -PSProvider FileSystem | Select-Object @{N='盘符';E={$_.Name}}, @{N='已用(GB)';E={[math]::Round($_.Used/1GB,2)}}, @{N='可用(GB)';E={[math]::Round($_.Free/1GB,2)}}, @{N='总计(GB)';E={[math]::Round(($_.Used+$_.Free)/1GB,2)}} | ConvertTo-Csv -NoTypeInformation" + '"'
        else:
            cmd = "df -h"
    elif "进程" in msg_lower or "process" in msg_lower:
        if is_windows:
            cmd = 'powershell -Command "' + utf8_cmd + "Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 15 @{N='进程名';E={$_.Name}}, @{N='CPU(秒)';E={[math]::Round($_.CPU,2)}}, @{N='内存(MB)';E={[math]::Round($_.WorkingSet64/1MB,2)}} | ConvertTo-Csv -NoTypeInformation" + '"'
        else:
            cmd = "ps aux --sort=-%mem | head -15"
    elif "内存" in msg_lower or "memory" in msg_lower:
        if is_windows:
            cmd = 'powershell -Command "' + utf8_cmd + "Get-CimInstance Win32_OperatingSystem | Select-Object @{N='总内存(GB)';E={[math]::Round($_.TotalVisibleMemorySize/1MB,2)}}, @{N='可用(GB)';E={[math]::Round($_.FreePhysicalMemory/1MB,2)}}, @{N='已用(GB)';E={[math]::Round(($_.TotalVisibleMemorySize-$_.FreePhysicalMemory)/1MB,2)}} | ConvertTo-Csv -NoTypeInformation" + '"'
        else:
            cmd = "free -h"
    elif "网络" in msg_lower or "network" in msg_lower:
        if is_windows:
            cmd = 'powershell -Command "' + utf8_cmd + "Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'} | Select-Object @{N='网卡';E={$_.InterfaceAlias}}, @{N='IP地址';E={$_.IPAddress}} | ConvertTo-Csv -NoTypeInformation" + '"'
        else:
            cmd = "ip addr | grep -A2 'state UP'"
    elif "用户" in msg_lower or "user" in msg_lower:
        if is_windows:
            cmd = 'powershell -Command "' + utf8_cmd + "$u=$env:USERNAME; $c=$env:COMPUTERNAME; $d=$env:USERDOMAIN; [PSCustomObject]@{用户名=$u; 计算机名=$c; 域=$d} | ConvertTo-Csv -NoTypeInformation" + '"'
        else:
            cmd = "whoami && hostname"
    elif "系统" in msg_lower or "system" in msg_lower or "uname" in msg_lower:
        if is_windows:
            cmd = 'powershell -Command "' + utf8_cmd + "Get-CimInstance Win32_OperatingSystem | Select-Object @{N='操作系统';E={$_.Caption}}, @{N='版本';E={$_.Version}}, @{N='架构';E={$_.OSArchitecture}}, @{N='构建号';E={$_.BuildNumber}} | ConvertTo-Csv -NoTypeInformation" + '"'
        else:
            cmd = "uname -a"
    else:
        return None, None, None
    
    result = executor.execute(cmd)
    if result and result.success:
        # 将输出转换为Markdown表格
        result.output = format_to_markdown_table(result.output, cmd)
    return cmd, result, None


def get_probe():
    global _probe
    if _probe is None:
        _probe = EnvironmentProbe()
    return _probe


# ============ 数据模型 ============

class ChatRequest(BaseModel):
    message: str
    confirmed: bool = False
    server_id: str = "local"
    session_id: str = "default"


class ChatResponse(BaseModel):
    success: bool
    message: str
    commands_executed: list = []
    risk_level: str = "low"
    needs_confirmation: bool = False
    server_id: str = "local"
    session_id: str = "default"
    progress: Optional[str] = None


class SessionCreateRequest(BaseModel):
    title: str = "新会话"


class CapabilityItem(BaseModel):
    name: str
    description: str
    actions: List[str]


class CapabilitiesResponse(BaseModel):
    capabilities: List[CapabilityItem]


class SystemResponse(BaseModel):
    os_name: str
    os_version: str = ""
    distro_name: str
    distro_version: str = ""
    kernel: str
    hostname: str
    current_user: str
    working_dir: str = ""
    package_manager: str = ""


class ServerInfo(BaseModel):
    id: str
    name: str
    host: str
    port: int = 22
    username: str = ""
    auth_type: str = "password"
    key_path: str = ""
    status: str = "disconnected"
    os_name: str = ""
    distro_name: str = ""


class ConnectRequest(BaseModel):
    id: str
    name: str
    host: str
    port: int = 22
    username: str = ""
    auth_type: str = "password"
    key_path: str = ""
    password: str = ""


class ServerListResponse(BaseModel):
    servers: List[ServerInfo]


# ============ 路由 ============

@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "message": "OS Agent 服务运行正常"
    }


@router.get("/sudo/status")
async def sudo_status():
    """检测当前 sudo 状态"""
    try:
        from src.connector.local import LocalExecutor
        status = LocalExecutor.check_sudo()
        return {"success": True, **status}
    except Exception as e:
        log.error(f"检测sudo状态失败: {e}")
        return {"success": False, "has_sudo": False, "message": str(e)}


@router.post("/sudo/password")
async def set_sudo_password(request: dict):
    """设置 sudo 密码"""
    password = request.get("password", "")
    if not password:
        return {"success": False, "message": "请输入密码"}
    try:
        from src.connector.local import LocalExecutor
        LocalExecutor.set_sudo_password(password)
        status = LocalExecutor.check_sudo()
        if status.get("has_sudo"):
            return {"success": True, "message": "sudo 密码验证成功"}
        else:
            return {"success": False, "message": "密码错误，请重试"}
    except Exception as e:
        log.error(f"设置sudo密码失败: {e}")
        return {"success": False, "message": str(e)}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """发送消息给代理 - 所有请求都经过完整的安全流程（人在闭环）"""
    try:
        server_id = request.server_id
        
        # 检查服务器是否已连接
        executor = get_executor(server_id)
        if not executor:
            return ChatResponse(
                success=False,
                message="服务器未连接，请先连接服务器。",
                server_id=server_id,
            )
        
        # 所有请求统一走agent的完整安全流程：意图解析 → 环境探测 → 风险评估 → 确认 → 执行 → 审计
        agent = get_agent(server_id)
        # 保存session_id到agent，方便保存到对应会话
        agent._current_session_id = request.session_id
        response = await agent.process(request.message, confirmed=request.confirmed)
        # 自动更新会话标题（第一条消息后）
        if request.session_id and request.session_id != "default":
            try:
                from src.agent.memory import ConversationMemory
                memory = ConversationMemory()
                sessions = memory.list_sessions()
                for s in sessions:
                    if s["id"] == request.session_id and s["title"] == "新会话" and s["message_count"] <= 1:
                        auto_title = memory.auto_title_from_input(request.message)
                        memory.update_session_title(request.session_id, auto_title)
                        break
            except Exception:
                pass
        return ChatResponse(
            success=response.success,
            message=response.message,
            commands_executed=response.commands_executed,
            risk_level=response.risk_level.value if hasattr(response.risk_level, 'value') else str(response.risk_level),
            needs_confirmation=response.needs_confirmation,
            server_id=server_id,
            session_id=request.session_id,
            progress=getattr(response, 'progress', None),
        )
    except Exception as e:
        log.error(f"处理消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities():
    """获取可用能力列表"""
    agent = get_agent("local")
    caps = agent.get_capabilities()
    return CapabilitiesResponse(
        capabilities=[
            CapabilityItem(name=cap["name"], description=cap["description"], actions=cap["actions"])
            for cap in caps
        ]
    )


@router.get("/system", response_model=SystemResponse)
async def get_system_info():
    """获取系统信息"""
    probe = get_probe()
    env = probe.detect()
    return SystemResponse(
        os_name=env.os_name,
        os_version=env.os_version,
        distro_name=env.distro_name,
        distro_version=env.distro_version,
        kernel=env.kernel,
        hostname=env.hostname,
        current_user=env.current_user,
        working_dir=env.working_dir,
        package_manager=env.package_manager,
    )


@router.get("/servers", response_model=ServerListResponse)
async def list_servers():
    """获取服务器列表"""
    servers = [ServerInfo(**info) for info in _servers_info.values()]
    return ServerListResponse(servers=servers)


@router.post("/servers/connect")
async def connect_server(request: ConnectRequest):
    """连接远程服务器"""
    try:
        executor = RemoteExecutor(
            host=request.host,
            port=request.port,
            username=request.username,
            key_path=request.key_path if request.auth_type == "key" else "",
            password=request.password if request.auth_type == "password" else "",
        )
        
        # 测试连接
        result = executor.execute("uname -a")
        if result.success:
            # 获取系统信息
            os_name = "Linux"
            distro_name = "Unknown"
            try:
                env_result = executor.execute("cat /etc/os-release 2>/dev/null | grep '^NAME=' | head -1")
                if env_result.success and env_result.output:
                    distro_name = env_result.output.split("=")[1].strip().strip('"')
            except Exception as e:
                log.debug(f"探测远程发行版失败（非关键）: {e}")
            
            # 存储执行器和服务器信息（先清除旧的 agent 缓存，防止用旧 executor 查到旧用户信息）
            server_id = request.id
            if server_id in _agents:
                del _agents[server_id]
            if server_id in _remote_executors:
                try:
                    _remote_executors[server_id].close()
                except Exception:
                    pass
            _remote_executors[server_id] = executor
            _servers_info[server_id] = {
                "id": server_id,
                "name": request.name,
                "host": request.host,
                "port": request.port,
                "username": request.username,
                "auth_type": request.auth_type,
                "key_path": request.key_path,
                "status": "connected",
                "os_name": os_name,
                "distro_name": distro_name,
            }
            
            return {
                "success": True,
                "message": f"成功连接到 {request.host}",
                "server_info": {"os_name": os_name, "distro_name": distro_name}
            }
        else:
            return {"success": False, "message": f"连接失败: {result.error or result.output}"}
    except Exception as e:
        log.error(f"连接服务器失败: {e}")
        return {"success": False, "message": f"连接失败: {str(e)}"}


@router.get("/detect-ssh-user")
async def detect_ssh_user(request: Request):
    """根据客户端 IP 检测 SSH 登录用户，供前端自动切换身份"""
    try:
        # 获取客户端 IP
        client_ip = request.client.host if request.client else ""
        log.info(f"检测 SSH 用户，客户端 IP: {client_ip}")

        if not client_ip or client_ip in ("127.0.0.1", "::1", "localhost"):
            return {"success": False, "message": "本地连接，无需检测 SSH 用户"}

        # 用 w 命令查找该 IP 的 SSH 用户
        import subprocess
        result = subprocess.run(
            ["w", "-h"],
            capture_output=True, text=True, timeout=5,
        )
        if not result.stdout.strip():
            return {"success": False, "message": "无法获取登录信息"}

        # 解析 w 输出，格式: USER TTY FROM LOGIN@ IDLE JCPU PCPU WHAT
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3 and parts[2] == client_ip:
                ssh_user = parts[0]
                # 跳过当前运行服务的用户（不需要自动切换）
                import os
                if ssh_user == os.environ.get("USER", ""):
                    return {"success": False, "message": f"SSH 用户 {ssh_user} 与服务用户相同，无需切换"}
                log.info(f"检测到 SSH 用户: {ssh_user} (来自 {client_ip})")
                return {
                    "success": True,
                    "ssh_user": ssh_user,
                    "client_ip": client_ip,
                }

        return {"success": False, "message": f"未找到来自 {client_ip} 的 SSH 登录"}
    except Exception as e:
        log.error(f"检测 SSH 用户失败: {e}")
        return {"success": False, "message": f"检测失败: {str(e)}"}


@router.post("/servers/switch-user")
async def switch_user(request: dict):
    """切换执行用户身份（通过 sudo -u）"""
    username = request.get("username", "")
    if not username:
        return {"success": False, "message": "请指定用户名"}

    try:
        # 验证用户是否存在
        check = _local_executor.execute(f"id {username} 2>&1")
        if not check.success or "no such user" in check.output.lower():
            return {"success": False, "message": f"用户 {username} 不存在"}

        # 设置执行身份
        _local_executor.run_as_user = username

        # 清除 agent 缓存，确保下次使用新身份
        if "local" in _agents:
            del _agents["local"]

        log.info(f"已切换执行用户为: {username}")
        return {"success": True, "message": f"已切换为 {username} 身份执行命令", "username": username}
    except Exception as e:
        log.error(f"切换用户失败: {e}")
        return {"success": False, "message": f"切换失败: {str(e)}"}


@router.post("/servers/reset-user")
async def reset_user():
    """恢复为服务启动用户身份"""
    _local_executor.run_as_user = None
    if "local" in _agents:
        del _agents["local"]
    import os
    return {
        "success": True,
        "message": f"已恢复为 {os.environ.get('USER', 'unknown')} 身份",
        "username": os.environ.get("USER", "unknown"),
    }


@router.post("/servers/disconnect")
async def disconnect_server(request: dict):
    """断开远程服务器连接"""
    server_id = request.get("server_id", "")
    if not server_id:
        return {"success": False, "message": "请指定服务器ID"}
    
    try:
        # 关闭远程执行器
        executor = _remote_executors.get(server_id)
        if executor:
            executor.close()
            del _remote_executors[server_id]
        
        # 清除服务器信息
        if server_id in _servers_info:
            del _servers_info[server_id]
        
        # 清除对应的agent缓存（下次使用会创建新agent）
        if server_id in _agents:
            del _agents[server_id]
        
        return {"success": True, "message": f"已断开服务器 {server_id}"}
    except Exception as e:
        log.error(f"断开服务器失败: {e}")
        return {"success": False, "message": f"断开失败: {str(e)}"}


@router.post("/servers/delete")
async def delete_server(request: dict):
    """删除服务器（断开连接并清除信息）"""
    server_id = request.get("server_id", "")
    if not server_id:
        return {"success": False, "message": "请指定服务器ID"}
    if server_id == "local":
        return {"success": False, "message": "不能删除本地服务器"}

    try:
        executor = _remote_executors.get(server_id)
        if executor:
            executor.close()
            del _remote_executors[server_id]

        if server_id in _servers_info:
            del _servers_info[server_id]

        if server_id in _agents:
            del _agents[server_id]

        return {"success": True, "message": f"已删除服务器 {server_id}"}
    except Exception as e:
        log.error(f"删除服务器失败: {e}")
        return {"success": False, "message": f"删除失败: {str(e)}"}


@router.post("/clear")
async def clear_memory(request: dict = None):
    """清空对话历史"""
    session_id = request.get("session_id") if request else None
    agent = get_agent("local")
    if session_id and session_id != "default":
        agent.memory.clear(session_id=session_id)
    else:
        agent.clear_memory()
    return {"success": True, "message": "对话历史已清空"}


# ============ 会话管理路由 ============

@router.post("/sessions")
async def create_session(request: SessionCreateRequest):
    """创建新会话"""
    import uuid
    session_id = str(uuid.uuid4())[:8]
    try:
        from src.agent.memory import ConversationMemory
        memory = ConversationMemory()
        session = memory.create_session(session_id, request.title)
        return {"success": True, "session": session}
    except Exception as e:
        log.error(f"创建会话失败: {e}")
        return {"success": False, "message": str(e)}


@router.get("/sessions")
async def list_sessions():
    """列出所有会话"""
    try:
        from src.agent.memory import ConversationMemory
        memory = ConversationMemory()
        sessions = memory.list_sessions()
        return {"success": True, "sessions": sessions}
    except Exception as e:
        log.error(f"获取会话列表失败: {e}")
        return {"success": False, "sessions": [], "message": str(e)}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取指定会话的消息列表"""
    try:
        from src.agent.memory import ConversationMemory
        memory = ConversationMemory()
        messages = memory.get_session_messages(session_id)
        return {"success": True, "messages": messages}
    except Exception as e:
        log.error(f"获取会话消息失败: {e}")
        return {"success": False, "messages": [], "message": str(e)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    try:
        from src.agent.memory import ConversationMemory
        memory = ConversationMemory()
        memory.delete_session(session_id)
        return {"success": True, "message": "会话已删除"}
    except Exception as e:
        log.error(f"删除会话失败: {e}")
        return {"success": False, "message": str(e)}


@router.get("/audit")
async def get_audit_logs(limit: int = 20):
    """获取操作审计日志 - 支持行为可解释"""
    try:
        from src.guardian.audit import AuditLogger
        audit = AuditLogger()
        logs = audit.get_recent_logs(limit=limit)
        return {"success": True, "logs": logs, "total": len(logs)}
    except Exception as e:
        log.error(f"获取审计日志失败: {e}")
        return {"success": False, "logs": [], "message": str(e)}


@router.get("/memory/search")
async def search_memory(query: str = "", limit: int = 10):
    """搜索对话记忆"""
    try:
        from src.agent.memory import ConversationMemory
        memory = ConversationMemory()
        if query:
            results = memory.search(query, limit=limit)
        else:
            results = memory.get_recent(limit)
        return {
            "success": True,
            "results": [
                {
                    "timestamp": r.timestamp,
                    "user_input": r.user_input,
                    "agent_response": r.agent_response[:200],
                    "commands": r.commands,
                }
                for r in results
            ],
        }
    except Exception as e:
        log.error(f"搜索记忆失败: {e}")
        return {"success": False, "results": [], "message": str(e)}


# ============ 学习记忆路由 ============

@router.get("/learning/stats")
async def get_learning_stats():
    """获取学习记忆统计"""
    try:
        from src.agent.learning import LearningMemory
        learning = LearningMemory()
        stats = learning.get_stats()
        return {"success": True, **stats}
    except Exception as e:
        log.error(f"获取学习统计失败: {e}")
        return {"success": False, "message": str(e)}


@router.get("/learning/lessons")
async def get_learning_lessons(limit: int = 50, offset: int = 0):
    """获取学习记忆列表"""
    try:
        from src.agent.learning import LearningMemory
        learning = LearningMemory()
        lessons = learning.get_all(limit=limit, offset=offset)
        return {"success": True, "lessons": lessons, "total": len(lessons)}
    except Exception as e:
        log.error(f"获取学习记忆失败: {e}")
        return {"success": False, "lessons": [], "message": str(e)}


@router.delete("/learning/lessons/{lesson_id}")
async def delete_learning_lesson(lesson_id: int):
    """删除一条学习记忆"""
    try:
        from src.agent.learning import LearningMemory
        learning = LearningMemory()
        learning.delete(lesson_id)
        return {"success": True, "message": "学习记忆已删除"}
    except Exception as e:
        log.error(f"删除学习记忆失败: {e}")
        return {"success": False, "message": str(e)}


@router.get("/learning/export")
async def export_learning_markdown():
    """导出全部学习记忆为 Markdown 文档"""
    try:
        from src.agent.learning import LearningMemory
        learning = LearningMemory()
        output_path = str(DATA_DIR / "learning_memory.md")
        content = learning.export_to_markdown(output_path)
        return {
            "success": True,
            "message": f"学习记忆已导出到 {output_path}",
            "path": output_path,
            "content": content,
        }
    except Exception as e:
        log.error(f"导出学习记忆失败: {e}")
        return {"success": False, "message": str(e)}


@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """语音识别 - 接收WAV音频文件，返回识别文字"""
    try:
        from src.voice.stt import get_stt
        stt = get_stt()
        
        if not stt.is_available:
            return {
                "success": False,
                "text": "",
                "message": "语音识别模型未安装，请先下载vosk中文模型",
            }
        
        # 读取音频数据
        audio_bytes = await audio.read()
        log.info(f"收到音频数据: {len(audio_bytes)} bytes, content_type={audio.content_type}")
        
        if len(audio_bytes) < 100:
            return {
                "success": False,
                "text": "",
                "message": "音频数据太短",
            }
        
        # 识别
        text = stt.recognize(audio_bytes)
        
        if text:
            return {
                "success": True,
                "text": text,
                "message": "识别成功",
            }
        else:
            return {
                "success": True,
                "text": "",
                "message": "未识别到语音内容",
            }
    except Exception as e:
        log.error(f"语音识别失败: {e}")
        return {
            "success": False,
            "text": "",
            "message": f"语音识别失败: {str(e)}",
        }


@router.get("/stt/status")
async def stt_status():
    """检查语音识别是否可用"""
    try:
        from src.voice.stt import get_stt
        stt = get_stt()
        return {
            "available": stt.is_available,
            "message": "语音识别可用" if stt.is_available else "语音识别模型未安装",
        }
    except Exception as e:
        return {
            "available": False,
            "message": f"检查失败: {str(e)}",
        }
