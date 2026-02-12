"""输出处理层（output）。

本子包包含 Qwen Agent Swarm 系统的输出处理组件，负责任务结果的
聚合、处理和存储。

子模块：
    - pipeline: 输出处理管道
    - registry: 输出处理器注册表
    - artifact_storage: 产物存储
    - result_aggregator: 结果聚合器
    - handlers: 各类输出处理器
"""

from ..output_pipeline import OutputPipeline
from ..output_registry import OutputTypeRegistry
from ..artifact_storage import ArtifactStorage
from ..result_aggregator import ResultAggregatorImpl

# 别名
ResultAggregator = ResultAggregatorImpl
OutputRegistry = OutputTypeRegistry

__all__ = [
    "OutputPipeline",
    "OutputTypeRegistry",
    "OutputRegistry",
    "ArtifactStorage",
    "ResultAggregatorImpl",
    "ResultAggregator",
]
