"""LangGraph状态图定义 - 代理工作流引擎"""
from typing import TypedDict, Optional, List, Callable, Any
from enum import Enum
from pathlib import Path
import yaml

from langgraph.graph import StateGraph, END
from src.agent.models import (
    Intent, Environment, RiskAssessment,
    CapabilityResult, AgentResponse, RiskLevel
)
from src.utils.logger import log

# 提示词配置路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
PROMPTS_PATH = PROJECT_ROOT / "configs" / "prompts.yaml"


def _load_prompts() -> dict:
    """加载提示词配置"""
    if PROMPTS_PATH.exists():
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class AgentState(TypedDict):
    """代理状态 - LangGraph状态图的状态定义"""
    user_input: str                          # 用户输入
    conversation_context: str                # 对话上下文
    intent: Optional[Intent]                 # 解析后的意图
    environment: Optional[Environment]       # 环境信息
    risk_assessment: Optional[RiskAssessment]  # 风险评估结果
    capability_result: Optional[CapabilityResult]  # 能力执行结果
    response: Optional[AgentResponse]        # 最终响应
    awaiting_confirmation: bool              # 是否等待用户确认
    confirmed: bool                          # 用户是否已确认
    error: Optional[str]                     # 错误信息
    executor: Optional[Any]                  # 命令执行器（支持远程服务器）
    llm: Optional[Any]                       # LLM实例（用于智能意图解析）
    health_warnings: Optional[List[str]]     # 系统健康预警
    retry_count: int                         # 已重试次数
    retry_log: Optional[List[str]]           # 自动修复日志（展示给用户的过程记录）


class RouteAction(str, Enum):
    """路由动作"""
    CONFIRM = "confirm"
    EXECUTE = "execute"
    REJECT = "reject"


# ============ 节点函数 ============

def parse_intent_node(state: AgentState) -> AgentState:
    """意图解析节点 - confirmed时复用缓存，解析时注入环境信息"""
    # 确认重放：如果已有 intent（从缓存注入），跳过 LLM 调用
    if state.get("intent") and state.get("confirmed"):
        log.info(f"确认重放，跳过意图解析，复用: action={state['intent'].action}, capability={state['intent'].capability_name}")
        return state

    # 先探测环境，获取 distro 信息传给 LLM，避免猜错路径
    env_hint = ""
    try:
        executor = state.get("executor")
        if executor and hasattr(executor, 'host'):
            env = _detect_remote_environment(executor)
        else:
            from src.connector.probe import EnvironmentProbe
            env = EnvironmentProbe().detect()
        if env and env.distro_name:
            env_hint = f"{env.os_name}/{env.distro_name}"
        elif env and env.os_name:
            env_hint = env.os_name
        state["environment"] = env
    except Exception as e:
        log.debug(f"意图解析前环境探测失败（不影响解析）: {e}")

    from src.understanding.intent import IntentParser
    llm = state.get("llm")
    parser = IntentParser(llm=llm)
    intent = parser.parse(state["user_input"], state.get("conversation_context", ""), env_hint=env_hint)
    state["intent"] = intent
    log.info(f"意图解析: action={intent.action}, confidence={intent.confidence}, env={env_hint}")
    return state


def probe_environment_node(state: AgentState) -> AgentState:
    """环境探测节点 - 已探测或确认重放时跳过环境探测，但始终执行健康检查"""
    from src.connector.probe import EnvironmentProbe

    executor = state.get("executor")

    if not state.get("environment"):
        # 环境未探测过（正常流程中的首次进入）
        if executor and hasattr(executor, 'host'):
            env = _detect_remote_environment(executor)
        else:
            probe = EnvironmentProbe()
            env = probe.detect()
        state["environment"] = env
        log.info(f"环境探测: os={env.os_name}, user={env.current_user}")
    else:
        log.info(f"环境已探测，跳过重复探测: os={state['environment'].os_name}")

    # 始终执行健康检查（仅第一次）
    if not state.get("health_warnings"):
        probe = EnvironmentProbe()
        try:
            if executor and hasattr(executor, 'host'):
                warnings = probe.check_health(executor=executor)
            else:
                warnings = probe.check_health()
            if warnings:
                state["health_warnings"] = warnings
                for w in warnings:
                    log.warning(f"环境预警: {w}")
        except Exception as e:
            log.debug(f"健康检查失败（不影响主流程）: {e}")

    return state


def _detect_remote_environment(executor) -> 'Environment':
    """通过远程执行器探测服务器环境"""
    from src.agent.models import Environment
    import re
    
    env = Environment()
    env.os_name = "Linux"
    
    try:
        # 获取发行版信息
        result = executor.execute("cat /etc/os-release 2>/dev/null || cat /etc/lsb-release 2>/dev/null || echo UNKNOWN")
        if result and result.success:
            content = result.output
            for line in content.split("\n"):
                if line.startswith("ID="):
                    distro_id = line.split("=")[1].strip().strip('"')
                    env.distro_name = _normalize_distro_name_remote(distro_id)
                elif line.startswith("VERSION_ID="):
                    env.distro_version = line.split("=")[1].strip().strip('"')
                elif line.startswith("NAME=") and not env.distro_name:
                    name = line.split("=")[1].strip().strip('"')
                    env.distro_name = name
        
        # 获取内核信息
        result = executor.execute("uname -r")
        if result and result.success:
            env.kernel = result.output.strip()
        
        # 获取主机名
        result = executor.execute("hostname")
        if result and result.success:
            env.hostname = result.output.strip()
        
        # 获取用户名
        result = executor.execute("whoami")
        if result and result.success:
            env.current_user = result.output.strip()
        
        # 获取包管理器
        result = executor.execute("which dnf 2>/dev/null && echo dnf || (which yum 2>/dev/null && echo yum || (which apt 2>/dev/null && echo apt || echo unknown))")
        if result and result.success:
            env.package_manager = result.output.strip().split('\n')[-1]
        
        log.info(f"远程环境探测完成: os={env.os_name}, distro={env.distro_name}, user={env.current_user}")
    except Exception as e:
        log.warning(f"远程环境探测失败: {e}")
    
    return env


def _normalize_distro_name_remote(distro_id: str) -> str:
    """标准化发行版名称"""
    distro_map = {
        "centos": "CentOS", "rhel": "RHEL", "ubuntu": "Ubuntu",
        "debian": "Debian", "fedora": "Fedora", "openeuler": "openEuler",
        "kylin": "Kylin", "uos": "UOS", "deepin": "Deepin",
        "alinux": "Alibaba Cloud Linux", "tencentos": "TencentOS",
        "anolis": "Anolis OS", "bclinux": "BigCloud Linux",
    }
    return distro_map.get(distro_id.lower(), distro_id)


def assess_risk_node(state: AgentState) -> AgentState:
    """风险评估节点 - confirmed时复用缓存"""
    # 确认重放：如果已有 risk_assessment（从缓存注入），跳过评估
    if state.get("risk_assessment") and state.get("confirmed"):
        log.info(f"确认重放，跳过风险评估，复用: level={state['risk_assessment'].level}")
        return state

    from src.guardian.detector import RiskDetector
    detector = RiskDetector()
    intent = state.get("intent")
    env = state.get("environment")
    if intent and env:
        assessment = detector.assess(intent, env)
        state["risk_assessment"] = assessment
        log.info(f"风险评估: level={assessment.level}, blocked={assessment.blocked}")
    return state


def request_confirmation_node(state: AgentState) -> AgentState:
    """请求二次确认节点"""
    state["awaiting_confirmation"] = True
    assessment = state.get("risk_assessment")
    if assessment:
        reasons_text = "\n".join(f"  - {r}" for r in assessment.reasons)
        state["response"] = AgentResponse(
            success=True,
            message=f"该操作存在风险 ({assessment.level.value}):\n{reasons_text}\n\n是否继续执行？",
            needs_confirmation=True,
            risk_level=assessment.level,
        )
    return state


def match_capability_node(state: AgentState) -> AgentState:
    """能力匹配节点 - 优先使用LLM给出的capability_name"""
    from src.capabilities.registry import CapabilityRegistry
    registry = CapabilityRegistry()
    intent = state.get("intent")
    if intent:
        # 优先使用LLM解析出的 capability_name
        if intent.capability_name:
            capability = registry.get(intent.capability_name)
            if capability and capability.supports(intent.action):
                log.info(f"能力匹配(LLM): {capability.name}.{intent.action}")
                return state
        # 回退到按 action 查找
        capability = registry.find(intent.action)
        if capability:
            intent.capability_name = capability.name
            log.info(f"能力匹配(查找): {capability.name}.{intent.action}")
        else:
            log.warning(f"未找到匹配的能力: capability={intent.capability_name}, action={intent.action}")
            state["error"] = f"暂不支持的操作：{intent.capability_name}.{intent.action}" if intent.capability_name else f"暂不支持的操作：{intent.action}"
    return state


def execute_node(state: AgentState) -> AgentState:
    """执行命令节点 - 支持异常自动重试（仅超时类错误）"""
    import time
    from src.capabilities.registry import CapabilityRegistry
    registry = CapabilityRegistry()
    intent = state.get("intent")
    env = state.get("environment")
    executor = state.get("executor")

    # 如果前面已经有错误（如能力匹配失败），直接跳过执行
    if state.get("error"):
        log.info(f"跳过执行，已有错误: {state['error']}")
        return state

    if intent and intent.capability_name:
        capability = registry.get(intent.capability_name)
        if capability and env:
            max_retries = 2
            retry_delays = [1, 2]

            for attempt in range(max_retries + 1):
                try:
                    result = capability.execute(
                        action=intent.action,
                        parameters=intent.parameters,
                        env=env,
                        executor=executor,
                    )
                    state["capability_result"] = result
                    log.info(f"执行完成: success={result.success}, attempt={attempt + 1}")
                    break
                except Exception as e:
                    error_msg = str(e)
                    is_timeout = "timeout" in error_msg.lower() or "timed out" in error_msg.lower()

                    if is_timeout and attempt < max_retries:
                        delay = retry_delays[attempt]
                        log.warning(f"命令执行超时，{delay}秒后重试 (第{attempt + 1}次): {error_msg}")
                        time.sleep(delay)
                        continue
                    else:
                        state["error"] = error_msg
                        log.error(f"执行失败: {e}")
                        break

    return state


def verify_result_node(state: AgentState) -> AgentState:
    """操作后状态验证节点 - 对关键操作自动执行验证命令"""
    result = state.get("capability_result")
    executor = state.get("executor")
    intent = state.get("intent")

    if not result or not result.success or not result.verification_command:
        return state

    try:
        verify_result = executor.execute(result.verification_command)
        expected_success = result.verification_expect_success

        if expected_success:
            # 创建类操作：期望验证命令成功（目标存在）
            if "EXISTS" in verify_result.output:
                # 检查是否包含文件内容
                if "---CONTENT_START---" in verify_result.output:
                    content_start = verify_result.output.index("---CONTENT_START---") + len("---CONTENT_START---")
                    content_end = verify_result.output.index("---CONTENT_END---")
                    file_content = verify_result.output[content_start:content_end].strip()
                    result.output += f"\n\n**验证通过:** 文件已创建，内容如下：\n```\n{file_content}\n```"
                else:
                    result.output += "\n\n**验证通过:** 目标资源已确认存在。"
            elif "NOT_FOUND" in verify_result.output:
                result.output += "\n\n**验证警告:** 未能确认资源是否成功创建。"
            else:
                result.output += f"\n\n**验证结果:** {verify_result.output.strip()}"
        else:
            # 删除类操作：期望目标不存在
            if "DELETED" in verify_result.output:
                result.output += "\n\n**验证通过:** 目标资源已确认成功删除。"
            elif "STILL_EXISTS" in verify_result.output:
                result.output += "\n\n**验证警告:** 目标资源仍然存在，删除可能未完全成功。"
            else:
                result.output += f"\n\n**验证结果:** {verify_result.output.strip()}"

        log.info(f"操作验证完成: {result.verification_command}, output={verify_result.output.strip()[:100]}")
    except Exception as e:
        log.warning(f"操作验证失败: {e}")
        result.output += f"\n\n**验证失败:** 无法确认操作结果 ({str(e)[:80]})"

    state["capability_result"] = result
    return state


def auto_retry_node(state: AgentState) -> AgentState:
    """执行失败后自动分析错误并调整方案重试（最多2次），同时从成功修正中学习"""
    import time

    result = state.get("capability_result")
    intent = state.get("intent")
    env = state.get("environment")
    executor = state.get("executor")
    user_input = state.get("user_input", "")
    retry_count = state.get("retry_count", 0)
    retry_log = state.get("retry_log") or []

    MAX_RETRIES = 2

    # 没有结果、结果成功、超过重试次数 → 跳过
    if not result or result.success or retry_count >= MAX_RETRIES:
        return state

    error = result.error or result.output or ""
    if not error:
        return state

    # ===== 第一步：查询学习记忆，看看是否见过类似错误 =====
    fix_hint = None
    try:
        from src.agent.learning import LearningMemory
        learning = LearningMemory()
        cap_name = intent.capability_name if intent else ""
        past_lessons = learning.recall(user_input, category=cap_name, limit=3)
        if past_lessons:
            # 用学习记忆辅助分析
            fix_hint = _analyze_with_learning(user_input, error, result.commands_executed, intent, past_lessons)
            if fix_hint:
                retry_log.append(f"第{retry_count + 1}次修复（基于历史经验）：{fix_hint.get('explanation', '')}")
    except Exception as e:
        log.debug(f"查询学习记忆失败: {e}")

    # ===== 第二步：如果没有从记忆中得到方案，用 LLM 分析 =====
    if not fix_hint:
        fix_hint = _analyze_error_with_llm(user_input, error, result.commands_executed, intent)
        if not fix_hint:
            retry_log.append(f"第{retry_count + 1}次重试：无法自动分析错误原因")
            state["retry_log"] = retry_log
            return state
        retry_log.append(f"第{retry_count + 1}次自动修复：{fix_hint.get('explanation', '')}")

    # ===== 第三步：执行修正 =====
    fixed_action = fix_hint.get("action") or (intent.action if intent else "")
    fixed_params = {**(intent.parameters if intent else {}), **(fix_hint.get("parameters") or {})}
    fixed_capability_name = fix_hint.get("capability") or (intent.capability_name if intent else "")

    if fix_hint.get("capability") or fix_hint.get("action"):
        from src.capabilities.registry import CapabilityRegistry
        registry = CapabilityRegistry()
        capability = registry.get(fixed_capability_name)
        if not capability:
            retry_log.append(f"  -> 建议的能力 {fixed_capability_name} 不存在，跳过重试")
            state["retry_log"] = retry_log
            return state
    else:
        from src.capabilities.registry import CapabilityRegistry
        registry = CapabilityRegistry()
        capability = registry.get(fixed_capability_name) if fixed_capability_name else None

    if not capability:
        state["retry_log"] = retry_log
        return state

    try:
        time.sleep(0.5)
        new_result = capability.execute(
            action=fixed_action,
            parameters=fixed_params,
            env=env,
            executor=executor,
        )
        state["capability_result"] = new_result
        state["retry_count"] = retry_count + 1
        if new_result.success:
            retry_log.append(f"  -> 重试成功")
            log.info(f"自动修复重试成功 (第{retry_count + 1}次): {fixed_action}")
            # ===== 成功修正 → 提取教训存入学习记忆 =====
            _save_lesson_async(user_input, intent, error, fix_hint, True)
        else:
            retry_log.append(f"  -> 重试仍失败: {new_result.error or new_result.output}")
            log.warning(f"自动修复重试仍失败 (第{retry_count + 1}次)")
            # 失败也记录，避免重复同样的错误方案
            _save_lesson_async(user_input, intent, error, fix_hint, False)
        state["retry_log"] = retry_log
    except Exception as e:
        retry_log.append(f"  -> 重试异常: {str(e)[:80]}")
        state["retry_log"] = retry_log
        state["retry_count"] = retry_count + 1  # 异常也累加重试次数，避免无限循环
        log.error(f"自动修复重试异常: {e}")

    # 清除 error 状态，让流程继续（错误信息已保存在 result 中）
    state["error"] = None
    return state


def _analyze_with_learning(
    user_input: str, error: str, commands: list,
    intent: Optional[Intent], past_lessons: list
) -> Optional[dict]:
    """结合学习记忆分析错误，给出修正方案"""
    try:
        from src.agent.llm import LLMFactory
        from src.agent.config import ConfigManager
        from src.agent.learning import LearningMemory
        from langchain_core.messages import HumanMessage
        import json

        config = ConfigManager()
        llm = LLMFactory.create(config)

        cap = intent.capability_name if intent else "unknown"
        act = intent.action if intent else "unknown"
        params = intent.parameters if intent else {}
        cmd_str = ", ".join(commands) if commands else "无"

        learning = LearningMemory()
        lessons_text = learning.format_for_prompt(past_lessons)

        prompt = f"""你是一个操作系统命令自动修复器。一条命令执行失败了，请结合历史经验分析原因并给出修正方案。

用户请求：{user_input}
当前能力：{cap}，当前操作：{act}
当前参数：{json.dumps(params, ensure_ascii=False)}
执行的命令：{cmd_str}
错误信息：{error}

{lessons_text}

请返回 JSON 格式的修正方案（只返回 JSON）：
{{
  "capability": "修正后的能力名（如不需要修正则保持原值）",
  "action": "修正后的操作（如不需要修正则保持原值）",
  "parameters": {{"修正后的参数（如不需要修正则传空对象）"}},
  "explanation": "一句话说明修正理由"
}}"""

        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            result = json.loads(text[first_brace:last_brace + 1])
            log.info(f"基于学习记忆的修正方案: {result}")
            return result
    except Exception as e:
        log.warning(f"基于学习记忆分析失败: {e}")

    return None


def _save_lesson_async(user_input: str, intent: Optional[Intent], error: str, fix_hint: dict, success: bool):
    """异步提取并保存学习教训"""
    try:
        from src.agent.learning import LearningMemory, extract_lesson_from_retry

        original_intent = {}
        if intent:
            original_intent = {
                "capability": intent.capability_name,
                "action": intent.action,
                "parameters": intent.parameters,
            }

        lesson = extract_lesson_from_retry(
            user_input=user_input,
            original_intent=original_intent,
            error=error,
            fix_hint=fix_hint,
            final_result_success=success,
        )

        if lesson:
            learning = LearningMemory()
            learning.save_lesson(
                category=lesson.get("category", "general"),
                trigger_pattern=lesson.get("trigger_pattern", ""),
                lesson=lesson.get("lesson", ""),
                original_error=lesson.get("original_error", error),
                correction_action=lesson.get("correction_action", fix_hint.get("action", "")),
                correction_params=lesson.get("correction_params"),
                success=lesson.get("success", success),
            )
    except Exception as e:
        log.warning(f"保存学习教训失败: {e}")


def _analyze_error_with_llm(user_input: str, error: str, commands: list, intent: Optional[Intent]) -> Optional[dict]:
    """用 LLM 分析执行失败的原因，给出修正方案"""
    try:
        from src.agent.llm import LLMFactory
        from src.agent.config import ConfigManager
        from langchain_core.messages import HumanMessage
        import json

        config = ConfigManager()
        llm = LLMFactory.create(config)

        cap = intent.capability_name if intent else "unknown"
        act = intent.action if intent else "unknown"
        params = intent.parameters if intent else {}
        cmd_str = ", ".join(commands) if commands else "无"

        # 可用的 capability 和 action
        from src.capabilities.registry import CapabilityRegistry
        registry = CapabilityRegistry()
        caps_desc = []
        for c in registry.list_all():
            caps_desc.append(f"- {c['name']}: {', '.join(c['actions'])}")

        prompt = f"""你是一个操作系统命令自动修复器。一条命令执行失败了，请分析原因并给出修正方案。

用户请求：{user_input}
当前能力：{cap}，当前操作：{act}
当前参数：{json.dumps(params, ensure_ascii=False)}
执行的命令：{cmd_str}
错误信息：{error}

可用能力和操作：
{chr(10).join(caps_desc)}

重要修复规则：
1. 如果错误是"路径不存在"或"文件未找到"，请考虑：
   - Linux 常见配置文件路径替代方案（例如 Ubuntu 22.04+ 使用 netplan: /etc/netplan/ 而非 /etc/network/interfaces）
   - 不同发行版的配置文件位置差异
   - 使用 file.search 操作在系统中查找相关配置文件
2. 如果用户请求模糊（如"网络配置文件"），尝试多个可能的路径
3. 可以建议使用 file.search 操作在常见目录中搜索相关文件

请返回 JSON 格式的修正方案（只返回 JSON，不要其他内容）：
{{
  "capability": "修正后的能力名（如不需要修正则保持原值）",
  "action": "修正后的操作（如不需要修正则保持原值）",
  "parameters": {{"修正后的参数（如不需要修正则传空对象）"}},
  "explanation": "一句话说明你做了什么修正"
}}

示例：
- 用户说"查看 xxx"，如果是目录则 action 从 view 改为 list
- 用户说"查找 xxx"，如果是文件名则 capability=file, action=search, parameters.name=xxx
- 如果 /etc/network/interfaces 不存在，尝试搜索 /etc/netplan/ 或其他网络配置文件"""

        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            result = json.loads(text[first_brace:last_brace + 1])
            log.info(f"LLM 自动修复方案: {result}")
            return result
    except Exception as e:
        log.warning(f"LLM 分析错误失败: {e}")

    return None


def route_after_execute(state: AgentState) -> str:
    """执行后的路由：失败时尝试自动修复，成功或已重试过则继续"""
    result = state.get("capability_result")
    retry_count = state.get("retry_count", 0)

    if result and not result.success and retry_count < 2:
        # 不可修复的错误直接跳过 auto-retry（重试多少次都没用）
        error = (result.error or result.output or "").lower()
        intent = state.get("intent")
        cap_name = intent.capability_name if intent else ""

        # 文件/目录操作的"不存在"是可重试的（LLM 可能猜错路径，应尝试替代路径）
        # 其他操作的"不存在"是不可重试的（如用户不存在就不存在）
        non_retriable = [
            "no such user",
            "不允许", "not allowed",
            "请指定", "权限不足",
            # sudo 密码相关错误（需要用户交互，不是命令本身的问题）
            "sudo 密码", "sudo password",
            "需要 sudo 密码",
            "密码错误",
        ]
        # 非文件操作的"路径不存在"才是不可重试的
        if cap_name != "file":
            non_retriable.extend(["不存在", "not found"])

        if any(kw in error for kw in non_retriable):
            return "verify_result"
        return "auto_retry"
    return "verify_result"


def _summarize_result_with_llm(user_input: str, raw_output: str, intent: Optional[Intent]) -> Optional[str]:
    """用 LLM 对执行结果生成智能摘要，先回答用户问题再附详情"""
    try:
        from src.agent.llm import LLMFactory
        from src.agent.config import ConfigManager
        from langchain_core.messages import HumanMessage

        config = ConfigManager()
        llm = LLMFactory.create(config)

        action = intent.action if intent else ""
        cap = intent.capability_name if intent else ""

        # 只取前80行避免太长
        output_lines = raw_output.strip().split("\n")
        truncated = "\n".join(output_lines[:80])
        if len(output_lines) > 80:
            truncated += f"\n... (共 {len(output_lines)} 行)"

        prompt = f"""你是一个操作系统助手。用户问了一个问题，系统执行了命令并拿到了结果。请根据结果，先用1-2句话直接回答用户的问题（总结部分），再用"### 详情"分隔，列出关键信息的 Markdown 表格或列表（详情部分）。

## 用户问题：
{user_input}

## 执行的操作：{cap}/{action}

## 执行结果：
{truncated}

## 输出要求：
- 先用简洁中文直接回答用户的问题（不要重复问题，直接给答案）
- 然后空一行，写 `### 详情`
- 详情部分用 Markdown 格式展示关键数据（表格或列表）
- 如果数据很多，只列出最重要的几个，说明"共N项，展示前M项"
- 不要编造结果中没有的信息"""

        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        log.warning(f"LLM 摘要生成失败: {e}")
        return None


def format_response_node(state: AgentState) -> AgentState:
    """格式化响应节点"""
    from src.understanding.formatter import ResponseFormatter
    formatter = ResponseFormatter()

    intent = state.get("intent")
    result = state.get("capability_result")
    error = state.get("error")
    user_input = state.get("user_input", "")

    # 处理闲聊意图或未知意图 - 使用LLM生成回复
    is_chat = intent and intent.capability_name == "chat"
    is_unknown = intent and (intent.action == "unknown" or intent.capability_name == "" or intent.capability_name == "unknown")
    
    if is_chat or is_unknown:
        log.info(f"检测到闲聊/未知意图，使用LLM生成回复: capability={intent.capability_name}, action={intent.action}")
        try:
            context = state.get("conversation_context", "")
            response = _generate_chat_response_with_llm(intent, user_input, context)
            state["response"] = response
        except Exception as e:
            log.error(f"LLM闲聊回复失败: {e}")
            state["response"] = AgentResponse(
                success=True,
                message="你好！有什么我可以帮你的吗？",
                commands_executed=[],
            )
        return state

    # 处理需要澄清的意图 - 返回澄清问题，不执行操作
    if intent and intent.needs_clarification and intent.clarification_question:
        log.info(f"需要澄清: {intent.clarification_question}")
        state["response"] = AgentResponse(
            success=True,
            message=intent.clarification_question,
            commands_executed=[],
        )
        return state

    # 处理系统管理意图
    if error:
        user_friendly = _explain_error_to_user(user_input, error, intent)
        state["response"] = AgentResponse(
            success=False,
            message=user_friendly or f"操作执行失败：{error}",
            error=error,
        )
    elif result:
        response = formatter.format(result)
        # 对成功的结果，用 LLM 生成智能摘要（先总结后详情）
        if result.success and result.output:
            output_len = len(result.output.strip().split("\n"))
            if output_len > 5:
                summary = _summarize_result_with_llm(user_input, result.output, intent)
                if summary:
                    response.message = summary
        # 失败结果：只给用户简洁的错误说明，不暴露内部重试细节
        elif not result.success:
            # 如果有重试日志且最终仍然失败，说明内部已尽力修复
            retry_log = state.get("retry_log")
            if retry_log:
                log.info(f"自动修复已尝试但最终失败，retry_log: {retry_log}")
            # 使用 LLM 生成用户友好的错误说明（非技术语言，无 shell 命令）
            err = result.error or result.output or "未知错误"
            user_friendly = _explain_error_to_user(user_input, err, intent)
            if user_friendly:
                response.message = user_friendly
        # 追加环境健康预警（仅在查询磁盘/内存/系统时）
        health_warnings = state.get("health_warnings")
        if health_warnings and intent and intent.capability_name in ("disk", "system"):
            warnings_text = "\n".join(f"  - {w}" for w in health_warnings)
            response.message = f"{response.message}\n\n---\n> **环境预警:**\n{warnings_text}"
        state["response"] = response
    else:
        # 没有执行结果时，也尝试用LLM回复
        log.info(f"没有执行结果，尝试用LLM回复")
        try:
            context = state.get("conversation_context", "")
            response = _generate_chat_response_with_llm(intent, user_input, context)
            state["response"] = response
        except Exception as e:
            log.error(f"LLM回复失败: {e}")
            state["response"] = AgentResponse(
                success=True,
                message="你好！有什么我可以帮你的吗？",
                commands_executed=[],
            )

    return state


def _generate_chat_response_with_llm(intent: Intent, user_input: str, conversation_context: str = "") -> AgentResponse:
    """使用LLM生成回复（闲聊+通用场景）"""
    try:
        from src.agent.llm import LLMFactory
        from src.agent.config import ConfigManager
        from langchain_core.messages import HumanMessage, SystemMessage
        
        config = ConfigManager()
        llm = LLMFactory.create(config)
        
        # 从配置文件加载系统提示词
        prompts = _load_prompts()
        system_prompt = prompts.get("system_prompt", "你是一个专业的操作系统智能代理。请用中文回复。")
        chat_prompt = prompts.get("chat_prompt", "请用中文自然地回复，保持友好专业的语气。")
        
        # 如果有对话上下文，加入到消息中
        context_msg = ""
        if conversation_context:
            context_msg = f"\n\n最近的对话记录:\n{conversation_context}"
        
        messages = [
            SystemMessage(content=system_prompt + "\n\n" + chat_prompt),
            HumanMessage(content=user_input + context_msg)
        ]
        
        response = llm.invoke(messages)
        
        return AgentResponse(
            success=True,
            message=response.content,
            commands_executed=[],
        )
    except Exception as e:
        log.error(f"LLM回复生成失败: {e}")
        # 回退到预设回复
        return _handle_chat_response(intent)


def _handle_chat_response(intent: Intent) -> AgentResponse:
    """处理闲聊意图的响应"""
    import random
    from datetime import datetime
    
    action = intent.action
    responses = {
        "greeting": [
            "你好！我是OS智能代理，很高兴为您服务！",
            "嗨！有什么可以帮助您的吗？",
            "您好！请告诉我您需要什么帮助。",
            "你好啊！我是您的操作系统助手。",
        ],
        "thanks": [
            "不客气！如果还有其他问题，随时告诉我。",
            "很高兴能帮到您！",
            "不用谢，这是我应该做的。",
            "不客气！有什么其他需要帮助的吗？",
        ],
        "goodbye": [
            "再见！祝您一切顺利！",
            "拜拜！有需要随时找我。",
            "下次见！祝您有美好的一天。",
            "再见！期待下次为您服务。",
        ],
        "help": [
            "我可以帮助您管理操作系统，包括：\n- 查看磁盘使用情况\n- 管理文件和目录\n- 监控系统进程\n- 用户管理\n- 系统信息查询\n\n试试说'查看磁盘'或'查看进程'吧！",
            "我是您的操作系统助手，可以帮您执行各种系统管理任务。例如：\n- '查看磁盘' - 显示磁盘使用情况\n- '查看进程' - 列出运行中的进程\n- '查看用户' - 显示系统用户\n\n需要什么帮助吗？",
        ],
        "how_are_you": [
            "我很好，谢谢关心！随时准备为您服务。",
            "我很好，正在等待您的指令。",
            "我很好，感谢您的关心！有什么需要帮助的吗？",
        ],
        "who_are_you": [
            "我是OS智能代理，一个专门用于操作系统管理的AI助手。",
            "我是您的操作系统助手，可以帮助您管理服务器。",
            "我是OS Agent，一个智能操作系统管理代理。",
        ],
        "what_can_you_do": [
            "我可以帮助您：\n- 管理磁盘和存储\n- 监控系统进程\n- 管理用户账户\n- 查看系统信息\n- 执行各种系统管理命令\n\n请告诉我您需要什么帮助！",
            "我能帮您完成这些任务：\n1. 磁盘空间管理\n2. 进程监控\n3. 用户管理\n4. 系统信息查询\n5. 文件操作\n\n试试看吧！",
        ],
        "joke": [
            "为什么程序员喜欢黑暗模式？因为光会吸引bug！",
            "程序员最讨厌的两件事：1. 别人不写注释 2. 自己写注释",
            "为什么程序员总是分不清万圣节和圣诞节？因为Oct 31 == Dec 25",
        ],
        "weather": [
            "抱歉，我无法获取实时天气信息。我可以帮您查看系统状态。",
            "我专注于系统管理，无法获取天气信息。需要我帮您查看系统状态吗？",
        ],
        "time": [
            f"当前时间：{datetime.now().strftime('%H:%M:%S')}",
            f"现在时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}",
        ],
        "date": [
            f"今天是：{datetime.now().strftime('%Y年%m月%d日')}",
            f"当前日期：{datetime.now().strftime('%Y年%m月%d日 %A')}",
        ],
    }
    
    # 获取对应的回复列表
    response_list = responses.get(action, ["我明白了，有什么需要帮助的吗？"])
    
    # 随机选择一个回复
    message = random.choice(response_list)
    
    return AgentResponse(
        success=True,
        message=message,
        commands_executed=[],
    )


def _explain_error_to_user(user_input: str, error: str, intent=None) -> str:
    """将内部错误信息翻译为用户友好的说明（不暴露 shell 命令、不暴露内部重试细节）"""
    try:
        from src.agent.llm import LLMFactory
        from src.agent.config import ConfigManager
        from langchain_core.messages import HumanMessage

        config = ConfigManager()
        llm = LLMFactory.create(config)

        cap = intent.capability_name if intent else "unknown"
        action = intent.action if intent else "unknown"

        prompt = f"""你是一个友好的操作系统助手。用户请求的操作执行失败了，请用简洁通俗的中文解释问题原因，并说明用户可以怎么做。

用户请求：{user_input}
操作类型：{cap}/{action}
错误信息：{error}

要求：
- 用非技术用户能理解的语言，不要给出 shell 命令或技术细节
- 如果是文件/目录不存在，直接告诉用户"目标文件/目录不存在"
- 如果是权限问题，告诉用户"没有足够的权限执行此操作"
- 如果是用户/账号问题，直接说明原因
- 可以给出1条简短建议，让用户知道下一步怎么做
- 不要使用 markdown 格式，直接给出文本
- 不超过2句话"""

        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        log.warning(f"生成用户友好错误说明失败: {e}")

    return f"操作执行失败：{error}"


def reject_node(state: AgentState) -> AgentState:
    """拒绝执行节点 - 提供详细拒绝说明与替代建议"""
    assessment = state.get("risk_assessment")
    intent = state.get("intent")
    raw_input = state.get("user_input", "")

    reasons = "\n".join(f"  - {r}" for r in assessment.reasons) if assessment else "未知原因"
    risk_level = assessment.level.value.upper() if assessment else "UNKNOWN"

    # 构建替代建议
    suggestions = []
    if intent:
        cap = intent.capability_name
        action = intent.action
        target = intent.target or intent.parameters.get("path", "")

        if cap == "file" and action == "delete":
            if target:
                suggestions.append(f"如果确认要删除，请使用明确的路径而非通配符: `{target}`")
            suggestions.append("如需安全删除，建议先用 `ls` 命令确认目标文件列表")
        elif cap == "user" and action == "delete":
            suggestions.append("如需临时禁用用户，请使用 `usermod -L <username>` 锁定账号")
            suggestions.append("删除用户是不可逆操作，建议先导出用户数据")
        elif "chmod" in raw_input or "chown" in raw_input:
            suggestions.append("如需修改权限，建议使用最小权限原则")
            suggestions.append("避免使用 `chmod 777`，改用 `chmod 755` 或更严格的权限")
        elif "systemctl" in raw_input or "iptables" in raw_input:
            suggestions.append("系统服务和防火墙操作可能影响远程连接，请谨慎操作")
            suggestions.append("建议先记录当前配置: `systemctl list-units --state=running`")

    suggestions_text = ""
    if suggestions:
        suggestions_text = "\n\n建议:\n" + "\n".join(f"  - {s}" for s in suggestions)

    state["response"] = AgentResponse(
        success=False,
        message=f"**操作已被拦截** (风险等级: {risk_level})\n\n原因:\n{reasons}{suggestions_text}",
        risk_level=assessment.level if assessment else RiskLevel.LOW,
    )
    return state


# ============ 路由函数 ============

def route_after_risk_check(state: AgentState) -> str:
    """风险检查后的路由 - 已确认时直接执行，不再走确认节点"""
    assessment = state.get("risk_assessment")

    if assessment and assessment.blocked:
        return RouteAction.REJECT
    elif assessment and assessment.needs_confirmation and not state.get("confirmed"):
        return RouteAction.CONFIRM
    else:
        return RouteAction.EXECUTE


def route_after_confirmation(state: AgentState) -> str:
    """确认后的路由 - 未确认时保留确认提示，不走拒绝流程"""
    if state.get("confirmed"):
        return RouteAction.EXECUTE
    # 未确认 - 直接结束，保留request_confirmation_node中设置的确认提示
    return "end"


# ============ 图构建 ============

def build_agent_graph() -> StateGraph:
    """构建代理状态图"""
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("probe_environment", probe_environment_node)
    graph.add_node("assess_risk", assess_risk_node)
    graph.add_node("request_confirmation", request_confirmation_node)
    graph.add_node("match_capability", match_capability_node)
    graph.add_node("execute", execute_node)
    graph.add_node("auto_retry", auto_retry_node)
    graph.add_node("verify_result", verify_result_node)
    graph.add_node("format_response", format_response_node)
    graph.add_node("reject", reject_node)

    # 定义边
    graph.set_entry_point("parse_intent")
    
    # 意图解析后的条件分支 - 闲聊/未知/澄清直接响应，其他继续处理
    def route_after_intent(state):
        intent = state.get("intent")
        log.info(f"路由判断: intent={intent}")
        if intent:
            log.info(f"路由判断: action={intent.action}, cap={intent.capability_name}")
            # 需要澄清 - 直接格式化响应（跳过执行）
            if intent.needs_clarification and intent.clarification_question:
                log.info(f"路由判断: 需要澄清，跳过执行")
                return "format_response"
            # 闲聊意图 - 直接格式化响应
            if intent.capability_name == "chat":
                return "format_response"
            # 未知意图 - 也直接格式化响应
            if intent.action == "unknown" or intent.capability_name == "" or intent.capability_name == "unknown":
                return "format_response"
        # 系统管理意图 - 继续环境探测和风险评估
        return "probe_environment"
    
    graph.add_conditional_edges(
        "parse_intent",
        route_after_intent,
        {
            "format_response": "format_response",
            "probe_environment": "probe_environment"
        }
    )
    
    graph.add_edge("probe_environment", "assess_risk")

    # 风险检查后的条件分支
    graph.add_conditional_edges(
        "assess_risk",
        route_after_risk_check,
        {
            RouteAction.CONFIRM: "request_confirmation",
            RouteAction.EXECUTE: "match_capability",
            RouteAction.REJECT: "reject",
        }
    )

    # 二次确认后的条件分支
    graph.add_conditional_edges(
        "request_confirmation",
        route_after_confirmation,
        {
            RouteAction.EXECUTE: "match_capability",
            "end": END,
        }
    )

    # 正常流程
    graph.add_edge("match_capability", "execute")
    # 执行后：失败走自动修复，成功或重试耗尽则继续验证
    graph.add_conditional_edges(
        "execute",
        route_after_execute,
        {
            "auto_retry": "auto_retry",
            "verify_result": "verify_result",
        }
    )
    # 自动修复后重新判断：又失败且还能重试则继续修复，否则去验证
    graph.add_conditional_edges(
        "auto_retry",
        route_after_execute,
        {
            "auto_retry": "auto_retry",
            "verify_result": "verify_result",
        }
    )
    graph.add_edge("verify_result", "format_response")
    graph.add_edge("format_response", END)
    graph.add_edge("reject", END)

    return graph


def compile_graph():
    """编译状态图"""
    graph = build_agent_graph()
    return graph.compile()
