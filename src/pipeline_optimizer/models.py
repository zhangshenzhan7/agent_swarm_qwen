"""Agent Pipeline 优化系统数据模型。

定义流水线优化系统中使用的所有数据类和枚举类型，
包括阶段报告、评估结果、优化方案、配置快照和优化历史等。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class StageType(Enum):
    """流水线阶段类型"""
    DECOMPOSITION = "decomposition"
    SUB_AGENT = "sub_agent"
    QUALITY_ASSURANCE = "quality_assurance"
    AGGREGATION = "aggregation"
    REPORT_GENERATION = "report_generation"


@dataclass
class DimensionScore:
    """维度评分"""
    name: str
    score: float  # 1.0 - 10.0
    feedback: str  # 评分理由

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "feedback": self.feedback,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DimensionScore":
        return cls(
            name=data["name"],
            score=data["score"],
            feedback=data["feedback"],
        )


@dataclass
class StageReport:
    """单阶段分析报告"""
    stage: StageType
    dimensions: List[DimensionScore]
    overall_score: float
    issues: List[str]
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "overall_score": self.overall_score,
            "issues": self.issues,
            "suggestions": self.suggestions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StageReport":
        return cls(
            stage=StageType(data["stage"]),
            dimensions=[DimensionScore.from_dict(d) for d in data["dimensions"]],
            overall_score=data["overall_score"],
            issues=data["issues"],
            suggestions=data["suggestions"],
        )


@dataclass
class PipelineAnalysisReport:
    """流水线完整分析报告"""
    stage_reports: Dict[StageType, StageReport]
    overall_score: float
    weakest_stages: List[StageType]
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_reports": {
                k.value: v.to_dict() for k, v in self.stage_reports.items()
            },
            "overall_score": self.overall_score,
            "weakest_stages": [s.value for s in self.weakest_stages],
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineAnalysisReport":
        return cls(
            stage_reports={
                StageType(k): StageReport.from_dict(v)
                for k, v in data["stage_reports"].items()
            },
            overall_score=data["overall_score"],
            weakest_stages=[StageType(s) for s in data["weakest_stages"]],
            timestamp=data["timestamp"],
        )


@dataclass
class EvaluationResult:
    """三维评估结果"""
    professionalism: float  # 专业度 1-10
    richness: float         # 丰富度 1-10
    structure: float        # 结构化 1-10
    overall_score: float    # 加权综合分
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "professionalism": self.professionalism,
            "richness": self.richness,
            "structure": self.structure,
            "overall_score": self.overall_score,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "suggestions": self.suggestions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationResult":
        return cls(
            professionalism=data["professionalism"],
            richness=data["richness"],
            structure=data["structure"],
            overall_score=data["overall_score"],
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            suggestions=data["suggestions"],
        )


@dataclass
class WeakPoint:
    """待优化薄弱点"""
    stage: StageType
    dimension: str
    score: float
    role_key: Optional[str] = None  # 关联的角色（如适用）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "dimension": self.dimension,
            "score": self.score,
            "role_key": self.role_key,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeakPoint":
        return cls(
            stage=StageType(data["stage"]),
            dimension=data["dimension"],
            score=data["score"],
            role_key=data.get("role_key"),
        )


@dataclass
class PromptOptimization:
    """Prompt 优化建议"""
    role_key: str
    original_prompt: str
    optimized_prompt: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_key": self.role_key,
            "original_prompt": self.original_prompt,
            "optimized_prompt": self.optimized_prompt,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptOptimization":
        return cls(
            role_key=data["role_key"],
            original_prompt=data["original_prompt"],
            optimized_prompt=data["optimized_prompt"],
            reason=data["reason"],
        )


@dataclass
class ModelOptimization:
    """模型配置优化建议"""
    role_key: str
    original_config: Dict[str, Any]
    optimized_config: Dict[str, Any]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_key": self.role_key,
            "original_config": self.original_config,
            "optimized_config": self.optimized_config,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelOptimization":
        return cls(
            role_key=data["role_key"],
            original_config=data["original_config"],
            optimized_config=data["optimized_config"],
            reason=data["reason"],
        )


@dataclass
class OptimizationPlan:
    """优化方案"""
    prompt_optimizations: List[PromptOptimization]
    model_optimizations: List[ModelOptimization]
    target_improvements: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_optimizations": [p.to_dict() for p in self.prompt_optimizations],
            "model_optimizations": [m.to_dict() for m in self.model_optimizations],
            "target_improvements": self.target_improvements,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationPlan":
        return cls(
            prompt_optimizations=[
                PromptOptimization.from_dict(p) for p in data["prompt_optimizations"]
            ],
            model_optimizations=[
                ModelOptimization.from_dict(m) for m in data["model_optimizations"]
            ],
            target_improvements=data["target_improvements"],
        )


@dataclass
class ConfigSnapshot:
    """配置快照"""
    role_model_config: Dict[str, Dict[str, Any]]
    predefined_roles: Dict[str, Dict[str, Any]]  # 序列化后的角色定义
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_model_config": self.role_model_config,
            "predefined_roles": self.predefined_roles,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigSnapshot":
        return cls(
            role_model_config=data["role_model_config"],
            predefined_roles=data["predefined_roles"],
            timestamp=data["timestamp"],
        )


@dataclass
class OptimizationRecord:
    """单轮优化记录"""
    iteration: int
    timestamp: float
    stage_scores: Dict[str, float]
    evaluation_scores: Dict[str, float]  # 专业度/丰富度/结构化
    overall_score: float
    optimization_plan: Optional[OptimizationPlan]
    config_snapshot: ConfigSnapshot
    execution_time: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "stage_scores": self.stage_scores,
            "evaluation_scores": self.evaluation_scores,
            "overall_score": self.overall_score,
            "optimization_plan": (
                self.optimization_plan.to_dict()
                if self.optimization_plan is not None
                else None
            ),
            "config_snapshot": self.config_snapshot.to_dict(),
            "execution_time": self.execution_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationRecord":
        plan_data = data.get("optimization_plan")
        return cls(
            iteration=data["iteration"],
            timestamp=data["timestamp"],
            stage_scores=data["stage_scores"],
            evaluation_scores=data["evaluation_scores"],
            overall_score=data["overall_score"],
            optimization_plan=(
                OptimizationPlan.from_dict(plan_data)
                if plan_data is not None
                else None
            ),
            config_snapshot=ConfigSnapshot.from_dict(data["config_snapshot"]),
            execution_time=data["execution_time"],
        )


@dataclass
class OptimizationHistory:
    """优化历史"""
    records: List[OptimizationRecord]
    final_score: float
    converged: bool
    total_iterations: int
    total_time: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "final_score": self.final_score,
            "converged": self.converged,
            "total_iterations": self.total_iterations,
            "total_time": self.total_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationHistory":
        return cls(
            records=[OptimizationRecord.from_dict(r) for r in data["records"]],
            final_score=data["final_score"],
            converged=data["converged"],
            total_iterations=data["total_iterations"],
            total_time=data["total_time"],
        )
