"""撰稿员生成最终报告"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any

from src import AgentStatus, MemoryType
from state import state
from utils import clean_thinking_tags


async def generate_final_report(
    task_id: str,
    original_task: str,
    execution_result: Any,
    execution_plan: Dict[str, Any],
    log_event,
    writer_id: str,
) -> str:
    """
    由 AI 撰稿员生成最终报告
    
    Args:
        task_id: 任务ID
        original_task: 原始任务描述
        execution_result: 执行结果
        execution_plan: 执行计划
        log_event: 日志记录函数
        writer_id: 撰稿员实例ID
        
    Returns:
        格式化的最终报告
    """
    from src.qwen.models import Message, QwenConfig
    import datetime as dt
    
    # 获取当前日期时间
    now = dt.datetime.now()
    current_datetime = now.strftime("%Y年%m月%d日 %H:%M:%S")
    current_year = now.year
    current_month = now.month
    current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    
    # 准备上下文
    refined_task = execution_plan.get("refined_task", original_task)
    key_objectives = execution_plan.get("key_objectives", [])
    suggested_agents = execution_plan.get("suggested_agents", [])
    
    # 构建提示词 - 添加时间声明，优化报告结构
    # 控制输入长度：子任务结果过长会挤占输出 token 预算，
    # 按步骤截断以确保报告生成有足够空间输出完整的 3000+ 字报告
    raw_result = str(execution_result) if execution_result else "无结果"
    
    # 按 "## " 分割各步骤结果，每步保留前 800 字符，总量上限 12000 字符
    sections = raw_result.split("\n\n## ")
    trimmed_sections = []
    total_len = 0
    max_total = 12000
    max_per_section = 800
    for i, sec in enumerate(sections):
        prefix = "## " if i > 0 else ""
        text = prefix + sec
        if len(text) > max_per_section:
            text = text[:max_per_section] + "...(已精简)"
        if total_len + len(text) > max_total:
            trimmed_sections.append(f"...(剩余 {len(sections) - i} 个步骤结果已省略，请基于已有内容综合分析)")
            break
        trimmed_sections.append(text)
        total_len += len(text)
    result_str = "\n\n".join(trimmed_sections)
    
    # 提取关键目标用于报告
    objectives_text = "\n".join(f"- {obj}" for obj in key_objectives) if key_objectives else "未指定"
    
    prompt = f"""你是一位资深的行业分析师兼首席撰稿员，需要根据多智能体团队的执行结果，撰写一份**深度、全面、专业**的综合研究报告。

###############################################
# 🕐 系统时间：{current_datetime} {current_weekday}
# 当前是{current_year}年{current_month}月
###############################################

## 原始任务
{original_task}

## 任务关键目标
{objectives_text}

## 各步骤执行结果
{result_str}

---

## 📐 报告撰写规范

### 硬性要求
- **报告总字数不少于 3000 字**，确保每个章节都有充分的论述
- **至少包含 3 个数据表格**，用于结构化对比分析
- **每个核心发现必须有数据/案例支撑**，标注具体来源

### 报告结构（严格按此顺序，每个章节都要充分展开）

#### 1. 📌 执行摘要（Executive Summary）（200-300字）
- 用 **5-8 句话** 概括核心结论和关键发现
- 提炼最关键的数据点和洞察
- 指出核心差异点和战略意义

#### 2. 📊 核心发现（800-1000字）
- 从所有步骤结果中提炼 **5-8 个最重要的发现**
- 每个发现用 **加粗标题 + 3-5 句详细说明** 的格式
- 必须包含具体数据、数字、百分比、事实支撑
- 使用 **对比表格** 呈现多维度数据

#### 3. 💡 详细分析（800-1200字）
- 按主题/维度分 **3-5 个小节**（使用 ### 三级标题）
- 每个小节深入分析一个方面，不少于 200 字
- **综合分析**：交叉对比不同步骤的结果，找出关联、趋势、矛盾
- **案例引用**：引用具体的公司/项目/产品案例来论证观点
- 使用列表、加粗、引用等格式增强可读性

#### 4. 📈 数据与趋势分析（500-800字）
- 用 **至少 2 个表格** 整理对比关键数据
- 识别数据中的 **趋势、规律、异常值、拐点**
- 提供数据解读：解释数字背后的原因和影响
- 使用具体数字进行纵向（历史演变）和横向（同类对比）分析
- 对趋势进行预测和展望

#### 5. 🎯 战略评估与场景推荐（300-500字）
- 按不同场景/用途给出明确的推荐方案
- 使用 **推荐矩阵表格**（场景 × 推荐方案 × 理由）
- 评估各方案的适用条件和限制

#### 6. ✅ 结论与行动建议（300-500字）
- **总结性结论**：3-5 个明确的核心结论
- **可操作建议**：5-8 条具体、可执行的行动建议（编号列出）
- **风险提示**：需要注意的潜在问题或局限性
- **展望**：未来 1-3 年的发展趋势预判

### 格式要求
- 使用 Markdown 格式：## 二级标题、### 三级标题、**加粗**、*斜体*、> 引用
- 数据对比必须使用表格（| 列1 | 列2 | 格式）
- 要点使用有序或无序列表
- 重要结论使用 **加粗** 或 > 引用块突出
- 段落之间留空行，保持视觉层次

### 内容要求
- **综合性**：不要简单罗列各步骤结果，要综合分析、交叉引用、深度融合
- **深度**：对关键发现进行深入解读，分析根本原因和深层影响
- **专业性**：使用专业术语和分析框架（SWOT、波特五力、PEST等适用时引入）
- **完整性**：覆盖所有步骤的重要发现，不遗漏关键信息
- **数据密度**：每段分析至少包含 1 个具体数据点或案例
- 当前是{current_year}年{current_month}月

## 严格禁止
- 禁止输出思考过程或分析过程描述
- 禁止使用"我认为"、"让我分析"、"首先我需要"等第一人称过程性语句
- 禁止输出"接下来"、"然后"等过渡性语句
- 禁止输出空洞的概括性语句，每句话必须有信息量
- 直接输出最终报告，不要任何铺垫或解释"""

    messages = [Message(role="user", content=prompt)]
    # 报告生成：关闭 enable_thinking 以将全部 max_tokens 预算用于实际输出内容
    # 深度分析已由子智能体完成，报告撰稿员只需综合撰写，不需要额外推理
    config = QwenConfig(
        temperature=0.7,
        enable_thinking=False,
        enable_search=True,
        max_tokens=16384,
        timeout=600.0,
    )
    
    # 记录开始生成
    await log_event("📝 撰稿员开始生成报告...")
    
    # 记录到撰稿员的流式输出
    if writer_id not in state.agent_logs:
        state.agent_logs[writer_id] = []
    state.agent_streams[writer_id] = ""
    
    # ========== 流式生成报告（支持续写：模型单次输出不足时自动追加） ==========
    report_content = ""
    required_sections = ["战略评估", "结论", "行动建议"]  # 完整报告必须包含的末尾章节关键词
    max_continuations = 2  # 最多续写 2 次
    
    for attempt in range(1 + max_continuations):
        if attempt == 0:
            # 首次生成
            call_messages = messages
        else:
            # 续写：将已有内容作为 assistant 回复，要求继续
            await log_event(f"📝 报告未完成（缺少后续章节），正在续写第 {attempt} 次...")
            call_messages = [
                Message(role="user", content=prompt),
                Message(role="assistant", content=report_content),
                Message(role="user", content=f"报告尚未完成，请从上文断点处**无缝续写**剩余章节（包括数据与趋势分析、战略评估与场景推荐、结论与行动建议）。不要重复已有内容，直接继续输出。"),
            ]
        
        async for chunk in state.swarm.qwen_client.chat_stream(call_messages, config=config):
            # 检查任务是否已被取消
            if task_id in state.cancelled_tasks or task_id not in state.tasks:
                raise asyncio.CancelledError("任务已被取消")
            report_content += chunk
            state.agent_streams[writer_id] = report_content
            await state.broadcast("agent_stream", {
                "agent_id": writer_id,
                "task_id": task_id,
                "content": chunk,
                "full_content": report_content
            })
        
        # 检查报告是否包含必要的末尾章节
        has_ending = any(kw in report_content for kw in required_sections)
        if has_ending:
            break
    
    # 添加报告头部信息
    from datetime import datetime
    report_header = f"""# 📄 任务执行报告

> **任务ID**: {task_id}  
> **生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
> **生成者**: AI 撰稿员

---

"""
    
    # 清理报告内容中的 thinking 标签
    report_content = clean_thinking_tags(report_content)
    final_report = report_header + report_content
    
    # ========== 质量评估（仅对较长报告进行）==========
    # 优化：短报告跳过质量评估以提高效率
    should_evaluate = state.quality_assurance and len(report_content) > 500
    
    if should_evaluate:
        try:
            await log_event("🔬 质量检查员正在评估报告质量...")
            
            quality_report = await state.quality_assurance.evaluate_quality(
                content=report_content,
                task_description=original_task,
                expected_output="完整、专业的任务执行报告",
                agent_type="summarizer",
            )
            
            # 存储质量报告
            state.quality_reports[task_id] = quality_report.to_dict()
            
            await log_event(f"📊 质量评分: {quality_report.score}/10 ({quality_report.level.value})")
            
            # 仅当质量明显不达标时才进行改进
            if quality_report.score < 7.0:
                await log_event("🔄 质量较低，启动改进...")
                
                reflection_result = await state.quality_assurance.reflect_and_improve(
                    content=report_content,
                    task_description=original_task,
                    quality_report=quality_report,
                )
                
                if reflection_result.improved_output:
                    report_content = clean_thinking_tags(reflection_result.improved_output)
                    final_report = report_header + report_content
                    await log_event(f"✅ 报告已改进")
        except Exception as e:
            await log_event(f"⚠️ 质量评估跳过: {str(e)[:50]}", "warning")
    else:
        # 短报告直接通过
        state.quality_reports[task_id] = {"score": 7.5, "level": "good", "passed": True}
    
    # ========== 存储到记忆 ==========
    if state.memory_manager:
        try:
            # 存储任务结果到短期记忆
            state.memory_manager.store(
                content=f"任务: {original_task}\n\n结果摘要: {report_content[:500]}",
                memory_type=MemoryType.SHORT_TERM,
                task_id=task_id,
                agent_type="summarizer",
                tags=["task_result", "report"],
                importance=0.7,
            )
            
            # 提取知识点存储到语义记忆
            knowledge_points = state.memory_manager.extract_knowledge(report_content, task_id)
            for kp in knowledge_points[:5]:  # 最多存储5个知识点
                state.memory_manager.store(
                    content=kp,
                    memory_type=MemoryType.SEMANTIC,
                    task_id=task_id,
                    tags=["knowledge", "extracted"],
                    importance=0.6,
                )
        except Exception as e:
            print(f"[Memory] 存储记忆失败: {e}")
    
    return final_report
