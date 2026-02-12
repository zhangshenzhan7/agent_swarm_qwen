"""
沙箱代码解释器工具 — 为非 Qwen 原生模型提供代码执行能力

当 coder/analyst 等角色使用第三方模型（DeepSeek/GLM/Kimi）时，
DashScope 内置的 code_interpreter 不可用。此模块将阿里云 AgentRun
Sandbox Code Interpreter 封装为标准的 function-calling 工具，
使第三方模型也能通过工具调用执行代码。

参考文档：
https://help.aliyun.com/zh/functioncompute/fc/sandbox-sandbox-code-interepreter
"""

import atexit
import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from ..models.tool import ToolDefinition
from .backends.aliyun_fc_code_interpreter_backend import AliyunFCCodeInterpreterBackend

logger = logging.getLogger(__name__)

# 全局单例，避免每次调用都创建新沙箱
_shared_backend: Optional[AliyunFCCodeInterpreterBackend] = None

# 沙箱 ID 持久化文件路径（用于异常中断后的恢复清理）
_SANDBOX_STATE_FILE = Path(tempfile.gettempdir()) / "qwen_swarm_sandbox_state.json"


# ─── 沙箱 ID 持久化：记录活跃沙箱，供异常恢复时清理 ───


def _save_sandbox_state(sandbox_id: str, account_id: str, region_id: str) -> None:
    """将活跃沙箱信息写入临时文件"""
    try:
        state = {
            "sandbox_id": sandbox_id,
            "account_id": account_id,
            "region_id": region_id,
            "pid": os.getpid(),
        }
        _SANDBOX_STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        logger.debug(f"沙箱状态已持久化: {sandbox_id}")
    except Exception as e:
        logger.debug(f"沙箱状态持久化失败（非致命）: {e}")


def _clear_sandbox_state() -> None:
    """清除持久化的沙箱状态"""
    try:
        if _SANDBOX_STATE_FILE.exists():
            _SANDBOX_STATE_FILE.unlink()
            logger.debug("沙箱状态文件已清除")
    except Exception as e:
        logger.debug(f"清除沙箱状态文件失败（非致命）: {e}")


def _load_sandbox_state() -> Optional[Dict[str, str]]:
    """读取上次残留的沙箱状态"""
    try:
        if _SANDBOX_STATE_FILE.exists():
            data = json.loads(_SANDBOX_STATE_FILE.read_text(encoding="utf-8"))
            if data.get("sandbox_id") and data.get("account_id"):
                return data
    except Exception as e:
        logger.debug(f"读取沙箱状态文件失败（非致命）: {e}")
    return None


async def cleanup_stale_sandboxes() -> None:
    """清理上次异常退出残留的沙箱
    
    读取持久化的沙箱状态文件，如果存在则尝试停止对应的沙箱实例。
    应在后端启动时（如 FastAPI startup 事件）调用。
    
    该操作是幂等的：
    - 如果沙箱已被 idle timeout 自动回收，stop 请求会返回 404，安全忽略
    - 如果沙箱已停止，stop 是幂等的，直接返回 TERMINATED 状态
    """
    state = _load_sandbox_state()
    if not state:
        return
    
    sandbox_id = state["sandbox_id"]
    account_id = state["account_id"]
    region_id = state.get("region_id", "cn-hangzhou")
    old_pid = state.get("pid", "?")
    
    logger.info(f"发现残留沙箱 {sandbox_id}（来自 PID {old_pid}），正在清理...")
    
    import aiohttp
    base_url = f"https://{account_id}.agentrun-data.{region_id}.aliyuncs.com"
    url = f"{base_url}/sandboxes/{sandbox_id}/stop"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={
                    "X-Acs-Parent-Id": account_id,
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status in (200, 204):
                    logger.info(f"残留沙箱 {sandbox_id} 已成功停止")
                elif response.status == 404:
                    logger.info(f"残留沙箱 {sandbox_id} 已不存在（可能已被 idle timeout 回收）")
                else:
                    body = await response.text()
                    logger.warning(f"停止残留沙箱 {sandbox_id} 返回 {response.status}: {body}")
    except Exception as e:
        logger.warning(f"清理残留沙箱 {sandbox_id} 失败: {e}")
    finally:
        _clear_sandbox_state()


# ─── atexit 安全网 ───


def _atexit_cleanup():
    """进程退出时的安全网：确保沙箱被销毁"""
    global _shared_backend
    if _shared_backend is None:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(cleanup_sandbox())
        else:
            loop.run_until_complete(cleanup_sandbox())
    except Exception:
        # 无法异步清理，沙箱靠 idle timeout 自动回收
        # 状态文件保留，下次启动时 cleanup_stale_sandboxes() 会处理
        logger.warning("atexit: 无法异步清理沙箱，将依赖 idle timeout 或下次启动时清理")
        _shared_backend = None


atexit.register(_atexit_cleanup)


# ─── 核心功能 ───


def _get_or_create_backend(
    account_id: Optional[str] = None,
    region_id: str = "cn-hangzhou",
    template_name: str = "python-sandbox",
    sandbox_idle_timeout: int = 3600,
    access_key_id: Optional[str] = None,
    access_key_secret: Optional[str] = None,
) -> AliyunFCCodeInterpreterBackend:
    """获取或创建共享的沙箱后端实例"""
    global _shared_backend
    if _shared_backend is not None:
        return _shared_backend

    resolved_account_id = account_id or os.environ.get("ALIYUN_ACCOUNT_ID", "")
    if not resolved_account_id:
        raise ValueError(
            "阿里云主账号 ID 未配置。"
            "请设置环境变量 ALIYUN_ACCOUNT_ID 或在 AgentSwarmConfig 中传入 sandbox_account_id。"
        )

    _shared_backend = AliyunFCCodeInterpreterBackend(
        account_id=resolved_account_id,
        region_id=region_id,
        template_name=template_name,
        sandbox_idle_timeout=sandbox_idle_timeout,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )
    return _shared_backend


async def _handle_sandbox_execute(
    code: str,
    language: str = "python",
) -> Dict[str, Any]:
    """工具调用处理函数"""
    backend = _get_or_create_backend()
    result = await backend.execute(code, language, timeout=30.0)
    
    # 沙箱创建后持久化状态（用于异常恢复）
    if backend.sandbox_id:
        _save_sandbox_state(backend.sandbox_id, backend.account_id, backend.region_id)
    
    return result.to_dict()


def create_sandbox_code_interpreter_tool(
    account_id: Optional[str] = None,
    region_id: str = "cn-hangzhou",
    template_name: str = "python-sandbox",
    sandbox_idle_timeout: int = 3600,
    access_key_id: Optional[str] = None,
    access_key_secret: Optional[str] = None,
) -> ToolDefinition:
    """
    创建沙箱代码解释器工具定义

    Args:
        account_id: 阿里云主账号 ID（也可通过 ALIYUN_ACCOUNT_ID 环境变量设置）
        region_id: 地域 ID，默认 cn-hangzhou
        template_name: 沙箱模板名称
        sandbox_idle_timeout: 沙箱闲置超时（秒）
        access_key_id: 阿里云 AccessKey ID（用于自动创建模板）
        access_key_secret: 阿里云 AccessKey Secret

    Returns:
        ToolDefinition 实例
    """
    # 预初始化后端（验证配置），失败时延迟到首次调用再报错
    try:
        _get_or_create_backend(
            account_id, region_id, template_name, sandbox_idle_timeout,
            access_key_id, access_key_secret,
        )
    except ValueError:
        logger.warning(
            "sandbox_code_interpreter 工具注册时未找到 ALIYUN_ACCOUNT_ID，"
            "将在首次调用时再次尝试。"
        )

    return ToolDefinition(
        name="sandbox_code_interpreter",
        description=(
            "在云端安全沙箱中执行代码并返回结果。"
            "支持 Python 和 JavaScript。适用于数据分析、数值计算、代码验证等场景。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的代码",
                },
                "language": {
                    "type": "string",
                    "description": "编程语言 (python, javascript)",
                    "enum": ["python", "javascript"],
                    "default": "python",
                },
            },
            "required": ["code"],
        },
        handler=_handle_sandbox_execute,
        timeout=35.0,
    )


async def cleanup_sandbox():
    """清理共享沙箱资源
    
    应在以下时机调用：
    1. 每次任务执行完成后（在 finally 块中）
    2. AgentSwarm.shutdown() 时
    3. 进程退出时（通过 atexit 安全网）
    
    调用后全局单例会被重置，下次使用时会自动创建新沙箱。
    重复调用是安全的（幂等）。
    """
    global _shared_backend
    if _shared_backend is None:
        return
    
    backend = _shared_backend
    _shared_backend = None  # 先重置引用，防止并发调用重复清理
    
    sandbox_id = backend.sandbox_id  # 记录用于日志
    try:
        await backend.close()
        logger.info(f"沙箱已清理: {sandbox_id or '(未创建)'}")
    except Exception as e:
        logger.warning(f"沙箱清理异常 (sandbox_id={sandbox_id}): {e}")
    finally:
        _clear_sandbox_state()
