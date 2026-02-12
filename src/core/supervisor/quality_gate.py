"""质量门控评审模块。

本模块实现阶段级质量门控机制，包括：
- StageReviewResult: 阶段评审结果数据类
- QualityGateReviewer: 质量门控评审器
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable

from .flow import ExecutionFlow, ExecutionStep, ExecutionStepStatus

logger = logging.getLogger(__name__)


@dataclass
class StageReviewResult:
    """阶段评审结果。

    Attributes:
        step_id: 步骤ID
        quality_score: 质量评分 (1-10)
        action: 决策动作 ("continue" | "retry" | "add_step" | "skip_next")
        reason: 评审理由
        adjustments: 调整建议列表
        attempt: 评审次数（第几次）
        timestamp: 评审时间
    """
    step_id: str
    quality_score: float
    action: str
    reason: str
    adjustments: List[Dict[str, Any]] = field(default_factory=list)
    attempt: int = 1
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "quality_score": self.quality_score,
            "action": self.action,
            "reason": self.reason,
            "adjustments": self.adjustments,
            "attempt": self.attempt,
            "timestamp": self.timestamp,
        }


class QualityGateReviewer:
    """质量门控评审器。

    封装评审逻辑，作为 agent_factory 和 Supervisor 之间的协调层。
    调用 Supervisor.evaluate_step_result() 获取评审结果，
    根据结果决定放行、重试或调整后续流程。
    """

    def __init__(
        self,
        supervisor,
        config,
        execution_flow: ExecutionFlow,
        task_board=None,
        stream_callback: Optional[Callable] = None,
    ):
        self._supervisor = supervisor
        self._config = config
        self._execution_flow = execution_flow
        self._task_board = task_board
        self._stream_callback = stream_callback

    async def review_step(
        self,
        step: Dict[str, Any],
        output: str,
        step_results: Dict[str, Any],
        attempt: int = 1,
    ) -> StageReviewResult:
        """评审单个步骤的交付物。

        调用 Supervisor.evaluate_step_result() 获取评审结果，
        解析返回结构，构造 StageReviewResult。

        Args:
            step: 步骤字典（planner.py 中步骤以 dict 存储）
            output: 步骤输出内容
            step_results: 所有已完成步骤的结果
            attempt: 当前评审次数

        Returns:
            StageReviewResult 评审结果
        """
        step_id = step.get("step_id", "unknown")

        try:
            # 构造一个临时 ExecutionStep 供 evaluate_step_result 使用
            temp_step = ExecutionStep(
                step_id=step_id,
                step_number=step.get("step_number", 0),
                name=step.get("name", ""),
                description=step.get("description", ""),
                agent_type=step.get("agent_type", "researcher"),
                expected_output=step.get("expected_output", ""),
                dependencies=step.get("dependencies", []),
                status=ExecutionStepStatus.COMPLETED,
            )

            result_dict = {"output": output[:2000] if output else ""}

            eval_result = await self._supervisor.evaluate_step_result(
                step=temp_step,
                result=result_dict,
                execution_flow=self._execution_flow,
                stream_callback=self._stream_callback,
            )

            quality_score = float(eval_result.get("quality_score", 7.0))
            action = eval_result.get("action", "continue")
            reason = eval_result.get("reason", "")
            adjustments = eval_result.get("adjustments", [])

            # 根据阈值决定最终 action
            threshold = self._config.quality_threshold
            if quality_score >= threshold and action not in ("add_step", "skip_next"):
                action = "continue"

            return StageReviewResult(
                step_id=step_id,
                quality_score=quality_score,
                action=action,
                reason=reason,
                adjustments=adjustments,
                attempt=attempt,
            )

        except Exception as e:
            logger.error(f"质量门控评审异常 (step={step_id}): {e}")
            # 异常时优雅降级：放行步骤
            return StageReviewResult(
                step_id=step_id,
                quality_score=7.0,
                action="continue",
                reason=f"评审异常，自动放行: {str(e)}",
                adjustments=[],
                attempt=attempt,
            )

    async def apply_adjustments(
        self,
        adjustments: List[Dict[str, Any]],
        trigger_step_id: str = "",
        broadcast_callback: Optional[Callable] = None,
    ) -> None:
        """应用动态调整。

        调用 Supervisor.adjust_execution_flow()，
        将新步骤发布到 TaskBoard，记录 adjustment_history，
        广播 flow_adjusted 事件。

        Args:
            adjustments: 调整列表
            trigger_step_id: 触发调整的步骤ID
            broadcast_callback: WebSocket 广播回调
        """
        try:
            updated_flow = await self._supervisor.adjust_execution_flow(
                execution_flow=self._execution_flow,
                adjustments=adjustments,
                stream_callback=self._stream_callback,
            )

            # 记录调整历史
            self._execution_flow.adjustment_history.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "trigger_step_id": trigger_step_id,
                "adjustments": adjustments,
                "result": "applied",
            })

            # 将新增步骤发布到 TaskBoard
            if self._task_board:
                from src.models.task import SubTask
                for adj in adjustments:
                    if adj.get("type") == "add_step":
                        new_step_id = adj.get("step_id", "")
                        if new_step_id and new_step_id in self._execution_flow.steps:
                            new_step = self._execution_flow.steps[new_step_id]
                            subtask = SubTask(
                                id=new_step_id,
                                parent_task_id="",
                                content=new_step.description or new_step.name,
                                role_hint=new_step.agent_type,
                                dependencies=set(new_step.dependencies),
                                priority=new_step.step_number,
                                estimated_complexity=1.0,
                            )
                            deps_map = {new_step_id: set(new_step.dependencies)}
                            await self._task_board.publish_tasks([subtask], deps_map)

            # 广播 flow_adjusted 事件
            if broadcast_callback:
                await broadcast_callback("flow_adjusted", {
                    "trigger_step_id": trigger_step_id,
                    "adjustments": adjustments,
                    "updated_flow": self._execution_flow.to_dict(),
                })

        except Exception as e:
            logger.error(f"应用动态调整失败: {e}")
            self._execution_flow.adjustment_history.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "trigger_step_id": trigger_step_id,
                "adjustments": adjustments,
                "result": "failed",
            })
