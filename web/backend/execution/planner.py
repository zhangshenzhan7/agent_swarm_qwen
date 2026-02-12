"""Supervisor 规划步骤执行 - 通过 TaskBoard + WaveExecutor 实现事件驱动的动态波次执行"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Set

from src import TaskStatus, AgentStatus, PREDEFINED_ROLES
from src.models.enums import OutputType
from src.output_registry import OutputTypeRegistry
from src.output_pipeline import OutputPipeline
from src.artifact_storage import ArtifactStorage
from src.handlers import register_all_handlers
from state import state
from utils import clean_thinking_tags
from execution.report import generate_final_report
from execution.helpers import analyze_dependency_layers, map_role_hint_to_key

# 上传目录
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), '..', 'uploads')

logger = logging.getLogger(__name__)


async def _merge_video_segments(
    video_urls: List[str], task_id: str, log_event
) -> Optional[str]:
    """下载多段视频并用 FFmpeg 合并为一个文件。

    Returns:
        合并后视频的本地 URL（如 /api/files/merged_xxx.mp4），失败返回 None。
    """
    if not shutil.which("ffmpeg"):
        await log_event("⚠️ 未检测到 ffmpeg，无法合并视频", "warning")
        return None

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="video_merge_")

    try:
        import aiohttp

        # 1. 下载所有视频片段
        downloaded: List[str] = []
        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(video_urls):
                if not url:
                    continue
                seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp4")
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                        if resp.status == 200:
                            with open(seg_path, "wb") as f:
                                f.write(await resp.read())
                            downloaded.append(seg_path)
                        else:
                            await log_event(f"⚠️ 下载视频片段 {i+1} 失败: HTTP {resp.status}", "warning")
                except Exception as e:
                    await log_event(f"⚠️ 下载视频片段 {i+1} 异常: {str(e)[:60]}", "warning")

        if len(downloaded) < 2:
            await log_event("⚠️ 可用视频片段不足，跳过合并", "warning")
            return None

        # 2. 生成 FFmpeg concat 文件列表
        list_path = os.path.join(tmp_dir, "filelist.txt")
        with open(list_path, "w") as f:
            for seg in downloaded:
                f.write(f"file '{seg}'\n")

        # 3. 用 FFmpeg concat demuxer 合并
        merged_filename = f"merged_{task_id[:8]}_{uuid.uuid4().hex[:6]}.mp4"
        merged_path = os.path.join(UPLOAD_DIR, merged_filename)

        loop = asyncio.get_event_loop()
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_path, "-c", "copy", merged_path,
        ]

        def run_ffmpeg():
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            return result.returncode, result.stderr

        returncode, stderr = await loop.run_in_executor(None, run_ffmpeg)

        if returncode != 0:
            # concat copy 失败时尝试重新编码
            await log_event("⚠️ 视频直接拼接失败，尝试重新编码合并...", "warning")
            cmd_reencode = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                merged_path,
            ]

            def run_ffmpeg_reencode():
                result = subprocess.run(
                    cmd_reencode, capture_output=True, text=True, timeout=300
                )
                return result.returncode, result.stderr

            returncode, stderr = await loop.run_in_executor(None, run_ffmpeg_reencode)

        if returncode == 0 and os.path.exists(merged_path):
            return f"/api/files/{merged_filename}"
        else:
            logger.error(f"FFmpeg 合并失败: {stderr[:200]}")
            await log_event(f"⚠️ FFmpeg 合并失败: {stderr[:80]}", "warning")
            return None

    except ImportError:
        await log_event("⚠️ 缺少 aiohttp 库，无法下载视频片段进行合并", "warning")
        return None
    except Exception as e:
        logger.error(f"视频合并异常: {e}")
        await log_event(f"⚠️ 视频合并异常: {str(e)[:60]}", "warning")
        return None
    finally:
        # 清理临时目录
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def execute_with_supervisor_plan(task_id: str, task: Dict, content: str, metadata: Optional[Dict], log_event, update_stage, stage_offset: int):
    """
    使用 Supervisor 规划的步骤执行任务
    通过 TaskBoard + WaveExecutor 实现事件驱动的动态波次执行
    """
    from src.qwen.models import Message, QwenConfig
    from src.task_board import TaskBoard
    from src.wave_executor import WaveExecutor
    from src.models.task import SubTask
    from src.models.team import TaskBoardStatus

    steps = task["plan"]["execution_flow"]["steps"]
    step_list = list(steps.values())

    # ========== 阶段 1: 任务分析 ==========
    task["status"] = TaskStatus.ANALYZING.value
    await update_stage(stage_offset, "running")
    await log_event("🔍 正在分析任务...")

    # 分析依赖层级（用于日志展示）
    dep_layers = analyze_dependency_layers(step_list)
    await update_stage(stage_offset, "completed", f"分析完成，{len(step_list)} 个步骤")
    await log_event(f"✅ 任务分析完成，{len(step_list)} 个步骤，{len(dep_layers)} 层执行流程")

    # ========== 阶段 2: 任务分解 → 发布到 TaskBoard ==========
    task["status"] = TaskStatus.DECOMPOSING.value
    await update_stage(stage_offset + 1, "running")
    await log_event("🔧 正在准备执行计划，发布任务到共享任务板...")

    # 将 Supervisor 步骤转换为 SubTask 对象
    subtasks = []
    dependencies_map: Dict[str, Set[str]] = {}

    for step in step_list:
        step_id = step.get("step_id")
        deps = step.get("dependencies", [])
        valid_deps = set(d for d in deps if d in steps)

        agent_type = step.get("agent_type", "researcher")
        role_key = map_role_hint_to_key(agent_type)
        if not role_key:
            role_key = "researcher"

        subtask = SubTask(
            id=step_id,
            parent_task_id=task_id,
            content=step.get("description", step.get("name", "执行任务")),
            role_hint=role_key,
            dependencies=valid_deps,
            priority=step.get("step_number", 0),
            estimated_complexity=1.0,
        )
        subtasks.append(subtask)
        dependencies_map[step_id] = valid_deps

        # 初始化步骤状态
        if valid_deps:
            steps[step_id]["status"] = "waiting"
        else:
            steps[step_id]["status"] = "pending"

    # 创建 TaskBoard 并发布任务
    task_board = TaskBoard()
    await task_board.publish_tasks(subtasks, dependencies_map)

    # ========== 创建质量门控评审器 ==========
    quality_gate_reviewer = None
    supervisor_instance = state.active_supervisors.get(task_id)
    supervisor_config = state.supervisor_config
    if (supervisor_instance and supervisor_config 
            and getattr(supervisor_config, 'enable_quality_gates', False)):
        from src.core.supervisor.quality_gate import QualityGateReviewer
        from src.core.supervisor.flow import ExecutionFlow as CoreExecutionFlow
        # 创建一个轻量 ExecutionFlow 用于质量门控追踪
        core_flow = CoreExecutionFlow()
        quality_gate_reviewer = QualityGateReviewer(
            supervisor=supervisor_instance,
            config=supervisor_config,
            execution_flow=core_flow,
            task_board=task_board,
        )
        await log_event("🔍 质量门控已启用")

    # 广播初始状态
    await state.broadcast("task_updated", task)

    await update_stage(stage_offset + 1, "completed", f"发布 {len(step_list)} 个任务到任务板")
    await log_event(f"📊 依赖分析: {len(dep_layers)} 层执行流程")
    for i, layer in enumerate(dep_layers):
        layer_names = [s.get("name", s.get("step_id")) for s in layer]
        await log_event(f"   第 {i+1} 层: {', '.join(layer_names)}")

    # ========== 阶段 3: 智能体分配 ==========
    await update_stage(stage_offset + 2, "running")
    await log_event("👥 正在分配智能体（WaveExecutor 事件驱动模式）...")
    await update_stage(stage_offset + 2, "completed", f"就绪，{len(dep_layers)} 层动态波次")

    # ========== 阶段 4: 并行执行（WaveExecutor 事件驱动）==========
    task["status"] = TaskStatus.EXECUTING.value
    await update_stage(stage_offset + 3, "running")

    # 存储步骤结果
    step_results: Dict[str, Any] = {}
    step_agent_mapping: Dict[str, str] = {}
    failed_steps: Set[str] = set()

    # ========== 多模态生成任务执行函数 ==========
    async def execute_multimodal_step(
        role_key: str,
        step_desc: str,
        input_context: str,
        instance: Dict,
        step: Dict,
        log_event
    ) -> Tuple[bool, str, str]:
        """执行多模态生成任务，输出统一为 JSON 字符串"""
        import json as _json

        def _extract_prompt_from_context(ctx: str, fallback: str) -> str:
            """从上游 JSON 上下文中提取提示词，回退到 step_desc"""
            if not ctx:
                return fallback
            # 尝试从 JSON 上下文中提取 text_content
            try:
                ctx_data = _json.loads(ctx)
                if isinstance(ctx_data, dict):
                    return ctx_data.get("text_content", fallback)[:500]
                elif isinstance(ctx_data, list):
                    # 多个上游结果，拼接 text_content
                    parts = [item.get("text_content", "") for item in ctx_data if isinstance(item, dict) and item.get("text_content")]
                    return "\n".join(parts)[:500] if parts else fallback
            except (_json.JSONDecodeError, TypeError):
                pass
            # 回退：直接用文本（截断）
            return ctx[:500]

        def _extract_image_urls_from_context(ctx: str) -> list:
            """从上游 JSON 上下文中提取图片 URL 列表"""
            urls = []
            try:
                ctx_data = _json.loads(ctx)
                if isinstance(ctx_data, dict):
                    urls.extend(ctx_data.get("media_urls", []))
                elif isinstance(ctx_data, list):
                    for item in ctx_data:
                        if isinstance(item, dict):
                            urls.extend(item.get("media_urls", []))
            except (_json.JSONDecodeError, TypeError):
                pass
            if not urls:
                # 回退：正则提取
                import re
                urls = re.findall(r'(https?://[^\s\"\'\)\]]+\.(?:png|jpg|jpeg|gif|webp|bmp)(?:[^\s\"\'\)\]]*)?)', ctx or "")
            return urls

        try:
            if role_key == "text_to_image":
                prompt = _extract_prompt_from_context(input_context, step_desc)
                await log_event(f"🎨 正在生成图像: {prompt[:50]}...")

                gen_log = {"timestamp": datetime.now().isoformat(), "message": f"调用文生图 API，提示词: {prompt[:100]}...", "level": "info"}
                state.agent_logs[instance["id"]].append(gen_log)
                await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": gen_log})

                result = await state.swarm.qwen_client.text_to_image(prompt=prompt, model="wanx2.1-t2i-turbo", size="1024*1024")

                if result["success"]:
                    images = result.get("images", [])
                    image_urls = [img.get("url") for img in images if img.get("url")]
                    output = _json.dumps({
                        "type": "image",
                        "media_urls": image_urls,
                        "prompt": prompt,
                        "count": len(image_urls),
                        "text_content": f"图像生成成功，共 {len(image_urls)} 张。提示词: {prompt}"
                    }, ensure_ascii=False)

                    success_log = {"timestamp": datetime.now().isoformat(), "message": f"图像生成成功，共 {len(images)} 张", "level": "success"}
                    state.agent_logs[instance["id"]].append(success_log)
                    await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": success_log})
                    return True, output, None
                else:
                    return False, None, result.get("error", "图像生成失败")

            elif role_key == "text_to_video":
                prompt = _extract_prompt_from_context(input_context, step_desc)
                await log_event(f"🎬 正在生成视频: {prompt[:50]}...")

                gen_log = {"timestamp": datetime.now().isoformat(), "message": f"调用文生视频 API，提示词: {prompt[:100]}...", "level": "info"}
                state.agent_logs[instance["id"]].append(gen_log)
                await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": gen_log})

                result = await state.swarm.qwen_client.text_to_video(prompt=prompt, model="wanx2.1-t2v-turbo")

                if result["success"]:
                    video_task_id = result.get("task_id")
                    await log_event(f"⏳ 视频生成任务已提交，任务ID: {video_task_id}，等待生成...")

                    max_wait = 180
                    wait_interval = 10
                    elapsed = 0
                    while elapsed < max_wait:
                        await asyncio.sleep(wait_interval)
                        elapsed += wait_interval
                        status_result = await state.swarm.qwen_client.get_video_task_result(video_task_id)
                        if status_result.get("status") == "completed":
                            video_url = status_result.get("video_url")
                            output = _json.dumps({
                                "type": "video",
                                "media_urls": [video_url],
                                "prompt": prompt,
                                "text_content": f"视频生成成功。提示词: {prompt}"
                            }, ensure_ascii=False)
                            success_log = {"timestamp": datetime.now().isoformat(), "message": "视频生成成功", "level": "success"}
                            state.agent_logs[instance["id"]].append(success_log)
                            await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": success_log})
                            return True, output, None
                        elif status_result.get("status") == "failed":
                            return False, None, status_result.get("error", "视频生成失败")
                        await log_event(f"⏳ 视频生成中... ({elapsed}s/{max_wait}s)")

                    # 超时
                    output = _json.dumps({
                        "type": "video",
                        "media_urls": [],
                        "async_task_id": video_task_id,
                        "prompt": prompt,
                        "text_content": f"视频生成任务已提交(ID: {video_task_id})，需要较长时间，请稍后查询。"
                    }, ensure_ascii=False)
                    return True, output, None
                else:
                    return False, None, result.get("error", "视频生成任务提交失败")

            elif role_key == "image_to_video":
                image_urls = _extract_image_urls_from_context(input_context)
                image_url = image_urls[0] if image_urls else ""
                prompt = step_desc

                if not image_url:
                    return False, None, "图生视频需要提供图片URL，但未从上游 JSON 中找到有效的图片URL"

                await log_event(f"🎞️ 正在将图片转为视频...")

                gen_log = {"timestamp": datetime.now().isoformat(), "message": f"调用图生视频 API，图片: {image_url[:80]}...", "level": "info"}
                state.agent_logs[instance["id"]].append(gen_log)
                await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": gen_log})

                result = await state.swarm.qwen_client.image_to_video(image_url=image_url, prompt=prompt, model="wanx2.1-i2v-turbo")

                if result["success"]:
                    video_task_id = result.get("task_id")
                    await log_event(f"⏳ 图生视频任务已提交，任务ID: {video_task_id}，等待生成...")

                    max_wait = 180
                    wait_interval = 10
                    elapsed = 0
                    while elapsed < max_wait:
                        await asyncio.sleep(wait_interval)
                        elapsed += wait_interval
                        status_result = await state.swarm.qwen_client.get_video_task_result(video_task_id)
                        if status_result.get("status") == "completed":
                            video_url = status_result.get("video_url")
                            output = _json.dumps({
                                "type": "video",
                                "media_urls": [video_url],
                                "source_image": image_url,
                                "text_content": f"图生视频成功。原图: {image_url}"
                            }, ensure_ascii=False)
                            success_log = {"timestamp": datetime.now().isoformat(), "message": "图生视频成功", "level": "success"}
                            state.agent_logs[instance["id"]].append(success_log)
                            await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": success_log})
                            return True, output, None
                        elif status_result.get("status") == "failed":
                            return False, None, status_result.get("error", "图生视频失败")
                        await log_event(f"⏳ 视频生成中... ({elapsed}s/{max_wait}s)")

                    output = _json.dumps({
                        "type": "video",
                        "media_urls": [],
                        "async_task_id": video_task_id,
                        "source_image": image_url,
                        "text_content": f"图生视频任务已提交(ID: {video_task_id})，请稍后查询。"
                    }, ensure_ascii=False)
                    return True, output, None
                else:
                    return False, None, result.get("error", "图生视频任务提交失败")

            elif role_key == "voice_synthesizer":
                text = step_desc
                if input_context:
                    try:
                        ctx_data = _json.loads(input_context)
                        if isinstance(ctx_data, dict):
                            text = ctx_data.get("text_content", step_desc)[:2000]
                        elif isinstance(ctx_data, list):
                            parts = [item.get("text_content", "") for item in ctx_data if isinstance(item, dict)]
                            text = "\n".join(parts)[:2000] if parts else step_desc
                    except (_json.JSONDecodeError, TypeError):
                        text = input_context[:2000]

                await log_event(f"🎙️ 正在合成语音...")

                gen_log = {"timestamp": datetime.now().isoformat(), "message": f"调用语音合成 API，文本: {text[:50]}...", "level": "info"}
                state.agent_logs[instance["id"]].append(gen_log)
                await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": gen_log})

                result = await state.swarm.qwen_client.text_to_speech(text=text, model="cosyvoice-v1", voice="longxiaochun")

                if result["success"]:
                    audio_data = result.get("audio_data")
                    audio_id = uuid.uuid4().hex[:8]
                    audio_filename = f"audio_{audio_id}.mp3"
                    audio_path = os.path.join(UPLOAD_DIR, audio_filename)
                    with open(audio_path, "wb") as f:
                        f.write(audio_data)
                    audio_url = f"/api/files/{audio_filename}"

                    output = _json.dumps({
                        "type": "audio",
                        "media_urls": [audio_url],
                        "text_content": f"语音合成成功。配音文本: {text[:200]}"
                    }, ensure_ascii=False)

                    success_log = {"timestamp": datetime.now().isoformat(), "message": "语音合成成功", "level": "success"}
                    state.agent_logs[instance["id"]].append(success_log)
                    await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": success_log})
                    return True, output, None
                else:
                    return False, None, result.get("error", "语音合成失败")

            else:
                return False, None, f"未知的多模态角色: {role_key}"

        except Exception as e:
            error_log = {"timestamp": datetime.now().isoformat(), "message": f"多模态任务执行失败: {str(e)}", "level": "error"}
            state.agent_logs[instance["id"]].append(error_log)
            await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": error_log})
            return False, None, str(e)

    async def execute_single_step(step: Dict, input_context: str = "") -> Tuple[bool, str, str]:
        """执行单个步骤"""
        step_id = step.get("step_id")
        step_name = step.get("name", "执行任务")
        step_desc = step.get("description", step_name)
        agent_type = step.get("agent_type", "researcher")

        role_key = map_role_hint_to_key(agent_type)
        if not role_key:
            role_key = "researcher"

        # 检查是否是多模态生成任务
        multimodal_roles = ["text_to_image", "text_to_video", "image_to_video", "voice_synthesizer"]
        is_multimodal = role_key in multimodal_roles

        # 检查是否是视觉分析角色（需要多模态消息格式）
        vision_roles = ["image_analyst", "ocr_reader", "chart_reader", "ui_analyst", "image_describer", "visual_qa"]
        is_vision = role_key in vision_roles

        # 获取角色对应的模型配置
        from src.models.agent import get_model_config_for_role
        role_model_config = get_model_config_for_role(role_key)

        # 创建 agent 实例
        instance = state.create_agent_instance(role_key, step_name)
        instance["status"] = AgentStatus.RUNNING.value
        instance["model"] = role_model_config.get("model", "qwen3-max")
        step_agent_mapping[step_id] = instance["id"]

        # 绑定 agent 实例到当前任务
        state.bind_agent_to_task(instance["id"], task_id)

        # 初始化 agent 日志
        if instance["id"] not in state.agent_logs:
            state.agent_logs[instance["id"]] = []

        # 更新步骤状态为 running
        steps[step_id]["status"] = "running"
        steps[step_id]["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        steps[step_id]["agent_id"] = instance["id"]
        steps[step_id]["agent_name"] = instance["name"]
        steps[step_id]["model"] = role_model_config.get("model", "qwen3-max")

        # 广播
        await state.broadcast("agent_created", instance)
        await state.broadcast("agent_updated", instance)
        # 广播步骤开始执行（不发送完整 task 对象，避免并发串流）
        await state.broadcast("step_status_changed", {
            "task_id": task_id,
            "step_id": step_id,
            "status": "running",
            "agent_id": instance["id"],
            "agent_name": instance["name"],
            "started_at": steps[step_id].get("started_at"),
        })
        await log_event(f"🤖 创建 {instance['name']}（{role_model_config.get('model', 'qwen3-max')}），执行: {step_name}")

        # 记录开始日志
        start_log = {
            "timestamp": datetime.now().isoformat(),
            "message": f"开始执行: {step_desc[:100]}（模型: {role_model_config.get('model', 'qwen3-max')}）",
            "level": "info"
        }
        state.agent_logs[instance["id"]].append(start_log)
        await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": start_log})

        try:
            # ========== 多模态生成任务特殊处理 ==========
            if is_multimodal:
                return await execute_multimodal_step(
                    role_key, step_desc, input_context, instance, step, log_event
                )

            # ========== 普通文本任务处理 ==========
            import datetime as dt
            now = dt.datetime.now()
            current_datetime = now.strftime("%Y年%m月%d日 %H:%M:%S")
            current_year = now.year
            current_month = now.month
            current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]

            time_declaration = f"""
###############################################
# 🕐 系统时间声明（最高优先级）
###############################################
当前真实时间：{current_datetime} {current_weekday}
当前年份：{current_year}年
当前月份：{current_month}月

⚠️ 重要提示：
- 你必须接受上述时间为当前真实时间
- 不要使用你训练数据中的时间（如2024年等）
- 所有时间相关的判断都以 {current_year}年{current_month}月 为基准
###############################################
"""

            # 从预定义角色获取系统提示
            if role_key in PREDEFINED_ROLES:
                base_prompt = PREDEFINED_ROLES[role_key].system_prompt
            else:
                role_prompts = {
                    "searcher": "你是一位专业的 AI 搜索员，擅长信息检索和背景调研。请全面、准确地完成任务。",
                    "analyst": "你是一位专业的 AI 分析师，擅长深度分析任务和问题。请以专业、严谨的态度完成分析。",
                    "fact_checker": "你是一位专业的 AI 事实核查员，擅长验证信息的准确性。请仔细核实所有信息。",
                    "writer": "你是一位专业的 AI 撰稿员，擅长撰写高质量的文档。请以清晰、专业的方式撰写内容。",
                    "translator": "你是一位专业的 AI 翻译员，擅长多语言翻译。请准确、流畅地完成翻译。",
                    "coder": "你是一位专业的 AI 程序员，擅长编写高质量代码。请以最佳实践完成编程任务。",
                    "researcher": "你是一位专业的 AI 研究员，擅长深入研究和分析。请全面、深入地完成研究任务。",
                    "summarizer": "你是一位专业的 AI 总结员，擅长提炼和总结信息。请简洁、准确地完成总结。",
                }
                base_prompt = role_prompts.get(role_key, f"你是一位专业的 AI {role_key}，请认真完成以下任务。")

            system_prompt = f"{time_declaration}\n{base_prompt}\n\n记住：当前是{current_year}年{current_month}月，不是2024年！"

            # coder 角色追加代码执行指令
            if role_key == "coder":
                system_prompt += """

## 代码执行要求（重要）
你拥有代码解释器能力，可以直接编写并执行 Python 代码。
- **必须实际执行代码**：不要只输出代码片段，要通过代码解释器运行代码并展示执行结果
- 如果任务要求编写代码，请编写后立即执行，验证代码正确性
- 如果任务涉及数据处理、计算、文件操作等，请用代码解释器完成
- 输出中应包含代码和执行结果"""

            # 构建用户提示
            user_prompt = f"""## 你的任务
{step_desc}

## 预期产出
{step.get('expected_output', '完成任务并提供结果')}

## 输出质量要求
- 请**直接执行任务**，产出实际内容，不要生成"执行指令"或"任务计划"
- **内容丰富度**：输出不少于 800 字，覆盖多个维度和角度，深入分析而非泛泛而谈
- **数据支撑**：必须引用具体的数据、统计、案例或事实依据，标注数据来源
- **结构清晰**：使用 Markdown 格式（标题、列表、表格、加粗），让内容层次分明
- **专业深度**：使用专业术语，提供行业洞察和独到见解，展现分析深度
- **对比分析**：涉及多个对象时，用表格进行结构化对比
- 直接给出分析结果、研究内容、报告文本等实际产出
"""

            # 如果有文件内容，添加到提示中
            file_contents = metadata.get("file_contents", []) if metadata else []
            if file_contents:
                file_content_sections = []
                for fc in file_contents:
                    content_preview = fc.get("content", "")[:30000] if len(fc.get("content", "")) > 30000 else fc.get("content", "")
                    file_content_sections.append(f"""
### 文件: {fc.get('name', '未知文件')}
{content_preview}
""")
                file_content_text = "\n".join(file_content_sections)
                user_prompt = f"""## 📄 附件文件内容
以下是需要分析的文件内容，请基于这些内容完成任务：

{file_content_text}

{user_prompt}"""

            # 如果有上游输入，添加到提示中
            if input_context:
                user_prompt = f"""## 上游任务结果（作为你的输入参考）
{input_context}

{user_prompt}"""

            # 构建消息
            from src.qwen.models import Message, QwenConfig, QwenModel

            # 视觉分析角色：构建多模态消息（content 为 list 格式）
            if is_vision and input_context:
                import re
                import json as _json
                image_urls = []
                # 优先从 JSON 结构中提取 media_urls（仅图片类型）
                try:
                    ctx_data = _json.loads(input_context)
                    items = [ctx_data] if isinstance(ctx_data, dict) else (ctx_data if isinstance(ctx_data, list) else [])
                    for item in items:
                        if isinstance(item, dict):
                            media_type = item.get("type", "")
                            if media_type == "image":
                                image_urls.extend(item.get("media_urls", []))
                            # video/audio 类型不传给 VL API，回退到纯文本分析
                except (_json.JSONDecodeError, TypeError):
                    pass
                # 回退：正则提取图片 URL（排除视频/音频扩展名）
                if not image_urls:
                    image_urls = re.findall(r'(https?://[^\s\"\'\)\]]+\.(?:png|jpg|jpeg|gif|webp|bmp)(?:[^\s\"\'\)\]]*)?)', input_context)

                if image_urls:
                    # 构建 DashScope VL 多模态 content: [{"image": url}, ..., {"text": prompt}]
                    multimodal_content = []
                    for url in image_urls[:4]:  # 最多 4 张图
                        multimodal_content.append({"image": url})
                    multimodal_content.append({"text": f"{system_prompt}\n\n{user_prompt}"})
                    messages = [
                        Message(role="user", content=multimodal_content)
                    ]
                    await log_event(f"🖼️ 视觉分析模式: 从 JSON 提取到 {len(image_urls)} 张图片URL，使用 MultiModalConversation API")
                else:
                    messages = [
                        Message(role="system", content=system_prompt),
                        Message(role="user", content=user_prompt)
                    ]
            else:
                messages = [
                    Message(role="system", content=system_prompt),
                    Message(role="user", content=user_prompt)
                ]

            # 根据角色配置创建 QwenConfig
            model_name = role_model_config.get("model", "qwen3-max")

            # 视觉角色但没有图片时，回退到文本模型避免 VL 模型的 url error
            has_multimodal_content = any(isinstance(m.content, list) for m in messages)
            if is_vision and not has_multimodal_content:
                model_name = "qwen3-max"
                await log_event(f"📝 视觉角色无图片输入，回退到文本模型 {model_name}")

            model_enum = QwenModel.QWEN3_MAX
            for m in QwenModel:
                if m.value == model_name:
                    model_enum = m
                    break

            # coder/analyst 角色启用代码解释器，让模型能实际执行代码
            needs_code_interpreter = role_key in ("coder", "analyst")
            # 代码解释器仅 Qwen 原生模型支持；如果当前模型不支持，切换到 qwen3-max
            if needs_code_interpreter and not model_enum.is_qwen_native():
                model_enum = QwenModel.QWEN3_MAX
                await log_event(f"💻 {role_key} 需要代码解释器，切换模型到 {model_enum.value}")
            enable_code_interpreter = needs_code_interpreter and model_enum.is_qwen_native()

            config = QwenConfig(
                model=model_enum,
                temperature=role_model_config.get("temperature", 0.3),
                enable_thinking=(role_model_config.get("enable_thinking", False) or enable_code_interpreter) if not has_multimodal_content else False,
                enable_search=role_key in ("searcher", "researcher", "fact_checker") and not is_vision,
                enable_code_interpreter=enable_code_interpreter,
                max_tokens=16384,
                timeout=300.0,
            )

            if enable_code_interpreter:
                await log_event(f"💻 代码解释器已启用，程序员可以执行代码")

            # 流式调用 Qwen
            result = ""
            state.agent_streams[instance["id"]] = ""

            async for chunk in state.swarm.qwen_client.chat_stream(messages, config=config):
                # 检查任务是否已被取消
                if task_id in state.cancelled_tasks or task_id not in state.tasks:
                    return False, None, "任务已被取消"
                result += chunk
                state.agent_streams[instance["id"]] = result
                await state.broadcast("agent_stream", {
                    "agent_id": instance["id"],
                    "task_id": task_id,
                    "content": chunk,
                    "full_content": result
                })

            # 记录完成日志
            complete_log = {
                "timestamp": datetime.now().isoformat(),
                "message": "任务执行成功",
                "level": "success"
            }
            state.agent_logs[instance["id"]].append(complete_log)
            await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": complete_log})

            # 清理结果中的 thinking 标签
            result = clean_thinking_tags(result)
            return True, result, None

        except Exception as e:
            error_msg = str(e)
            error_log = {
                "timestamp": datetime.now().isoformat(),
                "message": f"任务执行失败: {error_msg}",
                "level": "error"
            }
            state.agent_logs[instance["id"]].append(error_log)
            await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": error_log})

            return False, None, error_msg

        finally:
            # 更新 agent 状态
            instance["status"] = AgentStatus.IDLE.value
            await state.broadcast("agent_updated", instance)

            # 更新基础模板统计
            base_agent_id = f"agent_{role_key}"
            if base_agent_id in state.agents:
                state.agents[base_agent_id]["stats"]["tasks_completed"] += 1
                await state.broadcast("agent_updated", state.agents[base_agent_id])

    # ========== agent_factory: WaveExecutor 调用的工厂函数 ==========
    async def agent_factory(subtask: SubTask):
        """
        WaveExecutor 的工厂函数：为每个子任务创建 agent 并执行
        返回执行结果字符串，失败时抛出异常
        """
        # 检查任务是否已被取消
        if task_id in state.cancelled_tasks or task_id not in state.tasks:
            raise Exception("任务已被取消")

        step_id = subtask.id
        step = steps.get(step_id, {})
        step_name = step.get("name", "执行任务")
        deps = list(subtask.dependencies)

        # 收集上游依赖的输出作为输入上下文
        input_parts = []
        for dep_id in deps:
            if dep_id in step_results:
                dep_step = steps.get(dep_id, {})
                dep_name = dep_step.get("name", dep_id)
                dep_output = step_results[dep_id]
                # 尝试解析为 JSON，保持结构化
                try:
                    parsed = json.loads(dep_output)
                    if isinstance(parsed, dict):
                        parsed["_source_step"] = dep_name
                    input_parts.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    # 纯文本结果，包装为 JSON
                    input_parts.append({
                        "_source_step": dep_name,
                        "type": "text",
                        "text_content": dep_output[:6000] if dep_output else ""
                    })

        # 构建 input_context：多模态/生成角色用 JSON，文本角色用可读文本
        multimodal_consumer_roles = ["text_to_image", "text_to_video", "image_to_video",
                                     "voice_synthesizer", "image_analyst", "ocr_reader",
                                     "chart_reader", "ui_analyst", "image_describer", "visual_qa"]
        step_role = map_role_hint_to_key(step.get("agent_type", "")) or "researcher"

        if step_role in multimodal_consumer_roles and input_parts:
            # JSON 格式传递，便于下游精确解析 media_urls 等字段
            if len(input_parts) == 1:
                input_context = json.dumps(input_parts[0], ensure_ascii=False)
            else:
                input_context = json.dumps(input_parts, ensure_ascii=False)
        elif input_parts:
            # 文本角色：转为可读文本
            text_parts = []
            for item in input_parts:
                src = item.get("_source_step", "上游步骤")
                if item.get("type") in ("image", "video", "audio"):
                    urls = item.get("media_urls", [])
                    urls_str = "\n".join(urls) if urls else "无"
                    text_parts.append(f"### {src} 的结果:\n类型: {item['type']}\n媒体URL:\n{urls_str}\n{item.get('text_content', '')}")
                else:
                    text_parts.append(f"### {src} 的结果:\n{item.get('text_content', str(item))[:6000]}")
            input_context = "\n\n".join(text_parts)
        else:
            input_context = ""

        # 执行步骤（复用 execute_single_step），支持瞬态错误重试
        max_step_retries = 3
        success, output, error = False, None, None

        for step_attempt in range(max_step_retries):
            # 检查任务是否已被取消
            if task_id in state.cancelled_tasks or task_id not in state.tasks:
                raise Exception("任务已被取消")
            success, output, error = await execute_single_step(step, input_context)
            if success:
                break
            # 判断是否为可重试的瞬态错误（限流、连接重置等）
            if error and step_attempt < max_step_retries - 1:
                err_str = str(error)
                is_transient = any(kw in err_str for kw in [
                    "Throttling", "RateQuota", "rate limit",
                    "Connection", "reset", "InternalError",
                    "ServiceUnavailable", "502", "503",
                ])
                if is_transient:
                    wait_secs = min(10 * (2 ** step_attempt), 60)
                    await log_event(f"⏳ 步骤 {step_name} 遇到瞬态错误，{wait_secs}秒后重试 ({step_attempt + 1}/{max_step_retries}): {err_str[:80]}")
                    await asyncio.sleep(wait_secs)
                    continue
            # 非瞬态错误，不重试
            break

        # ========== 质量门控评审 ==========
        if success and quality_gate_reviewer:
            try:
                review_result = await quality_gate_reviewer.review_step(
                    step, output, step_results, attempt=1
                )
                # 记录评审结果
                step.setdefault("review_history", [])
                step["review_history"].append(review_result.to_dict())

                # 质量门控重试逻辑
                qg_retry_count = 0
                max_qg_retries = getattr(supervisor_config, 'max_retry_on_failure', 2)
                while (review_result.action == "retry"
                       and qg_retry_count < max_qg_retries):
                    qg_retry_count += 1
                    await log_event(f"🔄 质量门控要求重试 ({qg_retry_count}/{max_qg_retries}): {review_result.reason[:80]}")
                    success, output, error = await execute_single_step(step, input_context)
                    if not success:
                        break
                    review_result = await quality_gate_reviewer.review_step(
                        step, output, step_results, attempt=qg_retry_count + 1
                    )
                    step["review_history"].append(review_result.to_dict())

                # 重试耗尽仍未达标，标记 accepted_with_warning
                if (review_result.action == "retry"
                        and qg_retry_count >= max_qg_retries):
                    review_result = type(review_result)(
                        step_id=review_result.step_id,
                        quality_score=review_result.quality_score,
                        action="accepted_with_warning",
                        reason=f"重试 {max_qg_retries} 次后仍未达标，接受当前结果",
                        adjustments=review_result.adjustments,
                        attempt=review_result.attempt,
                    )
                    step["review_history"].append(review_result.to_dict())
                    await log_event(f"⚠️ 质量门控: 步骤 {step_name} 重试耗尽，接受当前结果")

                # 应用动态调整
                if review_result.adjustments:
                    async def broadcast_callback(event_type, data):
                        data["task_id"] = task_id
                        await state.broadcast(event_type, data)
                    await quality_gate_reviewer.apply_adjustments(
                        review_result.adjustments,
                        trigger_step_id=step_id,
                        broadcast_callback=broadcast_callback,
                    )
                    await log_event(f"🔧 质量门控触发动态调整: {len(review_result.adjustments)} 项")

                # 广播 step_reviewed 事件
                await state.broadcast("step_reviewed", {
                    "task_id": task_id,
                    "step_id": step_id,
                    "quality_score": review_result.quality_score,
                    "action": review_result.action,
                    "reason": review_result.reason,
                    "attempt": review_result.attempt,
                })

                score_emoji = "✅" if review_result.quality_score >= 6.0 else "⚠️"
                await log_event(f"{score_emoji} 质量评审: {step_name} 得分 {review_result.quality_score}/10 - {review_result.reason[:60]}")

            except Exception as qg_err:
                # 评审异常时优雅降级，不影响步骤结果
                import logging as _logging
                _logging.getLogger(__name__).error(f"质量门控异常: {qg_err}")
                await log_event(f"⚠️ 质量门控评审异常，已跳过: {str(qg_err)[:60]}")

        # 更新步骤状态
        if success:
            steps[step_id]["status"] = "completed"
            # 存储 output_data：JSON 输出保留结构，文本截断
            try:
                parsed_output = json.loads(output)
                # JSON 输出：保留完整结构但截断 text_content
                if isinstance(parsed_output, dict) and "text_content" in parsed_output:
                    summary = dict(parsed_output)
                    summary["text_content"] = summary["text_content"][:300]
                    steps[step_id]["output_data"] = json.dumps(summary, ensure_ascii=False)
                else:
                    steps[step_id]["output_data"] = output[:500] if output else None
            except (json.JSONDecodeError, TypeError):
                steps[step_id]["output_data"] = output[:500] if output else None
            step_results[step_id] = output
            await log_event(f"✅ 步骤完成: {step_name}")
        else:
            steps[step_id]["status"] = "failed"
            steps[step_id]["error"] = error
            failed_steps.add(step_id)
            await log_event(f"❌ 步骤失败: {step_name} - {error}")

        steps[step_id]["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        steps[step_id]["logs"] = state.agent_logs.get(step_agent_mapping.get(step_id), []).copy()

        # 存储子任务结果
        state.subtask_results[step_id] = {
            "status": steps[step_id]["status"],
            "agent_id": step_agent_mapping.get(step_id),
            "agent_name": steps[step_id].get("agent_name"),
            "output_data": steps[step_id].get("output_data"),
            "error": steps[step_id].get("error"),
            "logs": steps[step_id].get("logs", []),
        }

        # 广播步骤状态变化（包含完整步骤数据，避免前端需要额外轮询）
        await state.broadcast("step_status_changed", {
            "task_id": task_id,
            "step_id": step_id,
            "status": steps[step_id]["status"],
            "output_data": steps[step_id].get("output_data"),
            "error": steps[step_id].get("error"),
            "agent_id": step_agent_mapping.get(step_id),
            "agent_name": steps[step_id].get("agent_name"),
            "started_at": steps[step_id].get("started_at"),
            "completed_at": steps[step_id].get("completed_at"),
            "logs": steps[step_id].get("logs", []),
        })

        # 释放 agent 实例
        agent_id = step_agent_mapping.get(step_id)
        if agent_id and agent_id in state.active_agents:
            await asyncio.sleep(0.3)
            state.release_agent_instance(agent_id)
            await state.broadcast("agent_removed", {"id": agent_id})

        # 更新进度（使用深拷贝避免并发修改问题）
        completed_count = sum(1 for s in steps.values() if s.get("status") == "completed")
        total_count = len(steps)
        task["plan"]["execution_flow"]["progress"] = {
            "total": total_count,
            "completed": completed_count,
            "running": sum(1 for s in steps.values() if s.get("status") == "running"),
            "failed": len(failed_steps),
            "progress_percent": int(completed_count / total_count * 100) if total_count > 0 else 0,
        }
        # 仅广播进度更新，不发送完整 task 对象（避免并发步骤的 output_data 串流）
        await state.broadcast("task_progress", {
            "task_id": task_id,
            "progress": task["plan"]["execution_flow"]["progress"],
            "status": task.get("status"),
        })

        if not success:
            raise Exception(error or f"步骤 {step_name} 执行失败")

        return output

    # ========== 通过 WaveExecutor 执行 ==========
    wave_executor = WaveExecutor()
    await log_event("⚡ WaveExecutor 启动，事件驱动动态波次执行...")

    wave_result = await wave_executor.execute(task_board, agent_factory)

    # 记录波次统计
    wave_stats = await wave_executor.get_wave_statistics()
    await log_event(f"📈 波次执行完成: {wave_result.total_waves} 个波次, "
                    f"完成 {wave_result.completed_tasks}/{wave_result.total_tasks}, "
                    f"失败 {wave_result.failed_tasks}, 阻塞 {wave_result.blocked_tasks}")
    for ws in wave_stats:
        await log_event(f"   波次 {ws.wave_number + 1}: {ws.task_count} 个任务, "
                        f"并行度 {ws.parallelism}, 完成 {ws.completed_tasks}, 失败 {ws.failed_tasks}")

    # 记录失败和阻塞的步骤详情
    if wave_result.failed_tasks > 0 or wave_result.blocked_tasks > 0:
        for sid, s in steps.items():
            if s.get("status") == "failed":
                await log_event(f"⚠️ 失败步骤: {s.get('name', sid)} - {s.get('error', '未知错误')}", "warning")
            elif s.get("status") in ("waiting", "blocked"):
                await log_event(f"⏭️ 跳过步骤: {s.get('name', sid)}（依赖的步骤失败）", "warning")

    # ========== 阶段 5: 结果聚合 ==========
    await update_stage(stage_offset + 3, "completed", "所有步骤执行完成")
    task["status"] = TaskStatus.AGGREGATING.value
    await update_stage(stage_offset + 4, "running")
    await log_event("📊 正在聚合执行结果...")

    # 聚合所有步骤的结果 — 全量传递，不做截断
    # 解析 JSON 输出，提取媒体 URL 和文本内容
    import json as _json
    all_media_urls = []
    text_sections = []
    for sid, result in step_results.items():
        step_name = steps[sid].get('name', sid)
        try:
            parsed = _json.loads(result)
            if isinstance(parsed, dict):
                media_urls = parsed.get("media_urls", [])
                all_media_urls.extend(media_urls)
                text_content = parsed.get("text_content", "")
                media_type = parsed.get("type", "text")
                if media_urls:
                    urls_md = "\n".join([f"- {url}" for url in media_urls])
                    text_sections.append(f"## {step_name}\n类型: {media_type}\n媒体URL:\n{urls_md}\n{text_content}")
                else:
                    text_sections.append(f"## {step_name}\n{text_content or result}")
            else:
                text_sections.append(f"## {step_name}\n{result}")
        except (_json.JSONDecodeError, TypeError):
            text_sections.append(f"## {step_name}\n{result}")

    aggregated_result = "\n\n".join(text_sections)

    # ========== 通过 OutputPipeline 生成最终产物 ==========
    output_type_str = task.get("output_type", "report")
    try:
        output_type = OutputType(output_type_str)
    except ValueError:
        await log_event(f"⚠️ 未知输出类型 '{output_type_str}'，回退到 report", "warning")
        output_type = OutputType.REPORT

    # 对于 image/video 类型，将媒体 URL 放在结果最前面
    pipeline_output_type = output_type
    if output_type in (OutputType.IMAGE, OutputType.VIDEO):
        if all_media_urls:
            await log_event(f"🎨 从 JSON 输出中提取到 {len(all_media_urls)} 个媒体URL")

        # ========== VIDEO 类型：尝试合并多段视频 ==========
        if output_type == OutputType.VIDEO and len(all_media_urls) > 1:
            await log_event(f"🎬 检测到 {len(all_media_urls)} 段视频，尝试合并...")
            merged_url = await _merge_video_segments(all_media_urls, task_id, log_event)
            if merged_url:
                await log_event(f"✅ 视频合并成功: {merged_url}")
                task["merged_video_url"] = merged_url
                task["video_segments"] = all_media_urls
            else:
                await log_event(f"⚠️ 视频合并失败，保留分段视频", "warning")

        # ========== 构建媒体展示结果（不走 writer 报告流程）==========
        if all_media_urls:
            media_result_parts = []
            if output_type == OutputType.IMAGE:
                media_result_parts.append("# 🎨 图像生成结果\n")
                for i, url in enumerate(all_media_urls):
                    media_result_parts.append(f"![生成图片{i+1}]({url})\n")
            elif output_type == OutputType.VIDEO:
                media_result_parts.append("# 🎬 视频生成结果\n")
                merged = task.get("merged_video_url")
                if merged:
                    media_result_parts.append(f"**合并视频**:\n{merged}\n")
                for i, url in enumerate(all_media_urls):
                    media_result_parts.append(f"**视频片段{i+1}**:\n{url}\n")

            # 附加文本摘要（非媒体步骤的输出）
            text_only_sections = []
            for sid, result in step_results.items():
                step_name = steps[sid].get('name', sid)
                try:
                    parsed = _json.loads(result)
                    if isinstance(parsed, dict) and parsed.get("type") in ("image", "video"):
                        continue  # 跳过媒体步骤，已在上面展示
                    text_content = parsed.get("text_content", result) if isinstance(parsed, dict) else result
                except (_json.JSONDecodeError, TypeError):
                    text_content = result
                if text_content and len(str(text_content).strip()) > 0:
                    text_only_sections.append(f"## {step_name}\n{str(text_content)[:2000]}")

            if text_only_sections:
                media_result_parts.append("\n---\n# 📝 相关分析\n")
                media_result_parts.extend(text_only_sections)

            task["result"] = "\n".join(media_result_parts)
            task["media_urls"] = all_media_urls

            # 通过 OutputPipeline 存储产物（使用 REPORT handler 保存完整结果）
            registry = OutputTypeRegistry()
            register_all_handlers(registry)
            storage = ArtifactStorage()
            pipeline = OutputPipeline(registry, storage)
            pipeline_config = {
                "task_id": task_id,
                "original_task": content,
                "execution_plan": metadata.get("supervisor_plan", {}) if metadata else {},
            }
            try:
                artifacts = await pipeline.execute(
                    task_id=task_id,
                    aggregated_result=task["result"],
                    output_type=OutputType.REPORT,
                    config=pipeline_config,
                )
                task["artifacts"] = [a.to_dict() for a in artifacts]
            except Exception as store_err:
                await log_event(f"⚠️ 产物存储失败（不影响结果展示）: {str(store_err)[:80]}", "warning")

            await log_event(f"✅ {output_type.value} 任务完成，生成 {len(all_media_urls)} 个媒体文件!", "success")
            # 跳过后续的 REPORT/其他类型处理
            pipeline_output_type = None
        else:
            # 没有媒体 URL，回退到 REPORT 模式
            await log_event(f"⚠️ {output_type.value} 任务未生成媒体文件，回退到报告模式", "warning")
            pipeline_output_type = OutputType.REPORT

    # ========== REPORT 类型：由撰稿员 LLM 综合生成真正的报告 ==========
    if pipeline_output_type is not None and pipeline_output_type == OutputType.REPORT:
        await log_event("📝 正在由撰稿员综合各阶段结果，生成结构化报告...")
        writer_instance = state.create_agent_instance("writer", "生成最终报告")
        writer_instance["status"] = AgentStatus.RUNNING.value
        state.bind_agent_to_task(writer_instance["id"], task_id)
        await state.broadcast("agent_created", writer_instance)
        await state.broadcast("agent_updated", writer_instance)
        try:
            final_report = await generate_final_report(
                task_id=task_id,
                original_task=content,
                execution_result=aggregated_result,
                execution_plan=metadata.get("supervisor_plan", {}) if metadata else {},
                log_event=log_event,
                writer_id=writer_instance["id"]
            )
            task["final_report"] = final_report
            task["result"] = final_report

            # 通过 OutputPipeline 存储报告产物（用已生成的报告内容替代原始聚合文本）
            registry = OutputTypeRegistry()
            register_all_handlers(registry)
            storage = ArtifactStorage()
            pipeline = OutputPipeline(registry, storage)

            pipeline_config = {
                "task_id": task_id,
                "original_task": content,
                "execution_plan": metadata.get("supervisor_plan", {}) if metadata else {},
            }

            try:
                artifacts = await pipeline.execute(
                    task_id=task_id,
                    aggregated_result=final_report,
                    output_type=OutputType.REPORT,
                    config=pipeline_config,
                )
                task["artifacts"] = [a.to_dict() for a in artifacts]
            except Exception as store_err:
                await log_event(f"⚠️ 报告产物存储失败（不影响报告内容）: {str(store_err)[:80]}", "warning")

            await log_event("✅ 报告生成完成!", "success")
        except Exception as e:
            await log_event(f"⚠️ 撰稿员报告生成失败，使用聚合结果: {str(e)}", "warning")
            task["final_report"] = aggregated_result
            task["result"] = aggregated_result
        finally:
            writer_instance["status"] = AgentStatus.IDLE.value
            await state.broadcast("agent_updated", writer_instance)
            await asyncio.sleep(0.3)
            state.release_agent_instance(writer_instance["id"])
            await state.broadcast("agent_removed", {"id": writer_instance["id"]})

    # ========== 非 REPORT 类型：通过 OutputPipeline 直接生成 ==========
    elif pipeline_output_type is not None:
        await log_event(f"📝 正在通过输出流水线生成 {pipeline_output_type.value} 类型产物...")

        async def pipeline_progress_callback(stage: str, detail: str):
            await state.broadcast("output_progress", {
                "task_id": task_id,
                "stage": stage,
                "detail": detail,
                "output_type": pipeline_output_type.value,
            })
            await log_event(f"🔄 [{stage}] {detail}")

        registry = OutputTypeRegistry()
        register_all_handlers(registry)
        storage = ArtifactStorage()
        pipeline = OutputPipeline(registry, storage)

        pipeline_config = {
            "task_id": task_id,
            "original_task": content,
            "execution_plan": metadata.get("supervisor_plan", {}) if metadata else {},
        }

        try:
            artifacts = await pipeline.execute(
                task_id=task_id,
                aggregated_result=aggregated_result,
                output_type=pipeline_output_type,
                config=pipeline_config,
                progress_callback=pipeline_progress_callback,
            )

            task["artifacts"] = [a.to_dict() for a in artifacts]
            valid_count = sum(1 for a in artifacts if a.validation_status == "valid")
            task["result"] = f"生成了 {len(artifacts)} 个产物（{valid_count} 个验证通过）"

            await log_event("✅ 输出产物生成完成!", "success")

        except Exception as e:
            await log_event(f"⚠️ 输出流水线失败: {str(e)}", "warning")
            task["result"] = clean_thinking_tags(aggregated_result) if aggregated_result else ""

    # 记录波次执行元数据
    task["wave_execution"] = wave_result.to_dict()

    await update_stage(stage_offset + 4, "completed", "结果聚合完成")

    task["status"] = TaskStatus.COMPLETED.value
    task["completed_at"] = datetime.now().isoformat()
    task["progress"]["percentage"] = 100

    await state.broadcast("task_completed", task)
    await log_event("🎉 任务执行完成!", "success")
