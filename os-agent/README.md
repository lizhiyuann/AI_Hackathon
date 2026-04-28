# OS Agent - 操作系统智能代理

## 项目简介

OS Agent 是一个支持自然语言驱动的操作系统智能代理，用户通过文本或语音描述需求，代理自动解析意图、执行操作并反馈结果，实现"去命令行化"的系统管理体验。

支持本地和远程（SSH）服务器管理，具备多轮对话、复合任务分解、安全风险管控、行为审计、语音交互等完整能力。

## 功能特性

### 基础能力
- **磁盘管理**: 使用率查询、inode查询、IO监控、挂载点查看
- **文件操作**: 目录检索、文件搜索、内容查看、创建目录/文件、复制、移动
- **进程管理**: 进程列表、进程搜索、端口查询、服务状态
- **用户管理**: 用户列表、用户信息、创建/删除用户、sudo权限检查
- **系统信息**: 系统版本、运行时间、内存、CPU、网络

### 进阶能力
- **高风险识别**: 50+ 高危命令模式匹配（rm -rf、chmod 777、kill -9 1、反向 shell 等），受保护路径拦截
- **风险预警**: 高风险操作前进行二次确认，提供风险等级与原因说明（人在回路）
- **Sudo 密码弹窗**: 需要 sudo 权限的操作在确认后自动弹出密码输入框，密码设置前不执行任何命令
- **行为可解释**: 每次操作附带安全评估说明，拒绝操作提供详细原因与替代建议
- **用户友好错误提示**: 执行失败时由 LLM 生成通俗易懂的错误说明，不暴露 shell 命令和内部重试细节
- **行为审计**: 完整记录意图→决策→执行→结果的全链路日志
- **操作后状态验证**: 关键操作（创建/删除用户、文件/目录）执行后自动验证结果
- **智能自动修复**: 执行失败时自动用 LLM 分析错误原因，调整方案重试（最多2次），无需人工干预
- **学习记忆系统**: 从每次成功修正中自动提取经验教训，存入 SQLite；下次遇到类似场景直接复用历史经验，实现助手自我进化；自动同步更新 Markdown 报告
- **操作范围限制**: 批量删除上限控制（通配符场景）、搜索结果上限 50 条
- **复合任务分解**: LLM 自动判断并拆分复合任务，每步显示进度标注 `[i/total]`
- **环境感知路径解析**: 意图解析时自动探测 OS 发行版，LLM 根据发行版选择正确的配置文件路径（如 Ubuntu 使用 `/etc/netplan/`）
- **确认缓存优化**: 高风险操作确认后跳过重复的意图解析和环境探测，直接执行
- **异常自动重试**: 超时类错误自动重试最多 2 次，退避间隔 1s/2s
- **环境感知预警**: 磁盘/内存使用率超过 90% 时自动预警
- **上下文感知意图消歧**: 代词消解（"那个"、"它"等），利用对话上下文推断引用目标
- **LLM驱动意图解析**: LLM 为主、正则提取参数、启发式兜底的三层意图识别策略
- **跨平台**: 支持 Windows (PowerShell) 和 Linux 自适应命令
- **多服务器管理**: 前端支持添加/切换/断开多个 SSH 远程服务器

### 探索能力
- **语音交互**: 支持语音输入（vosk 本地 STT）和语音播报（浏览器 TTS）
- **多轮对话**: 基于 SQLite 持久化的对话记忆，支持上下文理解与代词消解
- **自我进化**: 学习记忆系统自动从错误修正中提取教训，注入后续意图解析，越用越智能
- **连续任务**: 支持多步骤任务的编排、进度可视化与统一反馈
- **前端界面**: React + TypeScript 的中英文双语 Web 界面，支持暗色模式

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.12 |
| 包管理 | uv / pip | latest |
| Web框架 | FastAPI | 0.115+ |
| AI框架 | LangChain | 1.x |
| 状态机 | LangGraph | 1.x |
| 本地STT | vosk | 0.3.45 |
| 前端 | React + TypeScript | 19+ |
| SSH | paramiko | 3.x |
| CLI | typer + rich | latest |
| 日志 | loguru | latest |
| 数据库 | SQLite (内置) | 3.x |

## 项目结构

```
os-agent/
├── src/
│   ├── agent/           # 代理核心（主代理、状态图、记忆、学习记忆、LLM）
│   ├── understanding/   # 意图理解（意图解析、上下文、格式化）
│   ├── capabilities/    # 能力模块（磁盘/文件/进程/用户/系统）
│   ├── guardian/        # 安全守护（风险检测、审计、确认）
│   ├── connector/       # 连接器（本地执行、SSH远程、环境探测）
│   ├── voice/           # 语音模块（STT/TTS 多引擎）
│   ├── interface/       # 交互界面（CLI/Web API/WebSocket）
│   └── utils/           # 工具模块（日志、辅助函数）
├── configs/             # 配置文件
│   ├── app.yaml         # 应用主配置
│   ├── llm.yaml         # 大模型多厂商配置
│   ├── voice.yaml       # 语音引擎配置
│   ├── capabilities.json # 能力模块命令配置
│   ├── guardian.json     # 安全规则配置
│   └── prompts.yaml     # LLM 提示词配置
├── frontend/            # React + TypeScript 前端
├── models/              # 本地模型（vosk 语音模型）
├── data/                # 数据存储（日志、审计、记忆数据库）
├── tests/               # 单元测试
├── docs/                # 文档（PRD、架构设计）
├── main.py              # 主入口
└── pyproject.toml       # 项目配置与依赖
```

## 快速开始

### 环境要求
- Python 3.12+
- Node.js 22+（Vite 8 要求 20.19+ 或 22.12+）

### 安装

```bash
# 克隆项目
cd os-agent

# 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安装依赖
pip install -e .
```

### 配置

1. 配置大模型（`configs/llm.yaml`）
```yaml
active_provider: "tongyi"
providers:
  tongyi:
    api_key: "your_api_key"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: "qwen3-max"
```

2. 语音配置（`configs/voice.yaml`）— 语音识别使用 vosk 本地模型

### 前端构建

首次运行或前端代码修改后需要重新构建：

```bash
cd frontend
npm install    # 安装依赖（首次）
npm run build  # 构建生产版本，输出到 frontend/dist/
```

### 运行

```bash
# ===== 前台运行（开发调试） =====

# 启动 Web 服务（含前端）
python main.py server

# 交互式聊天模式（CLI）
python main.py chat

# 执行单次命令
python main.py exec "查看磁盘使用情况"

# 查看可用能力
python main.py capabilities

# ===== 后台运行（生产部署） =====

# 使用 nohup 后台运行 Web 服务，日志输出到 data/logs/server.log
nohup .venv/bin/python -m uvicorn src.interface.server:app --host 0.0.0.0 --port 8000 > data/logs/server.log 2>&1 &

# 带热重载的后台运行（开发环境）
nohup .venv/bin/python -m uvicorn src.interface.server:app --host 0.0.0.0 --port 8000 --reload > data/logs/server.log 2>&1 &

# 查看后台进程
lsof -ti:8000

# 停止后台服务
kill $(lsof -ti:8000)

# 查看实时日志
tail -f data/logs/server.log
```

启动后访问 `http://localhost:8000` 即可使用 Web 界面。

## 使用示例

### 磁盘管理
```
查看磁盘使用情况
硬盘还有多少空间
```

### 文件操作
```
列出当前目录的文件
帮我在桌面上创建一个test文件夹
创建test11文件夹和1.txt文件    ← 复合任务自动分解
```

### 进程管理
```
查看运行中的进程
检查端口8080占用情况
```

### 系统信息
```
查看系统信息
内存使用情况
```

### 复合任务
```
在桌面上创建test11文件夹并在该文件夹创建1.txt文件
帮我在桌面上创建一个test文件夹然后在里面创建a.txt文件
```

## 多厂商大模型配置

支持以下 LLM 厂商（通过 `configs/llm.yaml` 配置，运行时热切换）：
- 通义千问 Qwen（阿里云百炼）
- 深度求索 DeepSeek
- 文心一言 ERNIE
- 智谱 GLM
- 月之暗面 Moonshot
- 百川 Baichuan
- 零一万物 Yi
- OpenAI

## 安全机制

- **风险等级**: LOW / MEDIUM / HIGH / CRITICAL 四级评估
- **受保护路径**: `/etc/passwd`, `/etc/shadow`, `/boot`, `/usr/bin` 等 17 个系统核心路径（`configs/guardian.json`）
- **高危模式匹配**: 50+ 危险命令模式，覆盖文件破坏、权限篡改、进程终止、反向 shell、编码绕过等场景
- **人在回路**: 高风险操作需用户二次确认后才执行，拒绝时提供详细原因和替代建议
- **操作范围限制**: 批量删除上限 10 个、搜索结果上限 50 条，防止大范围破坏
- **操作后验证**: 创建/删除用户和文件后自动执行验证命令，确认操作结果
- **用户友好错误提示**: 执行失败时由 LLM 生成通俗易懂的错误说明，不暴露 shell 命令和内部重试细节
- **智能自动修复**: 失败后自动分析错误原因并调整方案重试，无需人工干预
- **环境感知路径解析**: 意图解析时自动探测 OS 发行版，LLM 根据发行版选择正确的配置文件路径（如 Ubuntu 使用 `/etc/netplan/`）
- **学习记忆系统**: 自动从修正结果中提取经验教训，注入后续决策，越用越智能；提供 `/api/learning/*` 接口查看和管理；每次保存自动同步更新 `data/learning_memory.md` 报告
- **环境预警**: 磁盘/内存使用率超过 90% 时自动触发健康预警
- **审计日志**: 所有操作记录到 `data/audit.jsonl`，支持 API 查询

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat` | 发送消息（主入口） |
| GET | `/api/capabilities` | 获取可用能力列表 |
| GET | `/api/system` | 获取系统信息 |
| GET | `/api/servers` | 获取服务器列表 |
| POST | `/api/servers/connect` | 连接远程服务器 |
| POST | `/api/servers/disconnect` | 断开服务器 |
| POST | `/api/servers/delete` | 删除服务器 |
| POST | `/api/servers/switch-user` | 切换执行用户 |
| GET | `/api/detect-ssh-user` | 自动检测 SSH 登录用户 |
| GET | `/api/sudo/status` | 查询 sudo 密码状态 |
| POST | `/api/sudo/password` | 设置 sudo 密码 |
| POST | `/api/sessions` | 创建会话 |
| GET | `/api/sessions` | 获取会话列表 |
| GET | `/api/sessions/{id}/messages` | 获取会话消息 |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| GET | `/api/audit` | 查询审计日志 |
| GET | `/api/learning/stats` | 学习记忆统计 |
| GET | `/api/learning/lessons` | 学习记忆列表 |
| DELETE | `/api/learning/lessons/{id}` | 删除学习记忆 |
| GET | `/api/learning/export` | 导出学习记忆 Markdown |
| POST | `/api/stt` | 语音识别 |
| GET | `/api/stt/status` | 语音识别状态 |
| POST | `/api/clear` | 清空对话历史 |
| WS | `/ws` | WebSocket 实时通信 |

## 测试

```bash
# 运行全部单元测试
.venv/bin/python -m pytest tests/unit/ -v

# 运行指定测试模块
.venv/bin/python -m pytest tests/unit/test_learning.py -v
.venv/bin/python -m pytest tests/unit/test_graph.py -v
.venv/bin/python -m pytest tests/unit/test_api.py -v

# 运行并显示覆盖率
.venv/bin/python -m pytest tests/unit/ --tb=short -q
```

测试用例文档见 [测试用例文档.md](测试用例文档.md)。

## 文档

- [产品需求文档 PRD](docs/PRD.md)
- [架构设计文档](docs/architecture.md)
- [测试用例文档](测试用例文档.md)
- [测试结果报告](测试结果报告.md)

## 许可证

MIT License
