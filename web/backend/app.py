"""
AI 员工运行平台 - FastAPI 后端
真实调用 AgentSwarm 执行任务
"""

import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# 添加项目根目录到 path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 添加 web/backend 目录到 path（使 state, utils, models 等可直接导入）
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from src import (
    AgentSwarm,
    AgentSwarmConfig,
    AgentStatus,
    SupervisorConfig,
    QualityAssurance,
    MemoryManager,
    PREDEFINED_ROLES,
)
from state import state


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时清理上次异常退出残留的沙箱
    try:
        from src.tools import cleanup_stale_sandboxes
        await cleanup_stale_sandboxes()
    except Exception as e:
        print(f"⚠️ 残留沙箱清理失败（非致命）: {e}")
    try:
        from src.tools import cleanup_stale_browsers
        await cleanup_stale_browsers()
    except Exception as e:
        print(f"⚠️ 残留浏览器沙箱清理失败（非致命）: {e}")

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    state.api_key = api_key

    # 从环境变量初始化沙箱配置
    state.sandbox_account_id = os.environ.get("ALIYUN_ACCOUNT_ID") or None
    state.sandbox_access_key_id = os.environ.get("ALIYUN_ACCESS_KEY_ID") or None
    state.sandbox_access_key_secret = os.environ.get("ALIYUN_ACCESS_KEY_SECRET") or None
    sandbox_region = os.environ.get("SANDBOX_REGION_ID")
    if sandbox_region:
        state.sandbox_region_id = sandbox_region
    sandbox_template = os.environ.get("SANDBOX_TEMPLATE_NAME")
    if sandbox_template:
        state.sandbox_template_name = sandbox_template
    sandbox_timeout = os.environ.get("SANDBOX_IDLE_TIMEOUT")
    if sandbox_timeout:
        try:
            state.sandbox_idle_timeout = int(sandbox_timeout)
        except ValueError:
            pass

    # 初始化记忆管理器（不依赖 API Key）
    state.memory_manager = MemoryManager(
        max_short_term=100,
        max_long_term=1000,
        max_working=20,
        decay_rate=0.1,
    )
    print("✅ 记忆管理器初始化完成")

    if api_key:
        config = AgentSwarmConfig(
            api_key=api_key,
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

        print(f"✅ AgentSwarm 和质量保障系统初始化完成")
    else:
        print("⚠️ 未设置 DASHSCOPE_API_KEY，请在页面中配置")

    # 初始化 AI 主管显示状态（作为模板）
    state.agents["supervisor"] = {
        "id": "supervisor",
        "name": "AI 主管",
        "role": "supervisor",
        "description": "分析任务、调研背景、改写需求、制定执行计划（支持多实例并行）",
        "status": AgentStatus.IDLE.value,
        "avatar": "👔",
        "current_task": None,
        "tools": ["分析", "调研", "改写", "规划"],
        "stats": {"tasks_completed": 0, "plans_created": 0, "avg_complexity": 0},
        "is_supervisor": True,
    }

    state.agents["quality_checker"] = {
        "id": "quality_checker",
        "name": "AI 质量检查员",
        "role": "quality_checker",
        "description": "评估输出质量、检测冲突、反思改进",
        "status": AgentStatus.IDLE.value,
        "avatar": "🔬",
        "current_task": None,
        "tools": ["质量评估", "冲突检测", "反思改进", "自我纠错"],
        "stats": {"tasks_completed": 0, "avg_quality_score": 0, "improvements": 0},
        "is_quality_checker": True,
    }

    avatars = {
        "searcher": "🔍", "researcher": "🔬", "analyst": "📊",
        "writer": "✍️", "coder": "💻", "translator": "🌐",
        "fact_checker": "✅", "summarizer": "📋", "creative": "💡",
        "image_analyst": "🖼️",
    }

    multimodal_roles = {"text_to_image", "text_to_video", "image_to_video", "voice_synthesizer"}
    multimodal_avatars = {
        "text_to_image": "🎨", "text_to_video": "🎬",
        "image_to_video": "🎞️", "voice_synthesizer": "🎙️",
    }

    for role_key, role in PREDEFINED_ROLES.items():
        is_multimodal = role_key in multimodal_roles
        state.agents[f"agent_{role_key}"] = {
            "id": f"agent_{role_key}",
            "name": role.name,
            "role": role_key,
            "description": role.description,
            "status": AgentStatus.IDLE.value,
            "avatar": multimodal_avatars.get(role_key, avatars.get(role_key, "🤖")),
            "current_task": None,
            "tools": role.available_tools,
            "stats": {"tasks_completed": 0, "total_time": 0, "success_rate": 100},
            **({"is_multimodal": True} if is_multimodal else {}),
        }

    yield

    if state.swarm:
        try:
            await state.swarm.shutdown()
        except:
            pass


# ==================== 创建 FastAPI 应用 ====================

app = FastAPI(
    title="AI 员工运行平台",
    description="基于 AgentSwarm 的多智能体协作平台",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 注册路由 ====================

from routes.config import router as config_router
from routes.tasks import router as tasks_router
from routes.files import router as files_router
from routes.quality import router as quality_router
from routes.agents import router as agents_router
from routes.multimodal import router as multimodal_router
from routes.meeting import router as meeting_router
from routes.websocket import router as websocket_router
from routes.adaptive import router as adaptive_router
from routes.artifacts import router as artifacts_router

app.include_router(config_router)
app.include_router(tasks_router)
app.include_router(files_router)
app.include_router(quality_router)
app.include_router(agents_router)
app.include_router(multimodal_router)
app.include_router(meeting_router)
app.include_router(websocket_router)
app.include_router(adaptive_router)
app.include_router(artifacts_router)


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
