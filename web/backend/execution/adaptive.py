"""自适应编排任务执行"""

import asyncio
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

from src import (
    TaskStatus,
    AgentStatus,
    AdaptiveOrchestrator,
    OrchestrationConfig,
    TaskNode,
)
from state import state
from utils import clean_thinking_tags
from execution.report import generate_final_report


async def execute_adaptive_task(task_id: str, content: str, metadata: Optional[Dict] = None):
    """使用自适应编排器执行任务"""
    task = state.tasks[task_id]

    async def log_event(message: str, level: str = "info"):
        """记录执行日志"""
        clean_message = clean_thinking_tags(message)
        if not clean_message:
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
        task["stages"][idx]["status"] = status
        if details:
            task["stages"][idx]["details"] = details

        completed = sum(1 for s in task["stages"] if s["status"] == "completed")
        task["progress"]["percentage"] = int(completed / len(task["stages"]) * 100)
        task["progress"]["current_stage"] = task["stages"][idx]["name"]
        await state.broadcast("task_updated", task)

    try:
        await log_event(f"🚀 启动自适应编排模式: {content[:50]}...")

        if not state.swarm:
            raise Exception("AgentSwarm 未初始化")

        # ========== 阶段 1: 自适应规划 ==========
        task["status"] = TaskStatus.ANALYZING.value
        await update_stage(0, "running")
        await log_event("📊 自适应规划中...")

        # 创建自适应编排器
        orchestrator = AdaptiveOrchestrator(
            qwen_client=state.swarm.qwen_client,
            config=OrchestrationConfig(
                max_depth=3,
                max_breadth=4,
                goal_satisfaction_threshold=0.8,
                enable_speculative=True,
                time_budget=180.0,
                max_concurrent_tasks=6,
            )
        )

        # 设置回调
        async def on_node_update(node: TaskNode):
            """节点更新回调"""
            await log_event(f"📍 [{node.agent_type}] {node.query[:30]}... -> {node.status}")
            await state.broadcast("research_node_updated", {
                "task_id": task_id,
                "node": node.to_dict(),
            })

        async def on_finding(node_id: str, finding: str):
            """发现回调"""
            await log_event(f"💡 发现: {finding[:50]}...")

        orchestrator.set_callbacks(on_node_update, on_finding)

        await update_stage(0, "completed", "规划完成")

        # ========== 阶段 2: 并行研究 ==========
        await update_stage(1, "running")
        await log_event("🔄 启动并行研究...")

        result = await orchestrator.orchestrate(content, metadata)

        await update_stage(1, "completed", f"完成 {result['stats']['completed_nodes']} 个研究节点")

        # ========== 阶段 3: 实时编排 ==========
        await update_stage(2, "running")
        await log_event("📈 编排统计:")
        await log_event(f"   - 总节点: {result['stats']['total_nodes']}")
        await log_event(f"   - 完成节点: {result['stats']['completed_nodes']}")
        await log_event(f"   - 剪枝节点: {result['stats']['pruned_nodes']}")
        await log_event(f"   - 吞吐量: {result['stats']['throughput']:.2f} 节点/秒")

        task["research_tree"] = result.get("tree")

        await update_stage(2, "completed")

        # ========== 阶段 4: 结果聚合 ==========
        task["status"] = TaskStatus.AGGREGATING.value
        await update_stage(3, "running")
        await log_event("📝 聚合研究结果...")

        outputs = result.get("outputs", [])
        findings = result.get("findings", [])

        aggregated_content = "\n\n".join([
            f"## {o['query']}\n{o['output'][:1000]}"
            for o in outputs
        ])

        # 使用撰稿员生成报告
        writer_instance = state.create_agent_instance("writer", "生成最终报告")
        writer_instance["status"] = AgentStatus.RUNNING.value
        await state.broadcast("agent_created", writer_instance)
        await state.broadcast("agent_updated", writer_instance)

        try:
            final_report = await generate_final_report(
                task_id=task_id,
                original_task=content,
                execution_result=aggregated_content,
                execution_plan={"findings": findings},
                log_event=log_event,
                writer_id=writer_instance["id"]
            )

            task["result"] = final_report
            task["final_report"] = final_report

        finally:
            writer_instance["status"] = AgentStatus.IDLE.value
            await state.broadcast("agent_updated", writer_instance)
            await asyncio.sleep(0.3)
            state.release_agent_instance(writer_instance["id"])
            await state.broadcast("agent_removed", {"id": writer_instance["id"]})

        await update_stage(3, "completed", "报告生成完成")

        # 完成
        task["status"] = TaskStatus.COMPLETED.value
        task["completed_at"] = datetime.now().isoformat()
        task["progress"]["percentage"] = 100

        await state.broadcast("task_completed", task)
        await log_event("🎉 自适应编排任务完成!", "success")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 自适应编排失败: {error_msg}")
        print(traceback.format_exc())

        task["status"] = TaskStatus.FAILED.value
        task["error"] = error_msg
        task["completed_at"] = datetime.now().isoformat()

        await state.broadcast("task_failed", {"task_id": task_id, "error": error_msg})
        await log_event(f"❌ 任务失败: {error_msg}", "error")

    finally:
        # 清理沙箱代码解释器资源
        try:
            from src.tools import cleanup_sandbox
            await cleanup_sandbox()
        except Exception:
            pass
        # 清理浏览器沙箱资源
        try:
            from src.tools import cleanup_browser
            await cleanup_browser()
        except Exception:
            pass
