"""上下文管理模块 - 管理对话上下文"""
from typing import List, Tuple
from src.agent.models import ConversationTurn


class ContextManager:
    """上下文管理器"""

    def __init__(self, max_tokens: int = 2000):
        self.max_tokens = max_tokens

    def format_context(self, turns: List[ConversationTurn]) -> str:
        """格式化对话上下文"""
        if not turns:
            return ""

        context_parts = []
        for turn in reversed(turns):
            context_parts.append(f"用户: {turn.user_input}")
            context_parts.append(f"助手: {turn.agent_response}")

        return "\n".join(context_parts)

    def compress_context(self, context: str) -> str:
        """压缩过长的上下文"""
        if self._estimate_tokens(context) <= self.max_tokens:
            return context

        lines = context.split("\n")
        if len(lines) <= 4:
            return context

        # 保留首尾，中间压缩
        first_two = lines[:2]
        last_two = lines[-2:]
        compressed = first_two + ["... (中间对话已省略) ..."] + last_two

        return "\n".join(compressed)

    def _estimate_tokens(self, text: str) -> int:
        """估算token数量"""
        # 简单估算：中文约1.5 token/字，英文约0.25 token/字符
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + english_chars * 0.25)

    def enrich_clarification_reply(self, user_input: str, context: str) -> Tuple[str, bool]:
        """检测并增强澄清回复

        当上一条助手消息是澄清问题（包含"哪个"、"请说明"、"请具体"等），
        且当前用户输入是一个简短的实体（用户名、路径等），自动拼接上下文中的
        原始操作意图，让 LLM 能正确理解。

        场景：
        - 助手: "你是想修改哪个用户的密码？"  用户: "test333"
          → 增强为: "修改用户test333的密码"（结合前一条用户消息的意图）

        Args:
            user_input: 当前用户输入
            context: 对话上下文

        Returns:
            (增强后的输入, 是否被增强)
        """
        import re

        if not context:
            return user_input, False

        # 检查上下文中最后一条助手消息是否是澄清问题
        lines = context.strip().split("\n")
        last_assistant_msg = ""
        last_user_msg = ""
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("助手:") and not last_assistant_msg:
                last_assistant_msg = line[3:].strip()
            elif line.startswith("用户:") and not last_user_msg:
                last_user_msg = line[3:].strip()
            if last_assistant_msg and last_user_msg:
                break

        # 判断是否是澄清问题
        clarification_keywords = ['哪个', '请说明', '请具体', '是指', '请问', '哪里', '哪个用户', '哪个文件']
        is_clarification = any(kw in last_assistant_msg for kw in clarification_keywords)
        if not is_clarification:
            return user_input, False

        # 判断当前输入是否是简短实体回复（用户名、路径、单个词等）
        stripped = user_input.strip()
        # 短输入（< 20字符）且不含动词 → 可能是澄清回复
        if len(stripped) > 20:
            return user_input, False

        # 如果输入已经是完整的命令（包含动词），不需要增强
        action_verbs = ['创建', '删除', '修改', '查看', '列出', '搜索', '检查', '查看',
                        '新建', '添加', '移除', '改成', '改为', '设为', '查询']
        if any(v in stripped for v in action_verbs):
            return user_input, False

        # 从上一条用户消息中提取操作意图和参数
        if not last_user_msg:
            return user_input, False

        # 检测澄清问题中的关键词来推断要补充什么
        enhanced = stripped
        if '密码' in last_assistant_msg or '密码' in last_user_msg:
            # 密码相关澄清 → 输入的是用户名
            enhanced = f"用户{stripped}的密码" + self._extract_trailing_params(last_user_msg)
        elif '用户' in last_assistant_msg or '用户' in last_user_msg:
            enhanced = f"用户{stripped}"
        elif '文件' in last_assistant_msg or '文件' in last_user_msg:
            enhanced = f"文件{stripped}"
        elif '路径' in last_assistant_msg or '目录' in last_assistant_msg:
            enhanced = f"{stripped}"
        else:
            # 通用：直接附加到上一条用户消息中
            enhanced = f"{last_user_msg}（{stripped}）"

        return enhanced, True

    @staticmethod
    def _extract_trailing_params(text: str) -> str:
        """从文本中提取尾部参数（如密码值）"""
        import re
        # 匹配 "改成xxx"、"改为xxx"、"密码xxx" 等模式
        patterns = [
            r'(?:改成|改为|设为|设成)\s*["\']?([^\s"\'，,。]+)',
            r'密码\s*[是为]?\s*["\']?([^\s"\'，,。]+)',
            r'新密码\s*[是为]?\s*["\']?([^\s"\'，,。]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return f"，改成{match.group(1)}"
        return ""

    def resolve_references(self, user_input: str, context: str) -> str:
        """解析用户输入中的代词引用，替换为具体引用

        检测模式:
        - "那个"、"它"、"上面的"、"这个" → 从上下文推断具体目标
        - "也帮我看看"、"顺便查一下" → 保留前一个操作的目标

        Args:
            user_input: 用户当前输入
            context: 对话上下文

        Returns:
            增强后的用户输入（如无法解析则原样返回）
        """
        import re

        # 检查是否包含需要消歧的代词/引用词
        reference_patterns = [
            r'那个',
            r'它',
            r'上面的',
            r'这个',
            r'之前的',
            r'刚才的',
        ]

        has_reference = any(re.search(p, user_input) for p in reference_patterns)
        if not has_reference:
            return user_input

        # 从上下文中提取最近的操作和目标
        if not context:
            return user_input

        # 提取上下文中的路径/用户名等实体
        entities = self._extract_entities_from_context(context)
        if not entities:
            return user_input

        # 尝试替换代词
        enhanced = user_input
        for entity in entities:
            # 如果当前输入没有具体路径/目标，且上下文中有，则插入
            if not re.search(r'[/\\~][^\s,，。]*', enhanced) and not re.search(r'用户\s+\w+', enhanced):
                # 简单替换：在代词后面插入实体
                for pattern in reference_patterns:
                    if re.search(pattern, enhanced):
                        enhanced = re.sub(
                            pattern,
                            f'{pattern}（{entity}）',
                            enhanced,
                            count=1
                        )
                        break
                break

        return enhanced

    def _extract_entities_from_context(self, context: str) -> List[str]:
        """从对话上下文中提取实体（路径、用户名等）"""
        import re
        entities = []

        # 提取路径
        paths = re.findall(r'[/\\~][^\s,，。"\']+', context)
        if paths:
            entities.extend(paths[-2:])  # 取最近2个路径

        # 提取用户名（多种模式，只匹配合法Linux用户名：字母/数字/下划线/短横线）
        _uname_re = r'[a-zA-Z_][a-zA-Z0-9_-]*'
        usernames = []
        # 模式1: "用户 xxx"（有空格）
        usernames.extend(re.findall(rf'用户\s+({_uname_re})', context))
        # 模式2: "新用户xxx"（无空格，如 "创建一个新用户test333"）
        usernames.extend(re.findall(rf'新用户({_uname_re})', context))
        # 模式3: "用户xxx"（无空格，如 "用户test333的权限"）
        usernames.extend(re.findall(rf'用户({_uname_re})', context))
        if usernames:
            # 去重，保留顺序（最新的在后）
            seen = set()
            unique = []
            for u in usernames:
                if u not in seen:
                    seen.add(u)
                    unique.append(u)
            entities.extend(unique[-3:])  # 取最近3个用户名

        return entities
