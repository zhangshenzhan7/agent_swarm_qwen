"""AgentSwarm 自动分解执行流程"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List

from src import TaskStatus, AgentStatus, ExecutionFlow
from src.models.enums import OutputType
from src.output_registry import OutputTypeRegistry
from src.output_pipeline import OutputPipeline
from src.artifact_storage import ArtifactStorage
from src.handlers import register_all_handlers
from state import state
from utils import clean_thinking_tags
from execution.report import generate_final_report
from execution.helpers import analyze_dependency_layers, map_role_hint_to_key


async def execute_task_with_swarm(task_id: str, content: str, metadata: Optional[Dict] = None, start_stage: int = 0, suggested_agents: Optional[List[str]] = None, execution_flow: Optional[ExecutionFlow] = None):
    """使用 AgentSwarm 真实执行任务，支持动态执行流程"""
    task = state.tasks[task_id]
    suggested_agents = suggested_agents or []

    async def log_event(message: str, level: str = "info"):
        """记录执行日志并广播 - 清理 thinking 标签"""
        clean_message = clean_thinking_tags(message)
        if not clean_message:
            return
        # 任务可能已被用户删除
        if task_id not in state.execution_logs:
            return
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "message": clean_message,
            "level": level
        }
        state.execution_logs[task_id].append(log_entry)
        await state.broadcast("task_log", {"task_id": task_id, "log": log_entry})

    async def update_stage(idx: int, status: str, details: str = None):
        """更新执行阶段状态"""
        # 任务可能已被用户删除
        if task_id not in state.tasks:
            return
        task["stages"][idx]["status"] = status
        if status == "running":
            task["stages"][idx]["started_at"] = datetime.now().isoformat()
        elif status in ["completed", "failed"]:
            task["stages"][idx]["completed_at"] = datetime.now().isoformat()
        if details:
            task["stages"][idx]["details"] = details

        # 计算进度：completed 算 100%，running 算 50%
        total = len(task["stages"])
        progress = 0
        for s in task["stages"]:
            if s["status"] == "completed":
                progress += 100
            elif s["status"] == "running":
                progress += 50
        task["progress"]["percentage"] = min(int(progress / total), 99) if total > 0 else 0
        task["progress"]["current_stage"] = task["stages"][idx]["name"]
        await state.broadcast("task_updated", task)

    async def update_agent_status(role_key: str, running: bool, current_task: str = None):
        """更新 AI 员工状态"""
        agent_id = f"agent_{role_key}"
        if agent_id in state.agents:
            state.agents[agent_id]["status"] = AgentStatus.RUNNING.value if running else AgentStatus.IDLE.value
            state.agents[agent_id]["current_task"] = current_task[:50] + "..." if current_task else None
            if not running and current_task:
                state.agents[agent_id]["stats"]["tasks_completed"] += 1
            await state.broadcast("agent_updated", state.agents[agent_id])

    try:
        await log_event(f"📋 开始执行任务: {content}")

        # 阶段索引偏移（因为阶段0是主管决策）
        stage_offset = start_stage

        # 检查是否有 Supervisor 规划的执行流程
        has_execution_flow = task.get("plan") and task["plan"].get("execution_flow") and task["plan"]["execution_flow"].get("steps")

        if has_execution_flow:
            # ========== 使用 Supervisor 规划的步骤执行 ==========
            from execution.planner import execute_with_supervisor_plan
            await execute_with_supervisor_plan(task_id, task, content, metadata, log_event, update_stage, stage_offset)
        else:
            # ========== 使用 AgentSwarm 自动分解执行 ==========
            # ========== 阶段 1: 任务分析 ==========
            task["status"] = TaskStatus.ANALYZING.value
            await update_stage(stage_offset, "running")
            await log_event("🔍 正在分析任务复杂度...")

            # 提交任务到 AgentSwarm
            swarm_task = await state.swarm.submit_task(content, metadata)
            state.swarm_tasks[task_id] = swarm_task

            complexity = swarm_task.complexity_score
            await update_stage(stage_offset, "completed", f"复杂度评分: {complexity:.1f}")
            await log_event(f"✅ 任务分析完成，复杂度: {complexity:.1f}")

            # ========== 阶段 2-5: 执行任务并监控进度 ==========
            task["status"] = TaskStatus.DECOMPOSING.value
            await update_stage(stage_offset + 1, "running")
            await log_event("🔧 正在分解任务...")

            # 启动进度监控
            from execution.monitor import monitor_execution_progress
            monitor_task = asyncio.create_task(
                monitor_execution_progress(task_id, swarm_task.id, log_event, update_stage, update_agent_status, stage_offset, suggested_agents)
            )

            # 执行任务
            result = await state.swarm.execute_task(swarm_task)

            # 停止监控
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

            # ========== 完成处理 ==========
            if result.success:
                # 确保所有阶段都标记为完成
                for i in range(len(task["stages"])):
                    if task["stages"][i]["status"] != "completed" and task["stages"][i]["status"] != "skipped":
                        await update_stage(i, "completed")

                # ========== 通过 OutputPipeline 生成最终产物 ==========
                # 从任务配置中获取 output_type，默认 REPORT 以保持向后兼容
                output_type_str = task.get("output_type", "report")
                try:
                    output_type = OutputType(output_type_str)
                except ValueError:
                    await log_event(f"⚠️ 未知输出类型 '{output_type_str}'，回退到 report", "warning")
                    output_type = OutputType.REPORT

                # 对于 image/video 类型，检查是否有媒体 URL
                pipeline_output_type = output_type
                raw_output = result.output

                # 尝试从结果中提取媒体 URL
                all_media_urls = []
                if isinstance(raw_output, str):
                    import json as _json
                    import re as _re
                    try:
                        parsed = _json.loads(raw_output)
                        if isinstance(parsed, dict):
                            all_media_urls.extend(parsed.get("media_urls", []))
                        elif isinstance(parsed, list):
                            for item in parsed:
                                if isinstance(item, dict):
                                    all_media_urls.extend(item.get("media_urls", []))
                    except (_json.JSONDecodeError, TypeError):
                        # 回退：正则提取 URL
                        all_media_urls = _re.findall(r'(https?://[^\s\"\'\)\]]+\.(?:png|jpg|jpeg|gif|webp|bmp|mp4|webm)(?:[^\s\"\'\)\]]*)?)', raw_output)

                if output_type in (OutputType.IMAGE, OutputType.VIDEO) and all_media_urls:
                    # 有媒体 URL，构建媒体展示结果
                    media_result_parts = []
                    if output_type == OutputType.IMAGE:
                        media_result_parts.append("# 🎨 图像生成结果\n")
                        for idx, url in enumerate(all_media_urls):
                            media_result_parts.append(f"![生成图片{idx+1}]({url})\n")
                    elif output_type == OutputType.VIDEO:
                        media_result_parts.append("# 🎬 视频生成结果\n")
                        for idx, url in enumerate(all_media_urls):
                            media_result_parts.append(f"**视频片段{idx+1}**:\n{url}\n")

                    task["result"] = "\n".join(media_result_parts)
                    task["media_urls"] = all_media_urls
                    await log_event(f"✅ {output_type.value} 任务完成，生成 {len(all_media_urls)} 个媒体文件!", "success")
                    pipeline_output_type = None  # 跳过后续 pipeline 处理
                elif output_type in (OutputType.IMAGE, OutputType.VIDEO):
                    # 没有媒体 URL，回退到 REPORT
                    await log_event(f"⚠️ {output_type.value} 任务未生成媒体文件，回退到报告模式", "warning")
                    pipeline_output_type = OutputType.REPORT

                if pipeline_output_type is not None:
                    await log_event(f"📝 正在通过输出流水线生成 {pipeline_output_type.value} 类型产物...")

                    # 构建 WebSocket 进度回调
                    async def pipeline_progress_callback(stage: str, detail: str):
                        """通过 WebSocket broadcast 推送输出生成进度"""
                        await state.broadcast("output_progress", {
                            "task_id": task_id,
                            "stage": stage,
                            "detail": detail,
                            "output_type": pipeline_output_type.value,
                        })
                        await log_event(f"🔄 [{stage}] {detail}")

                    # 初始化 OutputPipeline 组件
                    registry = OutputTypeRegistry()
                    register_all_handlers(registry)
                    storage = ArtifactStorage()
                    pipeline = OutputPipeline(registry, storage)

                    # 准备流水线配置
                    pipeline_config = {
                        "task_id": task_id,
                        "original_task": content,
                        "execution_plan": metadata.get("supervisor_plan", {}) if metadata else {},
                    }

                    try:
                        artifacts = await pipeline.execute(
                            task_id=task_id,
                            aggregated_result=raw_output,
                            output_type=pipeline_output_type,
                            config=pipeline_config,
                            progress_callback=pipeline_progress_callback,
                        )

                        # 存储产物元数据到任务
                        task["artifacts"] = [a.to_dict() for a in artifacts]

                        # 对于 report 类型（含 image/video 回退），保持向后兼容
                        if pipeline_output_type == OutputType.REPORT and artifacts:
                            report_content = artifacts[0].content if isinstance(artifacts[0].content, str) else ""
                            task["final_report"] = report_content
                            task["result"] = report_content
                        else:
                            # 非 report 类型，result 存储产物摘要
                            valid_count = sum(1 for a in artifacts if a.validation_status == "valid")
                            task["result"] = f"生成了 {len(artifacts)} 个产物（{valid_count} 个验证通过）"

                        await log_event("✅ 输出产物生成完成!", "success")

                    except Exception as e:
                        await log_event(f"⚠️ 输出流水线失败: {str(e)}", "warning")
                        # 回退：尝试直接调用 generate_final_report
                        if pipeline_output_type == OutputType.REPORT or output_type == OutputType.REPORT:
                            await log_event("📝 回退到直接生成报告...")
                            writer_instance = state.create_agent_instance("writer", "生成最终报告")
                            writer_instance["status"] = AgentStatus.RUNNING.value
                            await state.broadcast("agent_created", writer_instance)
                            await state.broadcast("agent_updated", writer_instance)
                            try:
                                final_report = await generate_final_report(
                                    task_id=task_id,
                                    original_task=content,
                                    execution_result=raw_output,
                                    execution_plan=metadata.get("supervisor_plan", {}) if metadata else {},
                                    log_event=log_event,
                                    writer_id=writer_instance["id"]
                                )
                                task["final_report"] = final_report
                                task["result"] = final_report
                                await log_event("✅ 最终报告生成完成!", "success")
                            except Exception as fallback_err:
                                await log_event(f"⚠️ 报告生成失败，使用原始结果: {str(fallback_err)}", "warning")
                                task["result"] = clean_thinking_tags(raw_output) if raw_output else ""
                            finally:
                                writer_instance["status"] = AgentStatus.IDLE.value
                                await state.broadcast("agent_updated", writer_instance)
                                await asyncio.sleep(0.3)
                                state.release_agent_instance(writer_instance["id"])
                                await state.broadcast("agent_removed", {"id": writer_instance["id"]})
                        else:
                            task["result"] = clean_thinking_tags(raw_output) if raw_output else ""

                task["status"] = TaskStatus.COMPLETED.value
                task["completed_at"] = datetime.now().isoformat()
                task["progress"]["percentage"] = 100

                await state.broadcast("task_completed", task)
                await log_event("🎉 任务执行完成!", "success")
            else:
                raise Exception(result.error or "任务执行失败")

    except asyncio.CancelledError:
        # 任务被取消，静默退出，让上层处理
        raise
    except Exception as e:
        error_msg = str(e)
        if task_id in state.tasks:
            task["status"] = TaskStatus.FAILED.value
            task["error"] = error_msg
            task["completed_at"] = datetime.now().isoformat()

            # 标记当前阶段失败
            for i, stage in enumerate(task["stages"]):
                if stage["status"] == "running":
                    await update_stage(i, "failed", error_msg[:50])
                    break

            await state.broadcast("task_failed", {"task_id": task_id, "error": error_msg})
        await log_event(f"❌ 任务执行失败: {error_msg}", "error")

    finally:
        # 清理沙箱代码解释器资源（每次任务执行完毕后销毁沙箱）
        try:
            from src.tools import cleanup_sandbox
            await cleanup_sandbox()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"任务结束后沙箱清理失败: {e}")
        # 清理浏览器沙箱资源
        try:
            from src.tools import cleanup_browser
            await cleanup_browser()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"任务结束后浏览器沙箱清理失败: {e}")

        # 释放所有基础 agent
        for agent_id in state.agents:
            if state.agents[agent_id]["status"] == AgentStatus.RUNNING.value:
                state.agents[agent_id]["status"] = AgentStatus.IDLE.value
                state.agents[agent_id]["current_task"] = None
                await state.broadcast("agent_updated", state.agents[agent_id])

        # 释放所有动态创建的 agent 实例
        for instance_id in list(state.active_agents.keys()):
            agent = state.active_agents[instance_id]
            if agent.get("status") == AgentStatus.RUNNING.value:
                agent["status"] = AgentStatus.IDLE.value
                await state.broadcast("agent_updated", agent)
            state.release_agent_instance(instance_id)
            await state.broadcast("agent_removed", {"id": instance_id})

        # 清理 swarm task 引用
        if task_id in state.swarm_tasks:
            del state.swarm_tasks[task_id]
