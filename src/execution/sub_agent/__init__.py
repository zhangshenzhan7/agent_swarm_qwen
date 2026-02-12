"""子智能体子包（SubAgent）。

本子包包含 SubAgent 的拆分模块，负责执行具体子任务并与 Qwen 模型交互。

子模块：
    - executor: SubAgentExecutor 执行引擎核心
    - tool_handler: ToolCallHandler 工具调用处理
    - prompt: PromptBuilder 提示词构建
"""

# 从原始模块导入以保持向后兼容
from ...sub_agent import SubAgentImpl

# 别名
SubAgentExecutor = SubAgentImpl

__all__ = [
    "SubAgentImpl",
    "SubAgentExecutor",
]
