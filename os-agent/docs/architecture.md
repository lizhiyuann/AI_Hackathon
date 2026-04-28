# OS Agent - 系统架构设计文档

## 一、系统架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        交互层 (Interface)                           │
│                                                                     │
│    ┌──────────┐      ┌──────────┐      ┌──────────┐                │
│    │  CLI终端  │      │  Web界面  │      │ API接口  │                │
│    └─────┬────┘      └─────┬────┘      └─────┬────┘                │
│          │                 │                 │                      │
└──────────┼─────────────────┼─────────────────┼──────────────────────┘
           │                 │                 │
           └────────────────┬┴─────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                        代理层 (Agent Core)                          │
│                                                                     │
│    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│    │   主代理    │  │  任务规划器  │  │ LangGraph   │               │
│    │   (Core)    │  │ (Planner)   │  │  状态机     │               │
│    └──────┬──────┘  └─────────────┘  └─────────────┘               │
│           │                                                         │
│    ┌──────▼──────┐  ┌─────────────┐  ┌─────────────┐               │
│    │  意图理解   │  │  对话记忆   │  │  上下文管理  │               │
│    │(Understanding)  │  (Memory)   │  │  (Context)  │               │
│    └─────────────┘  └──────┬──────┘  └─────────────┘               │
│                            │                                        │
│                     ┌──────▼──────┐                                 │
│                     │  学习记忆   │ ← 从错误修正中自动提取经验教训   │
│                     │ (Learning)  │ → 注入意图解析提示词，自我进化   │
│                     └─────────────┘                                 │
│                                                                     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
┌──────────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
│   能力模块      │  │  安全守护   │  │   连接器    │
│ (Capabilities)  │  │ (Guardian)  │  │ (Connector) │
│                 │  │             │  │             │
│ 磁盘/文件/     │  │ 风险检测    │  │  本地执行   │
│ 进程/用户/     │  │ 二次确认    │  │  SSH远程    │
│ 系统信息       │  │ 审计日志    │  │  环境探测   │
└─────────────────┘  └─────────────┘  └─────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                      大模型服务层 (LLM Layer)                        │
│                                                                     │
│    ┌─────────────────────────────────────────────────────────┐      │
│    │              统一LLM接口适配层                           │      │
│    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │      │
│    │  │  Qwen   │ │DeepSeek │ │  GLM    │ │Moonshot │ ...   │      │
│    │  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │      │
│    └─────────────────────────────────────────────────────────┘      │
│                                                                     │
│    ┌─────────────────────────────────────────────────────────┐      │
│    │              语音服务层 (可选)                           │      │
│    │  ┌─────────────────┐      ┌─────────────────┐          │      │
│    │  │ STT (语音识别)   │      │ TTS (语音合成)   │          │      │
│    │  │     vosk        │      │  浏览器 Speech   │          │      │
│    │  │  (本地中文模型)  │      │    API / API     │          │      │
│    │  └─────────────────┘      └─────────────────┘          │      │
│    └─────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、核心模块设计

### 2.1 Agent模块 (`src/agent/`)

代理核心模块，负责协调各个子模块。

| 文件 | 职责 |
|------|------|
| `core.py` | 主代理类，协调所有模块；LLM驱动的复合任务分解；复合任务进度可视化 `[i/total]` |
| `planner.py` | 任务规划器，任务步骤数据结构定义 |
| `graph.py` | LangGraph 状态图定义（意图解析→环境探测→风险评估→确认→执行→验证→响应）；自动重试、风险解释、失败恢复建议、环境预警 |
| `config.py` | 配置管理（YAML 配置加载） |
| `memory.py` | 对话记忆（SQLite 持久化） |
| `learning.py` | 学习记忆（从错误修正中自动提取经验教训，注入后续决策，实现自我进化） |
| `models.py` | 数据模型定义（Intent, RiskAssessment, AgentResponse 等） |
| `llm.py` | 大模型统一调用接口（LLMFactory 多厂商适配） |

### 2.2 Understanding模块 (`src/understanding/`)

意图理解模块，负责解析用户输入。

| 文件 | 职责 |
|------|------|
| `intent.py` | 意图识别（LLM为主、正则参数提取、启发式兜底），支持上下文代词消歧，注入学习记忆经验，接收环境探测提示实现发行版感知路径解析 |
| `context.py` | 上下文管理、压缩与代词消解（resolve_references） |
| `formatter.py` | 结果格式化（Markdown 表格输出） |

### 2.3 Capabilities模块 (`src/capabilities/`)

能力模块，提供系统管理功能。支持的操作均带 `verification_command` 自动验证。

| 文件 | 职责 |
|------|------|
| `registry.py` | 能力注册中心（单例，根据配置动态加载） |
| `base.py` | 能力基类（从 capabilities.json 加载命令映射） |
| `disk.py` | 磁盘管理能力（check_usage, check_inode, check_io, check_mount） |
| `file.py` | 文件操作能力（list, search, view, create_dir, create_file, delete, copy, move），含批量限制检查与操作后验证 |
| `process.py` | 进程管理能力（list, search, check_port, check_service） |
| `user.py` | 用户管理能力（list, info, create, delete），含 sudo 权限检查与操作后验证 |
| `system.py` | 系统信息能力（info, uptime, memory, cpu, network） |

### 2.4 Guardian模块 (`src/guardian/`)

安全守护模块，提供风险控制与审计。

| 文件 | 职责 |
|------|------|
| `detector.py` | 风险检测器 |
| `rules.py` | 安全规则引擎（从 guardian.json 加载） |
| `confirm.py` | 二次确认机制（人在回路） |
| `audit.py` | 操作审计日志（JSONL 格式） |

### 2.5 Connector模块 (`src/connector/`)

连接器模块，负责命令执行。

| 文件 | 职责 |
|------|------|
| `local.py` | 本地命令执行 |
| `remote.py` | SSH 远程执行（paramiko） |
| `probe.py` | 环境探测（OS、发行版、包管理器）+ 系统健康检查（check_health: 磁盘/内存使用率） |
| `shell.py` | Shell 命令封装 |

### 2.6 Voice模块 (`src/voice/`)

语音模块，提供多模态交互。

| 文件 | 职责 |
|------|------|
| `base.py` | 语音引擎基类 |
| `stt.py` | 语音识别（vosk 本地模型） |
| `local_stt.py` | 本地语音识别（faster-whisper） |
| `remote_stt.py` | API 语音识别（多厂商） |
| `local_tts.py` | 本地语音合成（edge-tts） |
| `remote_tts.py` | API 语音合成（多厂商） |

### 2.7 Interface模块 (`src/interface/`)

交互界面模块。

| 文件 | 职责 |
|------|------|
| `cli.py` | 命令行界面（typer + rich） |
| `server.py` | Web 服务（FastAPI，含前端静态文件服务） |
| `api.py` | REST API 路由（聊天、服务器管理、审计查询） |
| `websocket.py` | WebSocket 实时通信 |

---

## 三、核心流程 (LangGraph 状态机)

```
用户输入
   │
   ▼
┌──────────────┐
│  意图解析    │ ← LLM 为主、正则参数提取、启发式兜底；上下文代词消解
│ parse_intent │
└──────┬───────┘
       │
       ▼ 闲聊/未知 ──────────────────────────────────┐
       │                                              │
       ▼ 系统管理意图                                  │
┌──────────────┐                                      │
│  环境探测    │ ← 自动检测 OS/发行版/包管理器          │
│ probe_env    │   + 健康检查（磁盘/内存使用率）        │
└──────┬───────┘                                      │
       │                                              │
       ▼                                              │
┌──────────────┐                                      │
│  风险评估    │───── 低风险 ─────┐                    │
│ assess_risk  │                  │                    │
└──────┬───────┘                  │                    │
       │                          │                    │
       ▼ 高风险                   │                    │
┌──────────────┐                  │                    │
│  二次确认    │── 确认 ──┐       │  ← 人在回路       │
│ confirm      │          │       │                    │
└──────┬───────┘          │       │                    │
       │                  │       │                    │
       ▼ 拒绝             │       │                    │
┌──────────────┐          │       │                    │
│  拒绝执行    │          │       │  ← 详细原因+替代建议│
│ reject       │          │       │                    │
└──────┬───────┘          │       │                    │
       │                  │       │                    │
       │                  ▼       ▼                    │
       │            ┌──────────────┐                   │
       │            │  能力匹配    │ ← 优先使用 LLM 预测的 capability_name
       │            │ match_cap    │                   │
       │            └──────┬───────┘                   │
       │                   │                           │
       │                   ▼                           │
       │            ┌──────────────┐                   │
       │            │  任务执行    │ ← 超时自动重试 (最多2次, 指数退避)
       │            │ execute      │ ← 智能自动修复 (失败后 LLM 分析+重试)
       │            └──────┬───────┘                   │
       │                   │                           │
       │                   ▼ 失败                      │
       │            ┌──────────────┐                   │
       │            │  自动修复    │ ← 查学习记忆 → LLM 分析 → 修正重试
       │            │ auto_retry   │ ← 成功修正后提取教训存入学习记忆
       │            └──────┬───────┘                   │
       │                   │ 成功/耗尽                 │
       │                   ▼                           │
       │            ┌──────────────┐                   │
       │            │  结果验证    │ ← 创建/删除后自动验证目标状态
       │            │ verify       │                   │
       │            └──────┬───────┘                   │
       │                   │                           │
       │                   ▼                           │
       │            ┌──────────────┐                   │
       │            │  响应格式化  │ ← 风险评估说明 + 失败恢复建议
       │            │ format       │ ← 环境预警 + 进度标注
       │            └──────┬───────┘                   │
       │                   │                           │
       ▼                   ▼                           │
┌──────────────────────────────┐                      │
│       审计日志 + 记忆存储      │◄─────────────────────┘
│    (audit.jsonl + SQLite)     │
└──────────────────────────────┘
```

---

## 四、数据模型

### 4.1 AgentState (LangGraph 状态)

```python
class AgentState(TypedDict):
    user_input: str                    # 用户输入
    conversation_context: str          # 对话上下文
    intent: Optional[Intent]           # 解析后的意图
    environment: Optional[Environment] # 环境信息
    risk_assessment: Optional[RiskAssessment]  # 风险评估
    capability_result: Optional[CapabilityResult] # 执行结果
    response: Optional[AgentResponse]  # 最终响应
    awaiting_confirmation: bool        # 是否等待确认
    confirmed: bool                    # 用户是否已确认
    error: Optional[str]               # 错误信息
    executor: Optional[Any]            # 命令执行器（本地/远程）
    llm: Optional[Any]                 # LLM 实例
    health_warnings: Optional[List[str]]  # 系统健康预警（磁盘/内存不足）
    retry_count: int                   # 已重试次数
    retry_log: Optional[List[str]]     # 自动修复日志（仅内部记录，不展示给用户）
```

### 4.2 Intent (意图)

```python
@dataclass
class Intent:
    action: str           # 操作类型（如 create_file, check_usage）
    target: str           # 操作目标（如文件路径）
    parameters: dict      # 参数（path, username, name 等）
    raw_input: str        # 原始输入
    confidence: float     # 置信度
    capability_name: str  # 能力模块名称（如 file, disk）
```

### 4.3 RiskAssessment (风险评估)

```python
@dataclass
class RiskAssessment:
    level: RiskLevel      # 风险等级（LOW/MEDIUM/HIGH/CRITICAL）
    reasons: List[str]    # 风险原因
    needs_confirmation: bool  # 是否需要确认
    blocked: bool         # 是否被阻止
```

### 4.4 CapabilityResult (执行结果)

```python
@dataclass
class CapabilityResult:
    success: bool = True                      # 是否成功
    output: str = ""                          # 输出内容
    raw_output: str = ""                      # 原始输出
    commands_executed: List[str] = []         # 执行的命令
    risk_level: RiskLevel = RiskLevel.LOW     # 风险等级
    error: Optional[str] = None               # 错误信息
    verification_command: Optional[str] = None  # 验证命令
    verification_expect_success: bool = True    # 验证期望结果
```

### 4.5 AgentResponse (代理响应)

```python
@dataclass
class AgentResponse:
    success: bool = True                      # 是否成功
    message: str = ""                         # 响应消息
    commands_executed: List[str] = []         # 执行的命令
    risk_level: RiskLevel = RiskLevel.LOW     # 风险等级
    needs_confirmation: bool = False           # 是否需要确认
    confirmation_prompt: str = ""              # 确认提示
    error: Optional[str] = None               # 错误信息
    progress: Optional[str] = None            # 复合任务进度（如 "2/3"）
```

---

## 五、配置管理

### 5.1 配置文件结构

```
configs/
├── app.yaml           # 应用主配置
├── llm.yaml           # 大模型多厂商配置
├── voice.yaml         # 语音配置
├── capabilities.json  # 能力命令映射
├── guardian.json      # 安全规则（保护路径、高危模式）
└── prompts.yaml       # LLM 提示词集中管理
```

### 5.2 配置加载流程

1. 使用 `pydantic-settings` 加载配置
2. 支持环境变量覆盖 (`${ENV_VAR}`)
3. 服务启动时重置单例，确保配置热重载

---

## 六、接口设计

### 6.1 CLI 接口

```bash
# 交互模式
python main.py chat

# 单次执行
python main.py exec "查看系统内存"

# 启动 Web 服务
python main.py server
```

### 6.2 Web API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/chat` | POST | 发送消息（含 server_id 支持多服务器，返回 progress 进度信息） |
| `/api/capabilities` | GET | 获取可用能力列表 |
| `/api/system` | GET | 获取系统信息 |
| `/api/servers` | GET | 获取已连接的服务器列表 |
| `/api/servers/connect` | POST | 连接远程服务器（SSH） |
| `/api/servers/disconnect` | POST | 断开远程服务器 |
| `/api/servers/delete` | POST | 删除服务器配置 |
| `/api/servers/switch-user` | POST | 切换执行用户身份 |
| `/api/servers/reset-user` | POST | 重置为默认用户 |
| `/api/detect-ssh-user` | GET | 自动检测 SSH 登录用户 |
| `/api/sudo/status` | GET | 查询 sudo 密码状态 |
| `/api/sudo/password` | POST | 设置 sudo 密码 |
| `/api/sessions` | GET/POST | 会话列表/创建会话 |
| `/api/sessions/{id}/messages` | GET | 获取会话消息 |
| `/api/sessions/{id}` | DELETE | 删除会话 |
| `/api/clear` | POST | 清空对话历史 |
| `/api/audit` | GET | 查询审计日志 |
| `/api/memory/search` | GET | 搜索对话历史 |
| `/api/learning/stats` | GET | 获取学习记忆统计 |
| `/api/learning/lessons` | GET | 获取学习记忆列表 |
| `/api/learning/lessons/{id}` | DELETE | 删除一条学习记忆 |
| `/api/learning/export` | GET | 导出全部学习记忆为 Markdown 文档 |
| `/api/stt` | POST | 语音识别（上传 WAV 音频） |
| `/api/stt/status` | GET | 语音识别可用状态 |
| `/ws` | WebSocket | 实时通信 |

---

## 七、安全机制

### 7.1 风险等级

| 等级 | 说明 | 处理方式 |
|------|------|----------|
| LOW | 只读查询 | 直接执行 |
| MEDIUM | 修改普通文件 | 直接执行，附带安全评估说明 |
| HIGH | 系统配置变更、用户管理 | 需要确认（人在回路），提供原因与替代建议 |
| CRITICAL | 危险命令（rm -rf / 等） | 默认阻止，提供详细拦截原因与修复建议 |

### 7.2 保护路径

受保护的系统路径列表定义在 `configs/guardian.json` 中，包含：
- `/etc/passwd`, `/etc/shadow`, `/etc/sudoers` 等核心配置
- `/boot`, `/usr/bin`, `/usr/sbin`, `/bin`, `/sbin`, `/lib` 等系统目录
- Windows 的 `C:\Windows`, `C:\Windows\System32` 等

### 7.3 高危命令模式

`guardian.json` 中定义了 50+ 高危模式，覆盖：
- **文件破坏**: `rm -rf /`, `find / -delete`, `truncate -s 0`, `rm -rf /tmp/.*`
- **权限篡改**: `chmod 777`, `chmod -R 777 /`, `chmod 000`, `chown -R`
- **进程终止**: `kill -9 1`, `killall`, `pkill -9`
- **系统控制**: `shutdown`, `reboot`, `systemctl mask`, `systemctl stop firewalld`
- **网络安全**: `iptables -F`, `ufw disable`, `nc -l`, `ncat -l`
- **编码绕过**: `base64 -d | sh`, `wget | sh`, `curl | bash`
- **代码注入**: `python -c 'import os;os.system'`

### 7.4 操作范围限制

- `max_batch_operations`: 10（单次通配符删除上限）
- `max_search_results`: 50（搜索结果上限）
- 批量删除检测：`rm` + 通配符 `*`，`find / -delete`，`find / -exec rm`

### 7.5 操作后验证

关键操作执行后自动验证结果：
- 创建用户后：`id <username>` 验证用户存在
- 删除用户后：`id <username>` 验证用户不存在
- 创建文件/目录后：`test -e <path>` 验证存在
- 删除后：`test ! -e <path>` 验证不存在

### 7.6 异常自动重试

`execute_node` 中对超时类错误自动重试：
- 最多重试 2 次
- 退避间隔：1 秒、2 秒（指数退避）
- 仅对 `timeout` / `timed out` 错误重试，权限错误等不重试

### 7.6.1 智能自动修复

`auto_retry_node` 在 `execute_node` 执行失败后介入：
1. 查询学习记忆，看是否见过类似错误
2. 结合历史经验 + LLM 分析错误原因，给出修正方案（切换 capability/action/调整参数）
3. 用修正后的方案重新执行（最多2次）
4. 修正成功后，用 LLM 从修正案例中提取经验教训，存入学习记忆
5. 修复过程日志仅记录到内部日志，不暴露给用户；用户只看到最终结果或友好的错误说明

`_analyze_error_with_llm` 中的路径修复规则：
- 对于"路径不存在"类错误，LLM 会根据 OS 发行版选择正确的配置文件路径（如 Ubuntu 22.04+ 使用 `/etc/netplan/` 而非 `/etc/network/interfaces`）
- 建议使用 `file.search` 在系统中查找相关配置文件

### 7.6.2 用户友好错误提示

`_explain_error_to_user` 函数（`graph.py`）在执行失败时：
- 使用 LLM 将内部错误信息翻译为通俗易懂的中文说明
- 不暴露 shell 命令、不暴露内部重试细节
- 给出 1 条简短建议，让用户知道下一步怎么做

### 7.6.3 学习记忆系统

`src/agent/learning.py` 实现助手自我进化：
- **存储**: SQLite `learning_memory` 表，包含分类、触发模式、教训、修正方案、成功/失败标记、使用次数
- **写入**: `auto_retry_node` 修正成功后自动提取教训存入
- **自动同步**: 每次 `save_lesson` 时自动更新 `data/learning_memory.md` 文件，方便人工检查
- **读取**: 意图解析时（`intent.py`）查询相关历史经验注入 LLM 提示词，避免重复犯错
- **管理**: 提供 `/api/learning/*` 接口供查看和删除
- **导出**: `/api/learning/export` 接口返回完整的 Markdown 报告
- **去重**: 相同触发模式的记忆自动更新而非重复插入

### 7.7 环境感知预警

`probe_environment_node` 中执行健康检查：
- 磁盘使用率 >= 90%: 警告磁盘空间不足
- 内存使用率 >= 90%: 警告内存紧张
- 预警结果存储在 `AgentState.health_warnings` 中

### 7.8 审计日志

所有操作记录到 `data/audit.jsonl`，包含：
- 用户输入原文
- 意图解析结果（action, capability, parameters）
- 风险评估结果
- 执行的命令列表
- 执行结果（成功/失败）
- 时间戳
