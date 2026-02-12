"""Built-in tools for Qwen Agent Swarm.

联网搜索和网页抽取能力已通过 DashScope API 内置提供:
- enable_search=True: 启用联网搜索
- search_options.search_strategy="agent_max": 启用网页抽取(web_extractor)
无需注册额外的搜索/浏览器工具。
"""

from .code_execution import CodeExecutionTool, create_code_execution_tool
from .file_operations import FileOperationsTool, create_file_operations_tool
from .code_review import CodeReviewTool, create_code_review_tool
from .data_analysis import DataAnalysisTool, create_data_analysis_tool
from .sandbox_code_interpreter import (
    create_sandbox_code_interpreter_tool,
    cleanup_sandbox,
    cleanup_stale_sandboxes,
)
from .sandbox_browser import (
    create_sandbox_browser_tool,
    cleanup_browser,
    cleanup_stale_browsers,
)

__all__ = [
    "CodeExecutionTool",
    "create_code_execution_tool",
    "FileOperationsTool",
    "create_file_operations_tool",
    "CodeReviewTool",
    "create_code_review_tool",
    "DataAnalysisTool",
    "create_data_analysis_tool",
    "create_sandbox_code_interpreter_tool",
    "cleanup_sandbox",
    "cleanup_stale_sandboxes",
    "create_sandbox_browser_tool",
    "cleanup_browser",
    "cleanup_stale_browsers",
]
