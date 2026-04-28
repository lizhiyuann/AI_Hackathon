"""意图解析模块 - LLM为核心，regex提取参数，无关键词匹配"""
import re
import os
from typing import Dict, Optional
from src.agent.models import Intent
from src.utils.logger import log


class IntentParser:
    """意图解析器 - 完全依赖 LLM 理解语义"""

    def __init__(self, llm=None):
        self.llm = llm

    def parse(self, user_input: str, context: str = "", env_hint: str = "") -> Intent:
        """解析用户输入，返回意图

        流程：
        1. 用 regex 提取结构化参数（用户名、密码、路径等）
        2. 用 LLM 判断意图类别（capability + action）
        3. LLM 失败时用极简启发式兜底（仅在无 LLM 时生效）

        Args:
            env_hint: 目标系统环境提示（如 "Linux/Ubuntu 24.04"），帮助 LLM 选择正确的路径
        """
        log.debug(f"解析用户输入: {user_input}, env={env_hint}")

        # 提取结构化参数（与意图无关，纯 regex）
        parameters = self._extract_parameters(user_input)

        # 主路径：LLM 理解意图
        intent = self._parse_with_llm(user_input, context, parameters, env_hint=env_hint)
        if intent:
            return intent

        # 兜底：LLM 不可用时的极简判断
        log.warning("LLM 不可用，使用兜底逻辑")
        return self._fallback_parse(user_input, parameters)

    def _parse_with_llm(self, user_input: str, context: str, parameters: Dict, env_hint: str = "") -> Optional[Intent]:
        """使用 LLM 解析意图"""
        if not self.llm:
            return None

        # 构建能力描述
        from src.capabilities.registry import CapabilityRegistry
        registry = CapabilityRegistry()
        caps_desc = []
        for cap in registry.list_all():
            caps_desc.append(f"- {cap['name']}: {cap['description']}, 支持操作: {', '.join(cap['actions'])}")

        # 增强上下文处理
        from src.understanding.context import ContextManager
        ctx_mgr = ContextManager()

        # 先检查是否是澄清回复（上一轮助手问了澄清问题，用户给了简短回答）
        effective_input, was_clarified = ctx_mgr.enrich_clarification_reply(user_input, context)
        if was_clarified:
            log.info(f"澄清回复增强: '{user_input}' → '{effective_input}'")

        # 再处理代词消解（基于增强后的输入和上下文）
        enhanced_input = ctx_mgr.resolve_references(effective_input, context)
        context_text = f"\n\n对话上下文:\n{context}" if context else ""
        home = os.path.expanduser("~")

        # 如果输入被增强了（澄清增强 或 代词消解），使用增强后的输入
        display_input = enhanced_input if enhanced_input != user_input else user_input

        # 澄清回复场景：额外提供上下文信息给 LLM
        clarification_hint = ""
        if was_clarified:
            clarification_hint = "\n\n## 注意：用户正在回答上一轮的澄清问题，请根据增强后的输入理解其完整意图。"

        # 查询学习记忆，注入历史经验
        learning_text = ""
        try:
            from src.agent.learning import LearningMemory
            learning = LearningMemory()
            lessons = learning.recall(user_input, limit=3)
            if lessons:
                learning_text = "\n\n## 历史经验（过去犯过的错误，请避免重复）：\n"
                for l in lessons:
                    learning_text += f"- {l.get('lesson', '')}\n"
        except Exception:
            pass

        # 环境信息提示
        env_text = f"\n\n## 当前系统环境：{env_hint}" if env_hint else ""

        prompt = f"""你是操作系统命令意图解析器。根据用户输入，判断用户想做什么。

## 可用能力（只能选这些）：
{chr(10).join(caps_desc)}

## 用户输入：
{display_input}{context_text}{learning_text}{env_text}{clarification_hint}

## 解析规则：
1. 如果用户在闲聊（打招呼、问你是谁、问功能、问问题、说谢谢、说再见等），返回 capability="chat", action="greeting"
2. 如果用户想查看/检查系统状态（磁盘、内存、进程、网络、用户列表、系统信息等），对应相应的能力
3. 如果用户想执行管理操作（创建/删除用户、修改用户密码、创建/删除文件等），对应相应的能力
4. 如果用户问关于 sudo、权限、管理员的问题，返回 capability="user", action="info"
5. 如果用户的问题不属于任何管理能力，返回 capability="chat", action="greeting"
6. 从输入中提取参数：path、username、password、new_password、name、port、keyword、service、source、dest
7. "桌面上" → path 前缀用 {home}/Desktop
8. **代词/指代消解（极其重要）**：如果用户使用了"这个"、"那个"、"它"、"刚才的"、"之前的"等代词，必须根据对话上下文推断具体指代：
   - "修改一下这个密码" → 如果上一步刚创建了用户 test333，那 username 应该是 test333，不是当前系统用户
   - "删掉那个文件" → 如果上一步刚查看了某文件，应该是指那个文件
   - **优先级**：最近一次操作涉及的对象 > 对话中提到的实体 > 当前系统用户名
   - **绝不应该**将代词默认指向当前操作系统的登录用户（如 lizhiyuan），除非上下文明确表示
9. 如果用户说"也帮我看看"或"顺便查一下"，结合上下文理解其指代的目标
10. **文件路径必须根据系统环境选择正确路径**，不要瞎猜：
    - Ubuntu 22.04+ 使用 netplan，网络配置在 /etc/netplan/，而非 /etc/network/interfaces
    - CentOS/RHEL 使用 /etc/sysconfig/network-scripts/
    - systemd-resolved 的 DNS 配置在 /etc/systemd/resolved.conf
    - 如果不确定具体文件位置，可以用 file.search 在相关目录搜索

11. **歧义澄清**：如果用户输入包含代词（"这个"、"那个"、"它"）且对话上下文无法确定具体指代，同时操作是破坏性的（修改密码、删除用户/文件、修改配置等），则返回 needs_clarification=true 和 clarification_question（自然语言的澄清问题）。
    - 只读操作（查看、列出、搜索、检查）不需要澄清，可以合理猜测
    - 如果上下文能合理推断（如刚创建了用户A后说"修改这个密码"→用户A），则不需要澄清
    - 澄清问题要简洁自然，如"你是想修改 test333 的密码吗？"
12. **澄清回复**：如果上一轮助手提出了澄清问题，当前用户输入是对该问题的回答（如用户名、路径等简短实体），请根据上下文中的原始操作意图 + 用户回答的实体，组合成完整意图。例如：
    - 上一轮: 助手问"你是想修改哪个用户的密码？" → 用户回答"test333" → 理解为"修改用户test333的密码"
    - 上一轮: 助手问"要删除哪个文件？" → 用户回答"/tmp/test.log" → 理解为"删除 /tmp/test.log"

## 重要：
- 不要把闲聊/问题误判为管理操作
- "有没有sudo权限" 是一个问题，不是创建用户
- "帮我查一下" 是闲聊/问题，不是具体操作
- 只有明确要求执行操作的才走管理能力
- 善于利用对话上下文理解代词和隐含引用
- 不确定时宁可澄清，也不要猜错执行破坏性操作

## 返回格式（只返回JSON）：
{{"capability":"xxx","action":"xxx","parameters":{{...}},"confidence":0.9,"needs_clarification":false,"clarification_question":""}}"""

        try:
            from langchain_core.messages import HumanMessage
            log.info(f"LLM 意图解析: {user_input[:50]}")
            response = self.llm.invoke([HumanMessage(content=prompt)])
            response_text = response.content
            log.info(f"LLM 响应: {response_text[:300]}")

            import json
            # 用括号匹配提取第一个完整 JSON 对象，避免 rfind 匹配到后面多余的 }
            json_str = self._extract_json(response_text)
            if json_str:
                result = json.loads(json_str)

                cap = result.get("capability", "unknown")
                act = result.get("action", "unknown")
                confidence = result.get("confidence", 0.8)

                # 合并参数：regex 提取的 + LLM 提取的
                # 用 v is not None 替代 if v，避免丢弃 port=0 等合法 falsy 值
                llm_params = {k: v for k, v in result.get("parameters", {}).items() if v is not None and v != ""}
                merged = {**parameters, **llm_params}

                log.info(f"意图解析结果: capability={cap}, action={act}, confidence={confidence}")
                intent = Intent(
                    action=act,
                    target=merged.get("path", ""),
                    parameters=merged,
                    raw_input=user_input,
                    confidence=confidence,
                    capability_name=cap,
                )
                # 澄清标记（LLM 返回 + 后置安全检查）
                needs_clarification = result.get("needs_clarification", False)
                clarification_question = result.get("clarification_question", "")
                if needs_clarification and clarification_question:
                    intent.needs_clarification = True
                    intent.clarification_question = clarification_question
                    log.info(f"LLM 判定需要澄清: {clarification_question}")
                else:
                    # 后置安全检查：LLM 未标记澄清时，检查是否有危险的代词未消解
                    self._post_check_clarification(intent, user_input, context)
                return intent
        except Exception as e:
            log.error(f"LLM 意图解析失败: {e}")

        return None

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """从 LLM 响应中提取第一个完整 JSON 对象（括号匹配，非贪婪）"""
        start = text.find('{')
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

    @staticmethod
    def _post_check_clarification(intent: 'Intent', user_input: str, context: str):
        """后置安全检查：LLM 没标记澄清时，检查是否有危险代词未消解

        只针对破坏性操作（modify/delete/change_password 等），且输入含有代词、
        上下文无法确定指代时，追加澄清标记。只读操作不检查。
        """
        import re

        # 破坏性动作列表
        destructive_actions = {"modify", "delete", "remove", "change_password", "set_password"}
        # 只读动作不检查
        readonly_actions = {"list", "check_usage", "info", "memory", "search", "view", "greeting", "unknown"}

        if intent.action in readonly_actions or intent.capability_name == "chat":
            return
        if intent.action not in destructive_actions:
            # 对于 create 等非破坏性操作，通常参数已明确，不检查
            return

        # 检查是否有未消解的代词
        pronouns = ['这个', '那个', '它', '上面的', '之前的', '刚才的']
        has_pronoun = any(p in user_input for p in pronouns)
        if not has_pronoun:
            return

        # 检查上下文是否包含足够信息来推断
        if not context:
            # 无上下文，代词无法消解 → 需要澄清
            cap_name = intent.capability_name
            action = intent.action
            target = intent.parameters.get("username") or intent.parameters.get("path") or "它"
            intent.needs_clarification = True
            intent.clarification_question = f"你说的「{user_input}」是指哪个{cap_name}呢？请具体说明。"
            log.info(f"后置安全检查: 无上下文，代词未消解，标记需要澄清")
            return

        # 有上下文但 LLM 没标记澄清 → 信任 LLM 的判断（它看到了上下文）
        return

    def _fallback_parse(self, user_input: str, parameters: Dict) -> Intent:
        """极简兜底 - 仅在 LLM 完全不可用时使用

        策略：默认当作闲聊，让 LLM 在 format_response 阶段生成回复。
        只有非常明确的操作指令才尝试匹配。
        """
        text = user_input.strip().lower()

        # 非常明确的操作指令前缀
        if text.startswith(("查看磁盘", "看磁盘", "disk")):
            return Intent(action="check_usage", target="", parameters=parameters,
                          raw_input=user_input, confidence=0.7, capability_name="disk")
        if text.startswith(("查看进程", "看进程", "进程列表", "ps")):
            return Intent(action="list", target="", parameters=parameters,
                          raw_input=user_input, confidence=0.7, capability_name="process")
        if text.startswith(("查看内存", "看内存", "内存使用")):
            return Intent(action="memory", target="", parameters=parameters,
                          raw_input=user_input, confidence=0.7, capability_name="system")
        if text.startswith(("查看用户", "用户列表", "看用户")):
            return Intent(action="list", target="", parameters=parameters,
                          raw_input=user_input, confidence=0.7, capability_name="user")

        # 其他一律当闲聊处理
        return Intent(
            action="greeting",
            target="",
            parameters=parameters,
            raw_input=user_input,
            confidence=0.5,
            capability_name="chat",
        )

    def _extract_parameters(self, text: str) -> Dict:
        """从输入中提取结构化参数（纯 regex，不影响意图判断）"""
        params = {}

        # 提取路径
        path_patterns = [
            r'[/\\~][^\s,，。]*',
            r'(?:路径|目录路径)\s*[为是到]?\s*["\']?([^\s"\']+?)["\']?\s*$',
        ]
        for pattern in path_patterns:
            match = re.search(pattern, text)
            if match:
                params["path"] = match.group(1) if match.lastindex else match.group()
                params["target"] = params["path"]
                break

        # 提取文件夹名
        if not params.get("path"):
            dir_patterns = [
                r'(?:创建|新建|建个?|建一个?)\s*(?:一个?)?\s*["\']?(\S+?)["\']?\s*(?:的|这个)?\s*(?:文件夹|目录)',
                r'(?:文件夹|目录)\s*[叫名为]?\s*["\']?([^\s"\']+?)["\']?\s*$',
                r'(?:创建|新建|建个?)\s*(?:一个?)?\s*(?:文件夹|目录)\s*["\']?([^\s"\']+?)["\']?\s*$',
            ]
            for pattern in dir_patterns:
                match = re.search(pattern, text)
                if match:
                    name = match.group(1)
                    if name:
                        location = ""
                        if any(w in text for w in ["桌面", "desktop"]):
                            location = os.path.join(os.path.expanduser("~"), "Desktop")
                        elif any(w in text for w in ["文档", "documents"]):
                            location = os.path.join(os.path.expanduser("~"), "Documents")
                        params["path"] = os.path.join(location, name) if location else name
                        params["target"] = params["path"]
                    break

        # 提取端口号
        port_patterns = [r'端口\s*(\d+)', r'(\d+)\s*端口', r'(?:port)\s*(\d+)']
        for pattern in port_patterns:
            match = re.search(pattern, text)
            if match:
                params["port"] = match.group(1)
                break

        # 提取用户名（只匹配合法 Linux 用户名）
        _user_re = r'[a-zA-Z_][a-zA-Z0-9_-]{0,31}'
        user_patterns = [
            rf'(?:创建|新建|添加|新增|删除|移除|查看|查询|修改)\s*(?:一个?)?\s*({_user_re})\s*用户',
            rf'(?:创建|新建|添加|新增|删除|移除)\s*(?:一个?)?\s*用户\s*({_user_re})',
            rf'用户\s*({_user_re})',
            rf'({_user_re})\s*用户',
            rf'(?:user)\s+({_user_re})',
        ]
        for pattern in user_patterns:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1)
                if candidate:
                    params["username"] = candidate
                break

        # 提取密码
        password_patterns = [
            r'密码\s*[是为]?\s*["\']?([^\s"\'，,。]+?)["\']?\s*$',
            r'密码\s*[是为]?\s*["\']?([^\s"\'，,。]+?)["\']?\s*(?:，|,|。|\s|$)',
            r'password\s*[=是]?\s*["\']?([^\s"\']+?)["\']?',
        ]
        for pattern in password_patterns:
            match = re.search(pattern, text)
            if match:
                params["password"] = match.group(1)
                break

        # 提取新密码（修改密码场景：改成xxx、新密码xxx）
        new_pw_patterns = [
            r'(?:改成|改为|设为|设成|改到)\s*["\']?([^\s"\'，,。]+?)["\']?\s*$',
            r'(?:改成|改为|设为|设成|改到)\s*["\']?([^\s"\'，,。]+?)["\']?\s*(?:，|,|。|\s|$)',
            r'新密码\s*[是为]?\s*["\']?([^\s"\'，,。]+?)["\']?',
        ]
        for pattern in new_pw_patterns:
            match = re.search(pattern, text)
            if match:
                params["new_password"] = match.group(1)
                break

        # 提取服务名
        service_patterns = [
            r'服务\s*[为是叫]?\s*(\w+)',
            r'(?:service)\s*(\w+)',
            r'(\w+)\s*(?:服务|service)',
        ]
        for pattern in service_patterns:
            match = re.search(pattern, text)
            if match:
                params["service"] = match.group(1)
                break

        # 提取文件名/模式
        name_patterns = [
            r'(?:名为|叫做|叫|找)\s*["\']?(\S+?)["\']?\s*(?:的|文件)',
            r'(?:file|文件)\s*["\']?(\S+?)["\']?',
            r'(?:搜索|查找)\s*(?:名叫)?\s*["\']?(\S+?)["\']?\s*(?:的|文件)',
            r'["\']?(\S+?)["\']?\s*文件',
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                params["name"] = match.group(1)
                params["pattern"] = match.group(1)
                break

        # 提取进程名/关键字
        keyword_patterns = [
            r'(?:进程|process)\s*[为是叫]?\s*(\w+)',
            r'(?:查找|搜索|找)\s*(\w+)\s*(?:进程|process)',
            r'(\w+)\s*(?:进程|process)',
        ]
        for pattern in keyword_patterns:
            match = re.search(pattern, text)
            if match:
                params["keyword"] = match.group(1)
                break

        # 存储原始输入
        params["raw_input"] = text

        return params
