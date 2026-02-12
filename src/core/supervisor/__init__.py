"""AI 主管子包（Supervisor）。

本子包包含 Supervisor 的拆分模块，负责使用 ReAct 架构进行
动态任务规划和执行流程管理。

作为 AI 团队的主管，主要职责：
1. 分析用户任务，理解真实意图
2. 调研任务背景，补充必要信息
3. 改写和细化任务描述，使其更清晰可执行
4. 制定动态执行计划，规划有依赖关系的子任务链路
5. 监督执行过程，根据中间结果动态调整后续步骤
6. 协调智能体团队，管理上下游依赖关系

子模块：
    - supervisor: Supervisor 核心类与配置
    - planning: TaskPlanningEngine 任务规划逻辑
    - flow: ExecutionStep、ExecutionFlow、TaskPlan 数据结构
    - evaluation: StepEvaluator 步骤评估与资源估算
"""

from .flow import (
    PlanningPhase,
    ExecutionStepStatus,
    ExecutionStep,
    ExecutionFlow,
    TaskPlan,
)
from .quality_gate import StageReviewResult, QualityGateReviewer

# 从原始 supervisor.py 导入完整实现
from ...supervisor import Supervisor, SupervisorConfig

__all__ = [
    # 数据结构
    "PlanningPhase",
    "ExecutionStepStatus",
    "ExecutionStep",
    "ExecutionFlow",
    "TaskPlan",
    # 质量门控
    "StageReviewResult",
    "QualityGateReviewer",
    # 核心类
    "Supervisor",
    "SupervisorConfig",
]
