"""主代理类 - 协调所有模块的核心"""
from typing import Optional
from datetime import datetime

from src.agent.config import ConfigManager
from src.agent.memory import ConversationMemory
from src.agent.planner import TaskPlanner
from src.agent.graph import compile_graph, AgentState
from src.agent.models import AgentResponse, ConversationTurn
from src.agent.llm import LLMFactory
from src.understanding.intent import IntentParser
from src.capabilities.registry import CapabilityRegistry
from src.guardian.detector import RiskDetector
from src.guardian.audit import AuditLogger
from src.connector.local import LocalExecutor
from src.connector.probe import EnvironmentProbe
from src.utils.logger import log


class OSIntelligentAgent:
    """操作系统智能代理主类"""

    def __init__(self, config: Optional[ConfigManager] = None, executor=None):
        self.config = config or ConfigManager()
        self.memory = ConversationMemory()
        self.planner = TaskPlanner()
        self.audit_logger = AuditLogger()
        self.graph = compile_graph()

        # 初始化LLM
        self.llm = LLMFactory.create(self.config)

        # 初始化意图解析器（传入LLM以支持智能解析）
        self.intent_parser = IntentParser(llm=self.llm)

        # 初始化各模块
        self.capability_registry = CapabilityRegistry()
        self.risk_detector = RiskDetector()
        self.env_probe = EnvironmentProbe()

        # 支持外部传入执行器（用于服务器切换场景）
        if executor:
            self.executor = executor
        elif self.config.connector.mode == "local":
            self.executor = LocalExecutor()
        else:
            from src.connector.remote import RemoteExecutor
            self.executor = RemoteExecutor(
                host=self.config.connector.remote_host,
                port=self.config.connector.remote_port,
                username=self.config.connector.remote_username,
                key_path=self.config.connector.remote_key_path,
            )

        # 当前会话ID（由API层设置）
        self._current_session_id = "default"

        # 多任务断点续传状态
        self._pending_tasks: list = []       # 待执行的子任务列表
        self._pending_index: int = 0         # 当前执行到第几步（0-based）
        self._completed_results: list = []   # 已完成步骤的结果
        self._completed_commands: list = []  # 已完成步骤的命令
        self._any_failed: bool = False       # 是否有失败步骤

        # 确认重放缓存 — 保存需要确认的操作的 intent/env/risk，确认后直接复用
        self._confirmed_cache: dict = {}

        log.info("OS Agent 初始化完成")

    async def process(self, user_input: str, confirmed: bool = False) -> AgentResponse:
        """处理用户输入 - 支持复合任务分解、确认断点续传"""
        try:
            if confirmed and self._pending_tasks:
                # 有未完成的多任务 → 从断点继续执行（已确认当前步骤）
                return await self._resume_pending_tasks()

            if confirmed:
                # 单任务确认 → 直接执行（跳过任务分解和再次确认）
                response = await self._process_single(user_input, confirmed=True)
                if response and not response.needs_confirmation:
                    turn = ConversationTurn(
                        timestamp=datetime.now().isoformat(),
                        user_input=user_input,
                        agent_response=response.message,
                        commands=response.commands_executed,
                    )
                    self.memory.add(turn, session_id=self._current_session_id)
                return response

            # 新的非确认请求 → 清空之前的待执行状态（取消或发起新请求）
            if self._pending_tasks:
                log.info("收到新请求，清空之前的待执行多任务状态")
                self._clear_pending()

            # 用户点"取消"时，前端发送 'cancel'，直接返回取消提示
            if user_input.strip().lower() == 'cancel':
                return AgentResponse(
                    success=True,
                    message="操作已取消。",
                )

            # 用LLM检测是否为复合任务，并拆分为子任务
            sub_tasks = self._decompose_task(user_input)

            if len(sub_tasks) <= 1:
                # 单任务 - 走标准LangGraph流程
                response = await self._process_single(user_input, confirmed)
                # 保存到记忆
                if response and not response.needs_confirmation:
                    turn = ConversationTurn(
                        timestamp=datetime.now().isoformat(),
                        user_input=user_input,
                        agent_response=response.message,
                        commands=response.commands_executed,
                    )
                    self.memory.add(turn, session_id=self._current_session_id)
                return response

            # 复合任务 - 依次执行每个子任务
            log.info(f"检测到复合任务，共 {len(sub_tasks)} 个子步骤")
            return await self._execute_multi_tasks(sub_tasks, user_input)

        except Exception as e:
            log.error(f"处理失败: {e}")
            return AgentResponse(
                success=False,
                message=f"处理请求时出错: {str(e)}",
                error=str(e),
            )

    async def _execute_multi_tasks(self, sub_tasks: list, original_input: str) -> AgentResponse:
        """执行多任务列表，遇到需要确认的步骤时保存状态并返回"""
        all_results = list(self._completed_results)
        all_commands = list(self._completed_commands)
        any_failed = self._any_failed

        total = len(sub_tasks)
        start_index = self._pending_index

        for i in range(start_index, total):
            sub_task = sub_tasks[i]
            progress_label = f"[{i+1}/{total}]"
            log.info(f"执行子任务 {progress_label}: {sub_task}")
            resp = await self._process_single(sub_task, confirmed=False)
            all_results.append(f"**{progress_label}** {sub_task}\n{resp.message}")
            all_commands.extend(resp.commands_executed)

            # 如果需要确认 → 保存状态，下次从下一步继续
            if resp.needs_confirmation:
                self._pending_tasks = sub_tasks
                self._pending_index = i  # 下次确认后从这一步重新执行（因为这步还没完成）
                self._completed_results = all_results[:-1]  # 不包含正在确认的这步
                self._completed_commands = all_commands[:-len(resp.commands_executed)]
                self._any_failed = any_failed
                # 在确认提示中附加进度信息
                resp.message = f"**{progress_label}** {sub_task}\n\n{resp.message}"
                return resp

            if not resp.success:
                any_failed = True

        # 全部完成 → 清空待执行状态
        self._pending_tasks = []
        self._pending_index = 0
        self._completed_results = []
        self._completed_commands = []
        self._any_failed = False

        combined_msg = "\n\n".join(all_results)
        if any_failed:
            combined_msg += f"\n\n---\n复合任务完成 ({total} 步，部分步骤失败)"
        else:
            combined_msg += f"\n\n---\n复合任务全部完成 ({total} 步)"

        response = AgentResponse(
            success=not any_failed,
            message=combined_msg,
            commands_executed=all_commands,
            progress=f"{total}/{total}",
        )

        # 保存到记忆
        turn = ConversationTurn(
            timestamp=datetime.now().isoformat(),
            user_input=original_input,
            agent_response=response.message,
            commands=response.commands_executed,
        )
        self.memory.add(turn, session_id=self._current_session_id)

        return response

    async def _resume_pending_tasks(self) -> AgentResponse:
        """用户确认后，从断点继续执行多任务"""
        if not self._pending_tasks:
            return AgentResponse(success=False, message="没有待执行的任务")

        # 先执行当前确认的这一步（已确认，直接执行）
        current_task = self._pending_tasks[self._pending_index]
        total = len(self._pending_tasks)
        progress_label = f"[{self._pending_index+1}/{total}]"
        log.info(f"确认后执行子任务 {progress_label}: {current_task}")

        resp = await self._process_single(current_task, confirmed=True)
        self._completed_results.append(f"**{progress_label}** {current_task}\n{resp.message}")
        self._completed_commands.extend(resp.commands_executed)

        if not resp.success:
            self._any_failed = True

        # 继续执行后续步骤
        self._pending_index += 1
        return await self._execute_multi_tasks(
            self._pending_tasks, f"(多任务续传，共 {total} 步)"
        )

    def _decompose_task(self, user_input: str) -> list:
        """用LLM判断是否为复合任务并分解"""
        # 短输入直接当单任务（省一次LLM调用）
        if len(user_input.strip()) < 10:
            return [user_input]

        try:
            from langchain_core.messages import HumanMessage
            prompt = f"""判断以下用户请求包含几个独立操作，返回JSON。

用户请求: {user_input}

规则：
1. 只返回JSON，不要多余文字
2. 询问类问题（如"xxx属于哪个用户"、"xxx在哪里"、"xxx是什么"）→ 绝对不要拆分，只有1个步骤
3. 单任务（如"查看磁盘"、"创建test文件夹"）→ steps数组只有1个元素
4. 只有明确包含多个不同操作（用"和"、"然后"、"接着"、"再"连接）才拆分
5. 复合任务（如"创建文件夹和文件"、"先建目录再建文件"）→ 拆成多个步骤
6. 每个步骤是完整的、可独立执行的操作描述
7. 后续步骤引用前面创建的资源时，必须包含完整路径，不能丢失上下文
8. 关键原则：一个问题只能对应一个操作，不要把一个问题拆成多个重复操作

返回格式：
{{"steps": ["步骤1"]}}

示例：
- "tmp在哪个用户下" → {{"steps": ["查看 /tmp 目录的所有者信息"]}}
- "帮我看一下tmp目录是什么" → {{"steps": ["查看 /tmp 目录的信息"]}}
- "创建test文件夹和1.txt文件" → {{"steps": ["创建test文件夹", "在test文件夹中创建1.txt文件"]}}
- "在桌面上创建test11文件夹并在该文件夹创建1.txt文件" → {{"steps": ["在桌面上创建test11文件夹", "在桌面上的test11文件夹中创建1.txt文件"]}}
- "查看磁盘" → {{"steps": ["查看磁盘"]}}
- "帮我在桌面上创建一个test文件夹然后在里面创建a.txt文件" → {{"steps": ["在桌面上创建一个test文件夹", "在桌面的test文件夹中创建a.txt文件"]}}
- "创建用户testuser" → {{"steps": ["创建用户testuser"]}}"""

            response = self.llm.invoke([HumanMessage(content=prompt)])
            import json
            import re
            json_match = re.search(r'\{[\s\S]*?\}', response.content)
            if json_match:
                result = json.loads(json_match.group())
                steps = result.get("steps", [user_input])
                if len(steps) > 1:
                    log.info(f"LLM任务分解: {steps}")
                    return steps
                return steps  # 单任务也由LLM判断返回
        except Exception as e:
            log.warning(f"任务分解失败，按单任务处理: {e}")

        return [user_input]

    async def _process_single(self, user_input: str, confirmed: bool = False, save_to_memory: bool = True) -> AgentResponse:
        """处理单个任务 - 经过完整的LangGraph安全流程"""
        context = self.memory.get_context(window=5, session_id=self._current_session_id)

        initial_state: AgentState = {
            "user_input": user_input,
            "conversation_context": context,
            "intent": None,
            "environment": None,
            "risk_assessment": None,
            "capability_result": None,
            "response": None,
            "awaiting_confirmation": False,
            "confirmed": confirmed,
            "error": None,
            "executor": self.executor,
            "llm": self.llm,
            "health_warnings": None,
            "retry_count": 0,
            "retry_log": None,
        }

        # 确认重放：注入缓存的 intent/environment/risk_assessment，跳过重新解析
        if confirmed and self._confirmed_cache:
            log.info(f"确认重放: 从缓存注入 intent/env/risk，跳过重复解析")
            initial_state["intent"] = self._confirmed_cache.get("intent")
            initial_state["environment"] = self._confirmed_cache.get("environment")
            initial_state["risk_assessment"] = self._confirmed_cache.get("risk_assessment")
            initial_state["health_warnings"] = self._confirmed_cache.get("health_warnings")

        result = await self.graph.ainvoke(initial_state)
        response = result.get("response")

        if response is None:
            response = AgentResponse(success=False, message="无法处理您的请求。")

        # 需要确认 → 缓存 intent/environment/risk_assessment，下次确认时复用
        if response and response.needs_confirmation and not confirmed:
            self._confirmed_cache = {
                "intent": result.get("intent"),
                "environment": result.get("environment"),
                "risk_assessment": result.get("risk_assessment"),
                "health_warnings": result.get("health_warnings"),
            }
            log.info(f"已缓存确认状态: intent={result.get('intent').action if result.get('intent') else None}")
        elif confirmed:
            # 确认执行后清空缓存（已完成）
            self._confirmed_cache = {}

        # 审计日志
        intent = result.get("intent")
        risk = result.get("risk_assessment")
        if intent:
            from src.agent.models import CapabilityResult, RiskAssessment
            cap_result = result.get("capability_result") or CapabilityResult(
                success=response.success,
                output=response.message,
                commands_executed=response.commands_executed,
                error=response.error,
            )
            risk_assessment = risk or RiskAssessment(level=response.risk_level)
            try:
                self.audit_logger.log_operation(
                    user_input=user_input,
                    intent=intent,
                    risk_assessment=risk_assessment,
                    result=cap_result,
                )
            except Exception as e:
                log.warning(f"审计日志写入失败: {e}")

        return response

    def _clear_pending(self):
        """清空多任务断点续传状态"""
        self._pending_tasks = []
        self._pending_index = 0
        self._completed_results = []
        self._completed_commands = []
        self._any_failed = False
        self._confirmed_cache = {}

    def get_capabilities(self) -> list:
        """获取所有可用能力"""
        return self.capability_registry.list_all()

    def clear_memory(self):
        """清空对话记忆"""
        self.memory.clear()
        self._clear_pending()
        log.info("对话记忆已清空")
