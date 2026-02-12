"""
网页搜索与浏览工具 — 为非 Qwen 原生模型提供联网搜索和网页浏览能力

当 researcher/fact_checker/analyst/translator 等角色使用第三方模型时，
DashScope 内置的 enable_search / web_extractor 不可用。此模块将搜索和网页抓取
封装为标准的 function-calling 工具，使第三方模型也能通过工具调用搜索信息、
浏览网页、提取内容。

支持两种操作：
- search: 通过搜索引擎搜索关键词，返回结构化搜索结果（标题、URL、摘要）
- fetch:  访问指定 URL，提取页面标题和文本内容
"""

import atexit
import asyncio
import logging
import os
from typing import Dict, Any, Optional

from ..models.tool import ToolDefinition
from .backends.aliyun_browser_tool_backend import AliyunBrowserToolBackend

logger = logging.getLogger(__name__)

# 全局单例
_shared_backend: Optional[AliyunBrowserToolBackend] = None


def _get_or_create_backend(
    account_id: Optional[str] = None,
    region_id: str = "cn-hangzhou",
    **kwargs,
) -> AliyunBrowserToolBackend:
    """获取或创建共享的后端实例"""
    global _shared_backend
    if _shared_backend is not None:
        return _shared_backend

    resolved_account_id = account_id or os.environ.get("ALIYUN_ACCOUNT_ID", "")

    _shared_backend = AliyunBrowserToolBackend(
        account_id=resolved_account_id,
        region_id=region_id,
    )
    return _shared_backend


async def _handle_browser_navigate(
    action: str = "search",
    query: str = "",
    url: str = "",
    extract_content: bool = True,
    num_results: int = 8,
) -> Dict[str, Any]:
    """工具调用处理函数：支持 search 和 fetch 两种操作"""
    backend = _get_or_create_backend()

    if action == "search":
        if not query:
            return {"success": False, "error": "search 操作需要提供 query 参数"}
        return await backend.search(
            query=query,
            num_results=num_results,
            timeout=20.0,
        )
    elif action == "fetch":
        if not url:
            return {"success": False, "error": "fetch 操作需要提供 url 参数"}
        return await backend.navigate_and_extract(
            url=url,
            extract_content=extract_content,
            timeout=30.0,
        )
    else:
        return {"success": False, "error": f"未知操作: {action}，支持 search 或 fetch"}


def create_sandbox_browser_tool(
    account_id: Optional[str] = None,
    region_id: str = "cn-hangzhou",
    sandbox_idle_timeout: int = 3600,
    access_key_id: Optional[str] = None,
    access_key_secret: Optional[str] = None,
) -> ToolDefinition:
    """
    创建网页浏览工具定义

    Args:
        account_id: 阿里云主账号 ID（保留参数，HTTP 模式下非必需）
        region_id: 地域 ID
        sandbox_idle_timeout: 保留参数
        access_key_id: 保留参数
        access_key_secret: 保留参数

    Returns:
        ToolDefinition 实例
    """
    _get_or_create_backend(account_id, region_id)

    return ToolDefinition(
        name="sandbox_browser",
        description=(
            "联网搜索和网页浏览工具。支持两种操作模式：\n"
            "1. search（搜索）：通过搜索引擎搜索关键词，返回搜索结果列表（标题、URL、摘要）。"
            "适用于查找信息、获取最新数据、事实核查。\n"
            "2. fetch（抓取）：访问指定 URL，提取页面标题和完整文本内容。"
            "适用于深入阅读搜索结果中的某个页面。\n"
            "典型工作流：先用 search 搜索关键词 → 从结果中选择相关 URL → 用 fetch 获取详细内容。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "fetch"],
                    "description": "操作类型：search=搜索关键词，fetch=访问URL提取内容",
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词（action=search 时必填）",
                },
                "url": {
                    "type": "string",
                    "description": "要访问的网页 URL（action=fetch 时必填，必须以 http:// 或 https:// 开头）",
                },
                "num_results": {
                    "type": "integer",
                    "description": "搜索返回的结果数量（默认 8，action=search 时有效）",
                    "default": 8,
                },
                "extract_content": {
                    "type": "boolean",
                    "description": "是否提取页面文本内容（默认 true，action=fetch 时有效）",
                    "default": True,
                },
            },
            "required": ["action"],
        },
        handler=_handle_browser_navigate,
        timeout=35.0,
    )


async def cleanup_browser():
    """清理后端资源（关闭 HTTP 会话）"""
    global _shared_backend
    if _shared_backend is None:
        return

    backend = _shared_backend
    _shared_backend = None

    try:
        await backend.close()
        logger.info("浏览器后端已清理")
    except Exception as e:
        logger.warning(f"浏览器后端清理异常: {e}")


async def cleanup_stale_browsers() -> None:
    """保留接口兼容性（HTTP 模式无需清理残留沙箱）"""
    pass


def _atexit_cleanup():
    global _shared_backend
    if _shared_backend is None:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(cleanup_browser())
        else:
            loop.run_until_complete(cleanup_browser())
    except Exception:
        _shared_backend = None


atexit.register(_atexit_cleanup)
