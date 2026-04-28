"""任务规划器 - 负责复杂任务分解与编排"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from src.utils.logger import log


@dataclass
class TaskStep:
    """任务步骤"""
    step_id: int
    description: str
    command: str
    capability_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: Optional[int] = None
    status: str = "pending"  # pending/running/completed/failed


@dataclass
class TaskPlan:
    """任务计划"""
    original_input: str
    steps: List[TaskStep] = field(default_factory=list)
    current_step: int = 0
    is_complex: bool = False

    def get_next_step(self) -> Optional[TaskStep]:
        """获取下一个待执行的步骤"""
        for step in self.steps:
            if step.status == "pending":
                return step
        return None

    def mark_step_completed(self, step_id: int):
        """标记步骤完成"""
        for step in self.steps:
            if step.step_id == step_id:
                step.status = "completed"
                break

    def mark_step_failed(self, step_id: int):
        """标记步骤失败"""
        for step in self.steps:
            if step.step_id == step_id:
                step.status = "failed"
                break

    def is_complete(self) -> bool:
        """检查任务是否完成"""
        return all(step.status == "completed" for step in self.steps)


class TaskPlanner:
    """任务规划器"""

    def __init__(self):
        # 复合任务的关键词
        self.complex_keywords = [
            "然后", "接着", "再", "之后", "并且", "同时",
            "and", "then", "also", "after", "finally"
        ]

    def is_complex_task(self, user_input: str) -> bool:
        """判断是否为复杂任务"""
        # 检查是否包含连接词
        for keyword in self.complex_keywords:
            if keyword in user_input:
                return True
        return False

    def plan(self, user_input: str, intents: List[Dict[str, Any]]) -> TaskPlan:
        """根据意图列表生成任务计划"""
        plan = TaskPlan(
            original_input=user_input,
            is_complex=len(intents) > 1
        )

        for i, intent in enumerate(intents):
            step = TaskStep(
                step_id=i + 1,
                description=intent.get("description", f"步骤 {i+1}"),
                command=intent.get("command", ""),
                capability_name=intent.get("capability", ""),
                parameters=intent.get("parameters", {}),
                depends_on=i if i > 0 else None,
            )
            plan.steps.append(step)

        log.info(f"任务规划完成: 共 {len(plan.steps)} 个步骤")
        return plan
