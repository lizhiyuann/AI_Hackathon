# 操作系统智能代理 - 产品需求文档 (PRD)

## 一、产品定位

### 1.1 产品名称
OS Agent - 操作系统智能代理

### 1.2 产品目标
构建一个支持自然语言驱动的操作系统智能代理，用户通过文本或语音描述需求，代理自动解析意图、执行操作并反馈结果，实现"去命令行化"的系统管理体验。

### 1.3 目标用户
- 服务器管理员
- 运维工程师
- 对命令行不熟悉但需要管理服务器的用户

---

## 二、能力体系

### 2.1 基础能力

| 能力模块 | 支持操作 | 风险等级 |
|----------|----------|----------|
| 磁盘管理 | 使用率查询、inode查询、IO监控、挂载点查看 | 低 |
| 文件操作 | 目录检索、文件搜索、内容查看、创建目录/文件、复制、移动 | 低~中 |
| 进程管理 | 进程列表、进程搜索、端口查询、服务状态 | 低 |
| 用户管理 | 用户列表、用户信息、创建用户、删除用户、sudo权限检查 | 高 |
| 系统信息 | 系统版本、运行时间、内存、CPU、网络 | 低 |

### 2.2 进阶能力

| 能力 | 说明 |
|------|------|
| 高风险识别 | 50+ 高危命令模式匹配，覆盖 rm -rf、chmod 777、kill init、反向 shell、编码绕过等；17 个受保护系统路径 |
| 风险预警 | 高风险操作前进行二次确认，提供风险等级与原因说明（人在回路） |
| 行为可解释 | 成功操作附带安全评估说明；拒绝操作提供详细原因与替代建议 |
| 行为审计 | 完整记录意图→决策→执行→结果的全链路日志 |
| 操作后状态验证 | 创建/删除用户和文件/目录后自动执行验证命令，确认操作结果 |
| 执行失败恢复建议 | 命令执行失败时通过 LLM 生成用户友好的错误说明，不暴露内部技术细节 |
| 操作范围限制 | 批量删除上限 10 个（通配符场景）；搜索结果上限 50 条 |
| 复合任务分解 | LLM 自动判断并拆分复合任务，每步显示进度标注 `[i/total]` |
| 智能自动修复 | 执行失败后自动用 LLM 分析错误原因，调整方案重试（最多2次），无需人工干预 |
| 学习记忆系统 | 自动从错误修正中提取经验教训存入 SQLite，注入后续意图解析提示词，实现助手自我进化；每次保存自动同步更新 Markdown 报告 |
| 环境感知路径解析 | 意图解析时自动探测 OS 发行版，LLM 根据发行版选择正确的配置文件路径（如 Ubuntu 使用 `/etc/netplan/`） |
| 确认缓存优化 | 高风险操作确认后跳过重复的意图解析和环境探测，直接执行 |
| Sudo 密码弹窗 | 需要 sudo 权限的操作在确认后自动弹出密码输入框，密码设置前不执行命令 |
| 异常自动重试 | 超时类错误自动重试最多 2 次，退避间隔 1s/2s |
| 环境感知预警 | 磁盘/内存使用率超过 90% 时自动触发健康预警 |
| 上下文感知意图消歧 | 代词消解（"那个"、"它"、"上面的"等），利用对话上下文推断引用目标 |
| LLM驱动意图解析 | LLM 为主、正则提取参数、启发式兜底的三层意图识别策略 |
| 跨平台支持 | Windows (PowerShell) 和 Linux 自适应命令执行 |
| 多服务器管理 | 支持添加/切换/断开多个 SSH 远程服务器 |

### 2.3 探索能力

| 能力 | 说明 |
|------|------|
| 语音交互 | 支持语音输入（vosk 本地STT）和语音播报（浏览器TTS） |
| 多轮对话 | 基于 SQLite 持久化的对话记忆，支持上下文理解与代词消解 |
| 连续任务 | 支持多步骤任务的编排、进度可视化与统一反馈 |
| 前端界面 | React + TypeScript 的中英文双语 Web 管理界面，支持暗色模式 |

---

## 三、技术选型

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 语言 | Python | 3.12 | 主开发语言 |
| 包管理 | uv / pip | latest | 虚拟环境和依赖管理 |
| Web框架 | FastAPI | 0.115+ | 异步API服务 |
| AI框架 | LangChain | 1.x | LLM编排 |
| 状态机 | LangGraph | 1.x | 工作流状态图编排 |
| 本地STT | vosk | 0.3.45 | 本地语音识别（中文小模型） |
| 前端 | React + TS | 19+ | Web管理界面 |
| SSH | paramiko | 3.x | 远程连接 |
| CLI | typer + rich | latest | 命令行界面 |
| 日志 | loguru | latest | 日志系统 |
| 数据库 | SQLite | 3.x | 本地存储（对话记忆） |
| 提示词管理 | pyyaml | 6.x | 集中化提示词配置 |
| 测试 | pytest | latest | 测试框架 |

---

## 四、多厂商大模型配置

### 4.1 支持的LLM厂商

通过 `configs/llm.yaml` 统一配置，支持运行时切换：

| 厂商 | API格式 | 配置项 |
|------|---------|--------|
| 通义千问 Qwen（阿里云百炼） | OpenAI兼容 | `tongyi` |
| 深度求索 DeepSeek | OpenAI兼容 | `deepseek` |
| 文心一言 ERNIE | 独立格式 | `wenxin` |
| 智谱 GLM | OpenAI兼容 | `zhipu` |
| 月之暗面 Moonshot | OpenAI兼容 | `moonshot` |
| 百川 Baichuan | OpenAI兼容 | `baichuan` |
| 零一万物 Yi | OpenAI兼容 | `yi` |
| OpenAI | 原生 | `openai` |

### 4.2 语音引擎配置

#### 语音识别 (STT)
| 引擎类型 | 技术方案 | 配置项 |
|----------|----------|--------|
| 本地模型 | vosk (中文小模型) | `voice.yaml > stt.engine: "vosk"` |
| API引擎 | 阿里云/百度/讯飞 | `voice.yaml > stt.engine: "api"` |

#### 语音合成 (TTS)
| 引擎类型 | 技术方案 | 配置项 |
|----------|----------|--------|
| 浏览器内置 | Web Speech API | 前端默认方式 |
| API引擎 | 阿里云/百度 | `voice.yaml > tts.engine: "api"` |

---

## 五、配置文件说明

| 配置文件 | 用途 |
|----------|------|
| `configs/app.yaml` | 应用主配置（端口、日志级别等） |
| `configs/llm.yaml` | 大模型多厂商配置（API Key、模型名、URL） |
| `configs/voice.yaml` | 语音识别/合成配置 |
| `configs/capabilities.json` | 能力模块命令映射配置 |
| `configs/guardian.json` | 安全规则配置（保护路径、高危模式） |
| `configs/prompts.yaml` | LLM 提示词集中配置 |

---

## 六、安全机制（人在回路）

### 6.1 风险等级

| 等级 | 说明 | 处理方式 |
|------|------|----------|
| LOW | 只读查询 | 直接执行 |
| MEDIUM | 修改普通文件 | 直接执行，附带安全评估说明 |
| HIGH | 系统配置变更、用户管理 | 需要用户确认，提供风险原因与替代建议 |
| CRITICAL | 危险命令（rm -rf / 等） | 默认阻止，提供详细拦截原因与修复建议 |

### 6.2 高危命令模式（guardian.json）

覆盖 50+ 危险命令模式，包括但不限于：
- **文件破坏**: `rm -rf /`, `find / -delete`, `truncate -s 0`
- **权限篡改**: `chmod 777`, `chmod -R 777 /`, `chown -R`
- **进程终止**: `kill -9 1`, `killall`, `pkill -9`
- **系统控制**: `shutdown`, `reboot`, `systemctl mask`, `systemctl stop firewalld`
- **网络安全**: `iptables -F`, `ufw disable`, `nc -l`（反向 shell）
- **编码绕过**: `base64 -d | sh`, `wget | sh`, `curl | bash`
- **代码注入**: `python -c 'import os;os.system'`

### 6.3 受保护路径

17 个系统核心路径受保护，禁止删除操作：
- Linux: `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`, `/boot`, `/usr/bin`, `/bin`, `/sbin`, `/lib` 等
- Windows: `C:\Windows`, `C:\Windows\System32`

### 6.4 人在回路（Human-in-the-Loop）
- 高风险操作执行前，系统返回确认请求，用户明确确认后才执行
- 用户拒绝则取消操作
- 拒绝时提供详细原因、风险等级说明和替代建议
- 所有操作（无论是否执行）均记录审计日志

### 6.5 操作后状态验证
- 创建用户后：自动执行 `id <username>` 验证用户存在
- 删除用户后：自动执行 `id <username>` 验证用户不存在
- 创建文件/目录后：自动执行 `test -e <path>` 验证存在
- 删除后：自动执行 `test -e <path>` 验证不存在

### 6.6 操作范围限制
- 单次删除文件/目录数量不超过 10 个（通配符场景）
- `rm -rf` 后跟通配符 `*` 时触发限制检查
- 搜索结果最多返回 50 条

### 6.7 审计日志
所有操作记录到 `data/audit.jsonl`，包含：
- 用户输入原文
- 意图解析结果
- 风险评估结果
- 执行的命令
- 执行结果

支持通过 `GET /api/audit` 接口查询审计日志。

---

## 七、环境搭建

### 环境要求
- Python 3.12+
- Node.js 22+（Vite 8 要求 20.19+ 或 22.12+）

```bash
# 克隆项目
cd os-agent

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安装依赖
pip install -e .

# 安装开发依赖（可选）
pip install -e ".[dev]"
```

---

## 八、启动方式

```bash
# Web 模式（推荐，含前端界面）
python main.py server

# CLI 交互模式
python main.py chat

# 单次执行
python main.py exec "查看磁盘使用情况"

# 后台运行 Web 服务（生产部署）
nohup .venv/bin/python -m uvicorn src.interface.server:app --host 0.0.0.0 --port 8000 > data/logs/server.log 2>&1 &

# 带热重载的后台运行（开发环境）
nohup .venv/bin/python -m uvicorn src.interface.server:app --host 0.0.0.0 --port 8000 --reload > data/logs/server.log 2>&1 &
```

启动后访问 `http://localhost:8000` 使用 Web 管理界面。
