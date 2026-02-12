"""执行流程数据结构模块。

本模块包含执行流程相关的数据结构定义，包括：
- PlanningPhase: 规划阶段枚举
- ExecutionStepStatus: 执行步骤状态枚举
- ExecutionStep: 执行步骤数据类
- ExecutionFlow: 执行流程管理类
- TaskPlan: 任务规划结果数据类
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum


class PlanningPhase(Enum):
    """规划阶段"""
    ANALYZING = "analyzing"           # 分析任务
    RESEARCHING = "researching"       # 调研背景
    REWRITING = "rewriting"           # 改写任务
    PLANNING = "planning"             # 制定计划
    READY = "ready"                   # 准备执行


class ExecutionStepStatus(Enum):
    """执行步骤状态"""
    PENDING = "pending"               # 等待执行
    BLOCKED = "blocked"               # 被依赖阻塞
    RUNNING = "running"               # 执行中
    COMPLETED = "completed"           # 已完成
    FAILED = "failed"                 # 失败
    SKIPPED = "skipped"               # 跳过


@dataclass
class ExecutionStep:
    """执行步骤。
    
    表示执行计划中的单个步骤，包含步骤信息、依赖关系和执行状态。
    
    Attributes:
        step_id: 步骤唯一标识符
        step_number: 步骤序号
        name: 步骤名称
        description: 详细描述
        agent_type: 执行智能体类型
        expected_output: 预期产出
        dependencies: 依赖的步骤ID列表
        status: 执行状态
        input_data: 输入数据（来自上游）
        output_data: 输出数据（传给下游）
        error: 错误信息
        started_at: 开始时间
        completed_at: 完成时间
    """
    step_id: str
    step_number: int
    name: str
    description: str
    agent_type: str
    expected_output: str
    dependencies: List[str]
    status: ExecutionStepStatus = ExecutionStepStatus.PENDING
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    review_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "name": self.name,
            "description": self.description,
            "agent_type": self.agent_type,
            "expected_output": self.expected_output,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "review_history": self.review_history,
        }


@dataclass
class ExecutionFlow:
    """执行流程 - 管理步骤间的依赖关系。
    
    负责管理执行步骤的添加、状态更新和依赖关系检查。
    
    Attributes:
        steps: 步骤字典，键为步骤ID
        execution_order: 拓扑排序后的执行顺序
    """
    steps: Dict[str, ExecutionStep] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)
    adjustment_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_step(self, step: ExecutionStep) -> None:
        """添加执行步骤。
        
        Args:
            step: 要添加的执行步骤
        """
        self.steps[step.step_id] = step
    
    def get_ready_steps(self) -> List[ExecutionStep]:
        """获取可以执行的步骤（依赖已满足）。
        
        Returns:
            可执行的步骤列表
        """
        ready = []
        for step in self.steps.values():
            if step.status != ExecutionStepStatus.PENDING:
                continue
            # 检查所有依赖是否已完成
            deps_satisfied = all(
                self.steps.get(dep_id, ExecutionStep("", 0, "", "", "", "", [])).status == ExecutionStepStatus.COMPLETED
                for dep_id in step.dependencies
            )
            if deps_satisfied:
                ready.append(step)
        return ready
    
    def get_step_input(self, step: ExecutionStep) -> Dict[str, Any]:
        """获取步骤的输入数据（来自上游依赖）。
        
        Args:
            step: 目标步骤
            
        Returns:
            输入数据字典
        """
        input_data = {}
        for dep_id in step.dependencies:
            dep_step = self.steps.get(dep_id)
            if dep_step and dep_step.output_data:
                input_data[dep_id] = dep_step.output_data
        return input_data
    
    def update_step_status(
        self,
        step_id: str,
        status: ExecutionStepStatus,
        output_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """更新步骤状态。
        
        Args:
            step_id: 步骤ID
            status: 新状态
            output_data: 输出数据（可选）
            error: 错误信息（可选）
        """
        if step_id in self.steps:
            step = self.steps[step_id]
            step.status = status
            if output_data:
                step.output_data = output_data
            if error:
                step.error = error
            if status == ExecutionStepStatus.RUNNING:
                step.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
            elif status in (ExecutionStepStatus.COMPLETED, ExecutionStepStatus.FAILED):
                step.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
    
    def is_completed(self) -> bool:
        """检查流程是否全部完成。
        
        Returns:
            是否全部完成
        """
        return all(
            step.status in (ExecutionStepStatus.COMPLETED, ExecutionStepStatus.SKIPPED, ExecutionStepStatus.FAILED)
            for step in self.steps.values()
        )
    
    def get_progress(self) -> Dict[str, Any]:
        """获取执行进度。

        Returns:
            进度信息字典，包含总数、完成数、运行数、失败数、进度百分比、
            已评审数和调整次数
        """
        total = len(self.steps)
        completed = sum(1 for s in self.steps.values() if s.status == ExecutionStepStatus.COMPLETED)
        running = sum(1 for s in self.steps.values() if s.status == ExecutionStepStatus.RUNNING)
        failed = sum(1 for s in self.steps.values() if s.status == ExecutionStepStatus.FAILED)
        reviewed = sum(1 for s in self.steps.values() if s.review_history)
        return {
            "total": total,
            "completed": completed,
            "running": running,
            "failed": failed,
            "progress_percent": int(completed / total * 100) if total > 0 else 0,
            "reviewed": reviewed,
            "adjusted": len(self.adjustment_history),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "execution_order": self.execution_order,
            "progress": self.get_progress(),
            "adjustment_history": self.adjustment_history,
        }


@dataclass
class TaskPlan:
    """任务规划结果。
    
    包含完整的任务规划信息，包括原始任务、分析结果、
    改写后的任务、执行计划等。
    
    Attributes:
        original_task: 原始任务
        task_analysis: 任务分析
        refined_task: 改写后的任务
        background_research: 背景调研
        execution_plan: 执行计划（步骤列表）
        execution_flow: 执行流程（带依赖关系）
        suggested_agents: 建议的智能体
        estimated_complexity: 预估复杂度
        key_objectives: 关键目标
        success_criteria: 成功标准
        potential_challenges: 潜在挑战
        react_trace: ReAct 追踪记录
    """
    original_task: str
    task_analysis: Dict[str, Any]
    refined_task: str
    background_research: str
    execution_plan: List[Dict[str, Any]]
    execution_flow: Optional[ExecutionFlow] = None
    suggested_agents: List[str] = field(default_factory=list)
    estimated_complexity: float = 5.0
    key_objectives: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    potential_challenges: List[str] = field(default_factory=list)
    react_trace: List[Dict[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "original_task": self.original_task,
            "task_analysis": self.task_analysis,
            "refined_task": self.refined_task,
            "background_research": self.background_research,
            "execution_plan": self.execution_plan,
            "execution_flow": self.execution_flow.to_dict() if self.execution_flow else None,
            "suggested_agents": self.suggested_agents,
            "estimated_complexity": self.estimated_complexity,
            "key_objectives": self.key_objectives,
            "success_criteria": self.success_criteria,
            "potential_challenges": self.potential_challenges,
            "react_trace": self.react_trace,
        }
