"""配置和认证相关路由"""

from datetime import datetime
from fastapi import APIRouter, Response

from src import (
    AgentSwarm,
    AgentSwarmConfig,
    SupervisorConfig,
    QualityAssurance,
)
from state import state
from models import ApiKeyUpdate, ExecutionModeUpdate, SandboxConfigUpdate

router = APIRouter()


@router.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "swarm_initialized": state.swarm is not None,
        "api_key_configured": bool(state.api_key)
    }


@router.get("/api/config")
async def get_config():
    return {
        "api_key_configured": bool(state.api_key),
        "api_key_preview": state.api_key[:8] + "..." if state.api_key and len(state.api_key) > 8 else None,
        "execution_mode": state.execution_mode,
        "sandbox_account_id": state.sandbox_account_id or "",
        "sandbox_access_key_configured": bool(state.sandbox_access_key_id and state.sandbox_access_key_secret),
        "sandbox_region_id": state.sandbox_region_id,
        "sandbox_template_name": state.sandbox_template_name,
        "sandbox_idle_timeout": state.sandbox_idle_timeout,
    }


@router.post("/api/config/apikey")
async def set_api_key(data: ApiKeyUpdate, response: Response):
    state.api_key = data.api_key
    try:
        if state.swarm:
            try:
                await state.swarm.shutdown()
            except:
                pass

        config = AgentSwarmConfig(
            api_key=data.api_key,
            max_concurrent_agents=32,
            max_tool_calls=1500,
            complexity_threshold=3.0,
            execution_timeout=3600.0,
            enable_team_mode=(state.execution_mode == "team"),
            sandbox_account_id=state.sandbox_account_id,
            sandbox_region_id=state.sandbox_region_id,
            sandbox_template_name=state.sandbox_template_name,
            sandbox_idle_timeout=state.sandbox_idle_timeout,
            sandbox_access_key_id=state.sandbox_access_key_id,
            sandbox_access_key_secret=state.sandbox_access_key_secret,
        )
        state.swarm = AgentSwarm(config=config)
        state.swarm._initialize()

        state.supervisor_config = SupervisorConfig(
            max_react_iterations=5,
            enable_research=True,
            verbose_planning=True,
        )

        state.quality_assurance = QualityAssurance(
            qwen_client=state.swarm.qwen_client,
            quality_threshold=6.0,
            max_reflection_iterations=2,
        )

        print(f"✅ AgentSwarm 和质量保障系统初始化成功")

        response.set_cookie(
            key="dashscope_api_key",
            value=data.api_key,
            max_age=30 * 24 * 60 * 60,
            httponly=True,
            samesite="lax"
        )
        return {"success": True, "message": "API Key 设置成功，已保存到浏览器"}
    except Exception as e:
        return {"success": False, "message": f"初始化失败: {str(e)}"}


@router.post("/api/config/logout")
async def logout(response: Response):
    state.api_key = None
    response.delete_cookie("dashscope_api_key")
    return {"success": True, "message": "已退出登录"}


@router.get("/api/config/execution-mode")
async def get_execution_mode():
    """获取当前执行模式"""
    return {
        "mode": state.execution_mode,
        "available_modes": ["scheduler", "team"],
        "descriptions": {
            "scheduler": "调度器模式：静态分层并行调度所有子任务",
            "team": "团队模式：基于依赖关系的事件驱动波次执行",
        },
    }


@router.post("/api/config/execution-mode")
async def set_execution_mode(data: ExecutionModeUpdate):
    """设置执行模式"""
    if data.mode not in ("scheduler", "team"):
        return {"success": False, "message": "无效的执行模式，必须是 'scheduler' 或 'team'"}

    try:
        state.execution_mode = data.mode

        if state.swarm:
            state.swarm.set_execution_mode(data.mode)

        mode_name = "调度器模式" if data.mode == "scheduler" else "团队模式"
        print(f"✅ 执行模式已切换为: {mode_name}")
        return {
            "success": True,
            "message": f"已切换为{mode_name}",
            "mode": data.mode,
        }
    except Exception as e:
        return {"success": False, "message": f"切换失败: {str(e)}"}


@router.get("/api/config/sandbox")
async def get_sandbox_config():
    """获取沙箱代码解释器配置"""
    return {
        "sandbox_account_id": state.sandbox_account_id or "",
        "sandbox_access_key_configured": bool(state.sandbox_access_key_id and state.sandbox_access_key_secret),
        "sandbox_region_id": state.sandbox_region_id,
        "sandbox_template_name": state.sandbox_template_name,
        "sandbox_idle_timeout": state.sandbox_idle_timeout,
    }


@router.post("/api/config/sandbox")
async def set_sandbox_config(data: SandboxConfigUpdate):
    """设置沙箱代码解释器配置"""
    try:
        state.sandbox_account_id = data.sandbox_account_id or None
        state.sandbox_region_id = data.sandbox_region_id
        state.sandbox_template_name = data.sandbox_template_name
        state.sandbox_idle_timeout = data.sandbox_idle_timeout

        # 保存 AK/SK（仅在前端传入时更新，空字符串视为清除）
        if data.sandbox_access_key_id is not None:
            state.sandbox_access_key_id = data.sandbox_access_key_id or None
        if data.sandbox_access_key_secret is not None:
            state.sandbox_access_key_secret = data.sandbox_access_key_secret or None

        # 如果 swarm 已初始化，更新其配置
        if state.swarm:
            state.swarm.config.sandbox_account_id = state.sandbox_account_id
            state.swarm.config.sandbox_region_id = state.sandbox_region_id
            state.swarm.config.sandbox_template_name = state.sandbox_template_name
            state.swarm.config.sandbox_idle_timeout = state.sandbox_idle_timeout
            state.swarm.config.sandbox_access_key_id = state.sandbox_access_key_id
            state.swarm.config.sandbox_access_key_secret = state.sandbox_access_key_secret

        configured = bool(state.sandbox_account_id)
        ak_configured = bool(state.sandbox_access_key_id and state.sandbox_access_key_secret)
        print(f"✅ 沙箱配置已更新 (account_id={'已设置' if configured else '未设置'}, ak={'已设置' if ak_configured else '未设置'})")
        return {
            "success": True,
            "message": "沙箱配置已保存" + ("" if configured else "（主账号 ID 未设置，沙箱功能暂不可用）"),
        }
    except Exception as e:
        return {"success": False, "message": f"保存失败: {str(e)}"}
