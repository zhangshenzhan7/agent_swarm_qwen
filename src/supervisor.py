"""
AI 主管 - 使用 ReAct 架构进行动态任务规划和执行流程管理

作为 AI 团队的主管，主要职责：
1. 分析用户任务，理解真实意图
2. 调研任务背景，补充必要信息
3. 改写和细化任务描述，使其更清晰可执行
4. 制定动态执行计划，规划有依赖关系的子任务链路
5. 监督执行过程，根据中间结果动态调整后续步骤
6. 协调智能体团队，管理上下游依赖关系

ReAct (Reasoning + Acting) 架构:
- Thought: 分析任务，思考如何规划
- Action: 执行调研、改写、规划
- Observation: 观察结果，迭代优化

动态执行流程:
- 支持串行、并行、条件分支执行
- 上游任务结果作为下游任务输入
- 根据中间结果动态调整执行路径
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Awaitable
from enum import Enum

from .qwen.interface import IQwenClient
from .qwen.models import Message, QwenConfig
from .models.team import ExecutionPlan, PlanStatus
from .models.task import SubTask

# 流式回调类型
StreamCallback = Callable[[str], Awaitable[None]]

logger = logging.getLogger(__name__)


class PlanningPhase(Enum):
    """规划阶段"""
    ANALYZING = "analyzing"           # 分析任务
    RESEARCHING = "researching"       # 调研背景
    REWRITING = "rewriting"           # 改写任务
    PLANNING = "planning"             # 制定计划
    READY = "ready"                   # 准备执行


class ExecutionStepStatus(Enum):
    """执行步骤状态"""
    PENDING = "pending"               # 等待执行
    BLOCKED = "blocked"               # 被依赖阻塞
    RUNNING = "running"               # 执行中
    COMPLETED = "completed"           # 已完成
    FAILED = "failed"                 # 失败
    SKIPPED = "skipped"               # 跳过


@dataclass
class ExecutionStep:
    """执行步骤"""
    step_id: str                          # 步骤ID
    step_number: int                      # 步骤序号
    name: str                             # 步骤名称
    description: str                      # 详细描述
    agent_type: str                       # 执行智能体类型
    expected_output: str                  # 预期产出
    dependencies: List[str]               # 依赖的步骤ID列表
    status: ExecutionStepStatus = ExecutionStepStatus.PENDING
    input_data: Optional[Dict[str, Any]] = None   # 输入数据（来自上游）
    output_data: Optional[Dict[str, Any]] = None  # 输出数据（传给下游）
    error: Optional[str] = None           # 错误信息
    started_at: Optional[str] = None      # 开始时间
    completed_at: Optional[str] = None    # 完成时间
    review_history: List[Dict[str, Any]] = field(default_factory=list)  # 评审历史
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "name": self.name,
            "description": self.description,
            "agent_type": self.agent_type,
            "expected_output": self.expected_output,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "review_history": self.review_history,
        }


@dataclass
class ExecutionFlow:
    """执行流程 - 管理步骤间的依赖关系"""
    steps: Dict[str, ExecutionStep] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)  # 拓扑排序后的执行顺序
    adjustment_history: List[Dict[str, Any]] = field(default_factory=list)  # 调整历史
    
    def add_step(self, step: ExecutionStep):
        """添加执行步骤"""
        self.steps[step.step_id] = step
    
    def get_ready_steps(self) -> List[ExecutionStep]:
        """获取可以执行的步骤（依赖已满足）"""
        ready = []
        for step in self.steps.values():
            if step.status != ExecutionStepStatus.PENDING:
                continue
            # 检查所有依赖是否已完成
            deps_satisfied = all(
                self.steps.get(dep_id, ExecutionStep("", 0, "", "", "", "", [])).status == ExecutionStepStatus.COMPLETED
                for dep_id in step.dependencies
            )
            if deps_satisfied:
                ready.append(step)
        return ready
    
    def get_step_input(self, step: ExecutionStep) -> Dict[str, Any]:
        """获取步骤的输入数据（来自上游依赖）"""
        input_data = {}
        for dep_id in step.dependencies:
            dep_step = self.steps.get(dep_id)
            if dep_step and dep_step.output_data:
                input_data[dep_id] = dep_step.output_data
        return input_data
    
    def update_step_status(self, step_id: str, status: ExecutionStepStatus, 
                           output_data: Optional[Dict[str, Any]] = None,
                           error: Optional[str] = None):
        """更新步骤状态"""
        if step_id in self.steps:
            step = self.steps[step_id]
            step.status = status
            if output_data:
                step.output_data = output_data
            if error:
                step.error = error
            if status == ExecutionStepStatus.RUNNING:
                step.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
            elif status in (ExecutionStepStatus.COMPLETED, ExecutionStepStatus.FAILED):
                step.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
    
    def is_completed(self) -> bool:
        """检查流程是否全部完成"""
        return all(
            step.status in (ExecutionStepStatus.COMPLETED, ExecutionStepStatus.SKIPPED, ExecutionStepStatus.FAILED)
            for step in self.steps.values()
        )
    
    def get_progress(self) -> Dict[str, Any]:
        """获取执行进度"""
        total = len(self.steps)
        completed = sum(1 for s in self.steps.values() if s.status == ExecutionStepStatus.COMPLETED)
        running = sum(1 for s in self.steps.values() if s.status == ExecutionStepStatus.RUNNING)
        failed = sum(1 for s in self.steps.values() if s.status == ExecutionStepStatus.FAILED)
        reviewed = sum(1 for s in self.steps.values() if s.review_history)
        return {
            "total": total,
            "completed": completed,
            "running": running,
            "failed": failed,
            "progress_percent": int(completed / total * 100) if total > 0 else 0,
            "reviewed": reviewed,
            "adjusted": len(self.adjustment_history),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "execution_order": self.execution_order,
            "progress": self.get_progress(),
            "adjustment_history": self.adjustment_history,
        }


@dataclass
class TaskPlan:
    """任务规划结果"""
    original_task: str                    # 原始任务
    task_analysis: Dict[str, Any]         # 任务分析
    refined_task: str                     # 改写后的任务
    background_research: str              # 背景调研
    execution_plan: List[Dict[str, Any]]  # 执行计划（步骤列表）
    execution_flow: Optional[ExecutionFlow] = None  # 执行流程（带依赖关系）
    suggested_agents: List[str] = field(default_factory=list)  # 建议的智能体
    estimated_complexity: float = 5.0     # 预估复杂度
    key_objectives: List[str] = field(default_factory=list)    # 关键目标
    success_criteria: List[str] = field(default_factory=list)  # 成功标准
    potential_challenges: List[str] = field(default_factory=list)  # 潜在挑战
    react_trace: List[Dict[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_task": self.original_task,
            "task_analysis": self.task_analysis,
            "refined_task": self.refined_task,
            "background_research": self.background_research,
            "execution_plan": self.execution_plan,
            "execution_flow": self.execution_flow.to_dict() if self.execution_flow else None,
            "suggested_agents": self.suggested_agents,
            "estimated_complexity": self.estimated_complexity,
            "key_objectives": self.key_objectives,
            "success_criteria": self.success_criteria,
            "potential_challenges": self.potential_challenges,
            "react_trace": self.react_trace,
        }


@dataclass
class SupervisorConfig:
    """主管配置"""
    max_react_iterations: int = 5         # 最大 ReAct 迭代次数
    enable_research: bool = True          # 是否启用背景调研
    verbose_planning: bool = True         # 是否详细规划
    enable_dynamic_adjustment: bool = True  # 是否启用动态调整
    enable_quality_gates: bool = True     # 是否启用质量门控
    quality_threshold: float = 6.0        # 质量门控阈值
    enable_conflict_detection: bool = True  # 是否启用冲突检测
    enable_reflection: bool = True        # 是否启用反思机制
    max_retry_on_failure: int = 2         # 失败时最大重试次数


class Supervisor:
    """
    AI 主管 - 任务规划专家
    
    职责：
    1. 深入分析用户任务，理解真实需求
    2. 调研相关背景知识
    3. 改写任务使其更清晰、可执行
    4. 制定详细的执行计划
    5. 为智能体团队提供明确的工作指导
    """
    
    def __init__(
        self,
        qwen_client: IQwenClient,
        config: Optional[SupervisorConfig] = None,
        # 委派回调函数
        delegate_callback: Optional[Callable[[str, str, str], Awaitable[str]]] = None,
    ):
        self._qwen_client = qwen_client
        self._config = config or SupervisorConfig()
        self._planning_history: List[TaskPlan] = []
        self._delegate_callback = delegate_callback  # (agent_type, task_name, task_content) -> result
    
    def set_delegate_callback(self, callback: Callable[[str, str, str], Awaitable[str]]):
        """设置委派回调函数"""
        self._delegate_callback = callback
    
    async def plan_task(
        self,
        user_task: str,
        context: Optional[Dict[str, Any]] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> TaskPlan:
        """
        规划任务 - 主入口
        简单任务：主管直接回答
        复杂任务：委派分析/调研 → 制定执行计划
        
        Args:
            user_task: 用户原始任务
            context: 可选的上下文信息
            stream_callback: 流式输出回调函数
            
        Returns:
            完整的任务规划
        """
        react_trace = []
        
        try:
            print(f"[Supervisor] 开始规划任务: {user_task[:50]}...")
            
            # ========== 阶段 1: 主管快速理解任务并判断复杂度 ==========
            print("[Supervisor] 阶段1: 快速理解任务...")
            if stream_callback:
                await stream_callback("\n📋 【主管】正在评估任务...\n")
            
            quick_result = await self._quick_understand_task(user_task, context, stream_callback)
            react_trace.append({"type": "thought", "phase": "任务评估", "content": json.dumps(quick_result, ensure_ascii=False)})
            
            is_simple = quick_result.get("is_simple", False)
            complexity = quick_result.get("complexity", 5)
            can_answer_directly = quick_result.get("can_answer_directly", False)
            direct_answer_from_llm = quick_result.get("direct_answer", "")
            
            print(f"[Supervisor] 任务评估: 简单={is_simple}, 复杂度={complexity}, 可直接回答={can_answer_directly}, 答案={direct_answer_from_llm}")
            
            # ========== 可直接回答的任务：主管直接回答 ==========
            # 禁用直接回答，强制使用多智能体协作
            should_answer_directly = False  # 暂时禁用直接回答，强制走多智能体流程
            
            print(f"[Supervisor] should_answer_directly={should_answer_directly} (已禁用直接回答，强制使用多智能体)")
            
            if should_answer_directly:
                print("[Supervisor] 简单问题，主管直接回答")
                if stream_callback:
                    await stream_callback(f"\n✅ 【主管】这是个简单问题，我直接回答\n")
                
                direct_answer = direct_answer_from_llm
                
                # 确保 direct_answer 是字符串
                if direct_answer is not None:
                    direct_answer = str(direct_answer)
                else:
                    direct_answer = ""
                
                # 如果没有直接答案，生成一个
                if not direct_answer:
                    direct_answer = await self._generate_direct_answer(user_task, stream_callback)
                
                react_trace.append({"type": "action", "phase": "直接回答", "content": direct_answer})
                
                # 构建简单任务的规划结果 - 标记为直接回答，不需要员工执行
                plan = TaskPlan(
                    original_task=user_task,
                    task_analysis={
                        "task_type": "simple_direct",  # 标记为直接回答类型
                        "complexity": complexity,
                        "core_intent": quick_result.get("understanding", user_task),
                        "is_simple": True,
                        "direct_answer": direct_answer,  # 保存直接答案
                    },
                    refined_task=user_task,
                    background_research="简单问题，无需调研",
                    execution_plan=[],  # 空执行计划，表示不需要员工执行
                    execution_flow=None,
                    suggested_agents=[],
                    estimated_complexity=complexity,
                    key_objectives=["直接回答用户问题"],
                    success_criteria=["问题已回答"],
                    potential_challenges=[],
                    react_trace=react_trace,
                )
                
                self._planning_history.append(plan)
                print(f"[Supervisor] 简单问题已直接回答!")
                return plan
            
            # ========== 复杂任务：并行委派分析和调研 ==========
            print("[Supervisor] 复杂任务，开始委派...")
            if stream_callback:
                await stream_callback(f"[NEW_PHASE]🔄 【主管】复杂任务(复杂度:{complexity})，启动团队协作\n")
            
            quick_understanding = quick_result.get("understanding", user_task[:100])
            
            # ========== 阶段 2+3: 并行委派分析师和搜索员 ==========
            import asyncio as _asyncio
            
            need_research = self._config.enable_research and complexity >= 5
            
            if stream_callback:
                if need_research:
                    await stream_callback("[NEW_PHASE]📊🔍 【主管】并行委派 AI分析师 + AI搜索员...\n")
                else:
                    await stream_callback("[NEW_PHASE]📊 【主管】委派 AI分析师 进行深度分析...\n")
            
            if need_research:
                print("[Supervisor] 阶段2+3: 并行委派分析师和搜索员...")
                # 分析师不需要 task_analysis，搜索员需要 — 但搜索员可以用 quick_result 代替
                analysis_coro = self._delegate_analysis(user_task, quick_understanding, stream_callback)
                research_coro = self._delegate_research(user_task, {"task_type": "comprehensive", "core_intent": quick_understanding, "domain_knowledge": []}, stream_callback)
                
                task_analysis, research = await _asyncio.gather(analysis_coro, research_coro)
                
                react_trace.append({"type": "action", "phase": "分析师分析", "content": json.dumps(task_analysis, ensure_ascii=False)})
                react_trace.append({"type": "action", "phase": "搜索员调研", "content": research})
            else:
                print("[Supervisor] 阶段2: 委派分析师...")
                task_analysis = await self._delegate_analysis(user_task, quick_understanding, stream_callback)
                react_trace.append({"type": "action", "phase": "分析师分析", "content": json.dumps(task_analysis, ensure_ascii=False)})
                research = "任务复杂度较低，跳过背景调研"
                if stream_callback:
                    await stream_callback("[NEW_PHASE]⏭️ 【主管】任务复杂度较低，跳过背景调研\n")
            
            print(f"[Supervisor] 分析完成: {task_analysis.get('task_type', 'N/A')}")
            print(f"[Supervisor] 调研完成")
            
            # 将主管判断的 output_type 注入到 task_analysis 中
            supervisor_output_type = quick_result.get("output_type", "report")
            task_analysis["output_type"] = supervisor_output_type
            print(f"[Supervisor] 输出类型判断: {supervisor_output_type}")
            
            # ========== 阶段 4: 主管改写任务 ==========
            print("[Supervisor] 阶段4: 改写任务...")
            if stream_callback:
                await stream_callback("[NEW_PHASE]✏️ 【主管】根据分析结果改写任务...\n")
            
            refined_task = await self._rewrite_task(user_task, task_analysis, research, stream_callback)
            react_trace.append({"type": "action", "phase": "任务改写", "content": refined_task})
            print(f"[Supervisor] 任务改写完成")
            
            # ========== 阶段 5: 主管制定执行计划 ==========
            print("[Supervisor] 阶段5: 制定执行计划...")
            if stream_callback:
                await stream_callback("[NEW_PHASE]📝 【主管】制定执行计划和智能体分配...\n")
            
            execution_plan = await self._create_execution_plan(refined_task, task_analysis, research, stream_callback)
            
            # 提取 ExecutionFlow 对象
            execution_flow = execution_plan.pop("execution_flow", None)
            
            react_trace.append({"type": "action", "phase": "执行计划", "content": json.dumps(execution_plan, ensure_ascii=False)})
            print(f"[Supervisor] 执行计划完成: {len(execution_plan.get('steps', []))} 个步骤")
            
            # ========== 阶段 6: 确定智能体分配 ==========
            print("[Supervisor] 阶段6: 智能体分配...")
            agent_assignment = await self._assign_agents(execution_plan, task_analysis)
            react_trace.append({"type": "observation", "phase": "智能体分配", "content": json.dumps(agent_assignment, ensure_ascii=False)})
            print(f"[Supervisor] 智能体分配完成: {agent_assignment.get('agents', [])}")
            
            # 构建最终规划
            plan = TaskPlan(
                original_task=user_task,
                task_analysis=task_analysis,
                refined_task=refined_task,
                background_research=research,
                execution_plan=execution_plan.get("steps", []),
                execution_flow=execution_flow,
                suggested_agents=agent_assignment.get("agents", []),
                estimated_complexity=task_analysis.get("complexity", complexity),
                key_objectives=execution_plan.get("objectives", []),
                success_criteria=execution_plan.get("success_criteria", []),
                potential_challenges=execution_plan.get("challenges", []),
                react_trace=react_trace,
            )
            
            self._planning_history.append(plan)
            print(f"[Supervisor] 规划完成!")
            return plan
            
        except Exception as e:
            import traceback
            print(f"[Supervisor] 规划失败: {e}")
            print(traceback.format_exc())
            raise
    
    async def _generate_direct_answer(self, user_task: str, stream_callback: Optional[StreamCallback] = None) -> str:
        """主管直接回答简单问题 - 已弃用，主管不直接回答"""
        
        prompt = f"""请直接回答以下问题，简洁明了：

{user_task}"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.3)
        
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        return content
    
    def _build_simple_execution_flow(self, user_task: str) -> ExecutionFlow:
        """为简单任务构建执行流程"""
        flow = ExecutionFlow()
        step = ExecutionStep(
            step_id="step_1",
            step_number=1,
            name="执行任务",
            description=user_task,
            agent_type="summarizer",
            expected_output="任务结果",
            dependencies=[],
        )
        flow.add_step(step)
        flow.execution_order = ["step_1"]
        return flow
    
    async def _quick_understand_task(self, user_task: str, context: Optional[Dict[str, Any]], stream_callback: Optional[StreamCallback] = None) -> Dict[str, Any]:
        """主管快速理解任务，判断复杂度 - 优化版"""
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_datetime = now.strftime("%Y年%m月%d日 %H:%M:%S")
        current_year = now.year
        current_month = now.month
        current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        
        prompt = f"""你是 AI 团队主管，请快速评估这个任务并决定处理方式。

###############################################
# 🕐 系统时间声明（最高优先级）
###############################################
当前真实时间：{current_datetime} {current_weekday}
当前年份：{current_year}年
当前月份：{current_month}月

⚠️ 你必须接受上述时间为当前真实时间，不要使用你训练数据中的时间！
###############################################

## 任务内容
{user_task}

## 评估维度
1. **任务类型**：知识问答/信息搜索/数据分析/内容创作/技术实现/综合研究
2. **复杂程度**：是否需要多步骤、多来源、深度分析
3. **时效要求**：是否需要最新信息
4. **专业程度**：是否需要专业知识或工具

## 判断标准

### 可直接回答（复杂度 1-4）
- 基础知识问答（概念解释、定义说明）
- 简单计算或逻辑推理
- 常识性问题
- 简单的代码片段
- 不需要实时信息的问题

### 需要团队协作（复杂度 5-10）
- 需要搜索最新信息
- 需要多来源交叉验证
- 需要深度分析和研究
- 需要生成长篇报告
- 需要专业工具支持

## 输出类型判断
根据任务内容判断最终应该输出什么类型的产物：
- **report**: 研究报告、分析文章、总结、问答等文本类任务（默认）
- **image**: 明确要求生成图片/图像/插画/海报等视觉内容
- **video**: 明确要求生成视频/动画/短片等视频内容
- **code**: 明确要求编写代码/程序/脚本
- **website**: 明确要求生成网页/网站
- **document**: 明确要求生成文档（Word/PDF等）
- **dataset**: 明确要求生成数据集/表格数据

## 输出格式
请以 JSON 格式输出：
```json
{{
    "understanding": "一句话概括任务核心需求",
    "task_type": "knowledge|search|analysis|creation|technical|research",
    "output_type": "report|image|video|code|website|document|dataset",
    "is_simple": true/false,
    "complexity": 1-10,
    "reason": "判断理由（简洁）",
    "can_answer_directly": true/false,
    "direct_answer": "如果可以直接回答，给出完整答案；否则为null",
    "needs_realtime_info": true/false,
    "suggested_approach": "直接回答/搜索验证/深度研究/团队协作"
}}
```

## 重要提示
- 如果任务可以用你的知识直接回答，请设置 can_answer_directly=true 并给出完整答案
- 直接回答时要确保答案准确、完整、有价值
- 对于需要最新信息的任务，即使看起来简单也要标记 needs_realtime_info=true
- output_type 必须根据用户意图准确判断：只有明确要求生成图片才选 image，明确要求生成视频才选 video，其他默认 report
- 再次强调：当前是{current_year}年{current_month}月，不是2024年！

只输出 JSON。"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.1)
        
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            result = json.loads(content.strip())
            # 确保 output_type 存在且合理，否则用关键词检测
            if not result.get("output_type") or result["output_type"] == "report":
                detected = self._detect_output_type(user_task)
                if detected != "report":
                    result["output_type"] = detected
            return result
        except:
            return {
                "understanding": user_task[:100],
                "task_type": "research",
                "output_type": self._detect_output_type(user_task),
                "is_simple": False,
                "complexity": 5,
                "reason": "无法判断，按复杂任务处理",
                "can_answer_directly": False,
                "direct_answer": None,
                "needs_realtime_info": True,
                "suggested_approach": "团队协作"
            }

    @staticmethod
    def _detect_output_type(task_content: str) -> str:
        """根据任务内容关键词检测输出类型"""
        task_lower = task_content.lower()
        
        # 图像关键词
        image_keywords = ["生成图", "生成一张", "画一张", "画一幅", "生成图片", "生成图像",
                          "生成海报", "生成插画", "生成logo", "文生图", "生图",
                          "设计一张", "制作一张图", "创作一幅", "绘制",
                          "画图", "画画", "作画", "生成一幅", "制作海报",
                          "generate image", "create image", "draw"]
        for kw in image_keywords:
            if kw in task_lower:
                return "image"
        
        # 视频关键词
        video_keywords = ["生成视频", "生成一段视频", "生成短视频", "生成一个视频",
                          "文生视频", "生成动画", "制作视频", "制作一段",
                          "生成一段", "生视频", "做一个视频", "做视频",
                          "generate video", "create video", "make video"]
        for kw in video_keywords:
            if kw in task_lower:
                return "video"
        
        # 代码关键词
        code_keywords = ["写代码", "编写代码", "写一个程序", "编写程序", "写脚本",
                         "实现一个", "开发一个", "写一个函数", "编程",
                         "write code", "implement", "develop a program"]
        for kw in code_keywords:
            if kw in task_lower:
                return "code"
        
        return "report"
    
    async def _delegate_analysis(self, user_task: str, quick_understanding: str, stream_callback: Optional[StreamCallback] = None) -> Dict[str, Any]:
        """委派分析师进行深度分析"""
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_year = now.year
        current_month = now.month
        current_date = now.strftime("%Y年%m月%d日")
        
        # 如果有委派回调，使用真实的分析师
        if self._delegate_callback:
            analysis_task = f"""
###############################################
# 🕐 系统时间声明（最高优先级）
###############################################
当前真实时间：{current_date}
当前年份：{current_year}年
当前月份：{current_month}月

⚠️ 重要：当前是{current_year}年{current_month}月，不是2024年！
###############################################

请对以下任务进行深度分析：

任务：{user_task}

主管初步理解：{quick_understanding}

请分析（以{current_year}年{current_month}月为当前时间基准）：
1. 任务类型（research/analysis/creation/technical/comprehensive）
2. 复杂度（1-10）
3. 核心意图
4. 关键要素
5. 所需能力
6. 潜在歧义
7. 预期产出格式
8. 所需领域知识

以 JSON 格式输出。记住当前是{current_year}年！"""
            
            try:
                result = await self._delegate_callback("analyst", "深度任务分析", analysis_task)
                # 尝试解析 JSON
                if "```json" in result:
                    result = result.split("```json")[1].split("```")[0]
                elif "```" in result:
                    result = result.split("```")[1].split("```")[0]
                return json.loads(result.strip())
            except:
                pass
        
        # 回退：主管自己分析
        return await self._extract_task_analysis(user_task, quick_understanding, stream_callback)
    
    async def _delegate_research(self, user_task: str, task_analysis: Dict[str, Any], stream_callback: Optional[StreamCallback] = None) -> str:
        """委派搜索员进行背景调研"""
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_year = now.year
        current_month = now.month
        current_date = now.strftime("%Y年%m月%d日")
        
        # 如果有委派回调，使用真实的搜索员
        if self._delegate_callback:
            research_task = f"""
###############################################
# 🕐 系统时间声明（最高优先级）
###############################################
当前真实时间：{current_date}
当前年份：{current_year}年
当前月份：{current_month}月

⚠️ 重要：当前是{current_year}年{current_month}月，不是2024年！
###############################################

请对以下任务进行背景调研：

任务：{user_task}

任务类型：{task_analysis.get('task_type', '综合')}
核心意图：{task_analysis.get('core_intent', '')}
所需领域知识：{', '.join(task_analysis.get('domain_knowledge', []))}

请调研（以{current_year}年{current_month}月为当前时间基准）：
1. 相关概念和背景知识
2. 行业最佳实践
3. 执行注意事项
4. 参考方向

简洁输出调研结果。记住当前是{current_year}年！"""
            
            try:
                result = await self._delegate_callback("searcher", "背景调研", research_task)
                if stream_callback:
                    await stream_callback(result)
                return result
            except:
                pass
        
        # 回退：主管自己调研
        return await self._research_background(user_task, task_analysis, stream_callback)
    
    async def _extract_task_analysis(self, user_task: str, analysis: str, stream_callback: Optional[StreamCallback] = None) -> Dict[str, Any]:
        """从分析中提取结构化信息（流式输出）"""
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_year = now.year
        current_month = now.month
        
        prompt = f"""基于以下任务分析，提取结构化信息。

###############################################
# 🕐 系统时间：{current_year}年{current_month}月
# ⚠️ 当前是{current_year}年，不是2024年！
###############################################

## 原始任务
{user_task}

## 分析内容
{analysis}

请以 JSON 格式输出：
```json
{{
    "task_type": "research|analysis|creation|technical|comprehensive",
    "complexity": 1-10,
    "core_intent": "用户的核心意图（一句话）",
    "key_elements": ["关键要素1", "关键要素2"],
    "required_capabilities": ["搜索", "分析", "写作", "编程"],
    "ambiguities": ["不清晰的点"],
    "expected_output_format": "报告|代码|数据|文档|其他",
    "domain_knowledge": ["需要的领域知识"]
}}
```

只输出 JSON。"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.1)
        
        # 使用流式 API
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        try:
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content.strip())
        except:
            return {
                "task_type": "comprehensive",
                "complexity": 5,
                "core_intent": user_task[:100],
                "key_elements": [],
                "required_capabilities": ["分析", "执行"],
                "ambiguities": [],
                "expected_output_format": "报告",
                "domain_knowledge": []
            }
    
    async def _research_background(self, user_task: str, analysis: Dict[str, Any], stream_callback: Optional[StreamCallback] = None) -> str:
        """调研任务背景（流式输出）"""
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_year = now.year
        current_month = now.month
        
        prompt = f"""作为 AI 主管，你需要为团队提供任务背景知识。

###############################################
# 🕐 系统时间声明
当前时间：{current_year}年{current_month}月
⚠️ 注意：当前是{current_year}年，不是2024年！
###############################################

## 用户任务
{user_task}

## 任务分析
- 类型: {analysis.get('task_type', '综合')}
- 核心意图: {analysis.get('core_intent', '')}
- 所需领域知识: {', '.join(analysis.get('domain_knowledge', []))}

## 调研要求
请提供执行此任务所需的背景知识：

1. **相关概念**：完成任务需要理解哪些核心概念？
2. **行业背景**：有哪些相关的行业知识或最佳实践？
3. **注意事项**：执行时需要特别注意什么？
4. **参考方向**：可以从哪些方向入手？

请简洁地输出背景调研结果，为后续执行提供指导。
记住：当前是{current_year}年{current_month}月！"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.4)
        
        # 使用流式 API
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        return content

    
    async def _rewrite_task(
        self, 
        user_task: str, 
        analysis: Dict[str, Any],
        research: str,
        stream_callback: Optional[StreamCallback] = None,
    ) -> str:
        """改写和细化任务 - 优化版，生成更清晰可执行的任务描述"""
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_datetime = now.strftime("%Y年%m月%d日")
        current_year = now.year
        current_month = now.month
        
        prompt = f"""作为 AI 主管，你需要将用户的任务改写成更清晰、更可执行的版本，让团队成员能够准确理解并高效执行。

###############################################
# 🕐 系统时间声明（最高优先级）
###############################################
当前真实时间：{current_datetime}
当前年份：{current_year}年
当前月份：{current_month}月

⚠️ 重要：你必须以 {current_year}年{current_month}月 为当前时间基准！
不要使用2024年或其他过去的时间！
###############################################

## 原始任务
{user_task}

## 任务分析
- 核心意图: {analysis.get('core_intent', '')}
- 任务类型: {analysis.get('task_type', '')}
- 关键要素: {', '.join(analysis.get('key_elements', []))}
- 不清晰的点: {', '.join(analysis.get('ambiguities', []))}
- 预期产出: {analysis.get('expected_output_format', '报告')}

## 背景调研
{research[:600] if research else '无'}

## 改写要求

### 1. 明确目标
- 清晰说明要达成什么结果
- 定义成功的标准

### 2. 补充细节
- 填补原任务中的空白
- 添加必要的上下文信息
- **时间范围**：如果任务涉及"近期"、"最新"等，请明确为截至{current_year}年{current_month}月

### 3. 消除歧义
- 对不清晰的地方做合理假设
- 明确范围和边界

### 4. 结构化表达
- 使用清晰的结构组织任务
- 突出关键要求

### 5. 可执行性
- 确保描述足够具体
- 让执行者知道该做什么

## 输出格式
请直接输出改写后的任务描述，格式如下：

**任务目标**：[一句话说明要达成什么]

**具体要求**：
1. [要求1]
2. [要求2]
...

**预期产出**：[描述期望的输出形式和内容]

**注意事项**：[如有特殊要求或限制]

不要加额外的解释说明，直接输出改写后的任务。记住当前是{current_year}年{current_month}月！"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.5)
        
        # 使用流式 API
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        # 清理 THINKING 标签
        import re
        content = re.sub(r'\[THINKING\].*?\[/THINKING\]', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'\[THINKING\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\[/THINKING\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\[NEW_PHASE\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = content.strip()
        
        return content
    
    async def _create_execution_plan(
        self,
        refined_task: str,
        analysis: Dict[str, Any],
        research: str,
        stream_callback: Optional[StreamCallback] = None,
    ) -> Dict[str, Any]:
        """制定详细执行计划 - 优化版，更智能的任务编排"""
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_datetime = now.strftime("%Y年%m月%d日")
        current_year = now.year
        current_month = now.month
        
        prompt = f"""作为 AI 主管，你需要为团队制定高效的执行计划，让智能体团队实际完成任务。

###############################################
# 🕐 系统时间声明（最高优先级）
###############################################
当前真实时间：{current_datetime}
当前年份：{current_year}年
当前月份：{current_month}月

⚠️ 重要：当前是{current_year}年，不是2024年！
所有时间相关的描述都要以{current_year}年{current_month}月为基准！
###############################################

## ⚠️ 重要说明
下面的"改写后的任务"是用户的最终需求，你需要制定执行计划来**实际完成这个任务**。
- 执行计划中的步骤应该是**实际执行任务的动作**（如：搜索信息、分析数据、撰写报告、解读论文等）
- **不要**把"任务改写"、"任务分析"、"任务规划"作为执行步骤，这些已经完成了
- 每个步骤都应该产出**实际的内容**，而不是"指令"或"计划"

## 改写后的任务（这是要实际完成的目标）
{refined_task}

## 任务分析
- 类型: {analysis.get('task_type', '综合')}
- 复杂度: {analysis.get('complexity', 5)}/10
- 核心意图: {analysis.get('core_intent', '')}
- 所需能力: {', '.join(analysis.get('required_capabilities', []))}
- 预期产出: {analysis.get('expected_output_format', '报告')}

## 背景知识
{research[:800] if research else '无'}

## 智能体团队（按专业分类）
### 信息获取类
| 角色 | 职责 | 适用场景 | 模型 |
|------|------|----------|------|
| searcher | 信息搜索 | 收集资料、查找信息 | qwen-plus |
| fact_checker | 事实核查 | 验证信息真实性、交叉核实 | qwen3-turbo |
| extractor | 信息提取 | 从文本提取结构化数据 | qwen3-turbo |

### 分析研究类
| 角色 | 职责 | 适用场景 | 模型 |
|------|------|----------|------|
| analyst | 数据分析 | 分析数据、识别趋势、统计分析 | qwen3-max |
| researcher | 深度研究 | 综合分析、学术研究、文献综述 | qwen3-max |
| strategist | 战略规划 | 市场分析、竞争研究、策略制定 | qwen3-max |
| consultant | 专业咨询 | 问题诊断、解决方案设计 | qwen3-max |

### 内容创作类
| 角色 | 职责 | 适用场景 | 模型 |
|------|------|----------|------|
| writer | 内容撰写 | 撰写报告、文档、文章 | qwen3-max |
| copywriter | 文案创作 | 营销文案、广告创意 | qwen3-max |
| creative | 创意构思 | 头脑风暴、创意发散 | qwen3-max |
| editor | 内容编辑 | 审核润色、格式优化 | qwen-plus |
| summarizer | 信息总结 | 摘要生成、要点提炼 | qwen-plus |

### 技术开发类
| 角色 | 职责 | 适用场景 | 模型 |
|------|------|----------|------|
| coder | 代码编写 | 技术实现、编程开发 | qwen3-max |
| debugger | 代码调试 | Bug定位、问题排查 | qwen3-max |
| reviewer | 代码审查 | 代码质量、安全检查 | qwen-max-longcontext |
| architect | 架构设计 | 系统设计、技术选型 | qwen3-max |

### 语言处理类
| 角色 | 职责 | 适用场景 | 模型 |
|------|------|----------|------|
| translator | 多语言翻译 | 翻译、本地化 | qwen-plus |
| formatter | 格式化 | 文档排版、格式整理 | qwen-plus |
| classifier | 内容分类 | 分类标注、主题识别 | qwen3-turbo |

### 专业领域类
| 角色 | 职责 | 适用场景 | 模型 |
|------|------|----------|------|
| document_analyst | 文档分析 | 长文档分析、信息提取 | qwen-max-longcontext |
| legal_reviewer | 法务审查 | 合同审查、法律风险 | qwen-max-longcontext |
| assistant | 通用助手 | 简单任务、快速响应 | qwen3-turbo |

### 视觉理解类
| 角色 | 职责 | 适用场景 | 模型 |
|------|------|----------|------|
| image_analyst | 图像分析 | 图像深度分析、场景理解 | qwen-vl-max |
| ocr_reader | 文字识别 | OCR、文档扫描、手写识别 | qwen-vl-ocr |
| chart_reader | 图表解读 | 图表数据提取、趋势分析 | qwen-vl-max |
| ui_analyst | 界面分析 | UI/UX评估、设计审查 | qwen-vl-max |
| image_describer | 图像描述 | 图像描述、无障碍文本 | qwen-vl-plus |
| visual_qa | 视觉问答 | 图像问答、视觉推理 | qwen-vl-max |

### 多模态生成类
| 角色 | 职责 | 适用场景 | 模型 |
|------|------|----------|------|
| text_to_image | 文生图 | 根据文字描述生成图像 | wanx2.1-t2i-turbo |
| text_to_video | 文生视频 | 根据文字描述生成视频 | wanx2.1-t2v-turbo |
| image_to_video | 图生视频 | 将静态图片转为动态视频 | wanx2.1-i2v-turbo |
| voice_synthesizer | 语音合成 | 文字转语音、配音 | cosyvoice-v1 |

## 执行计划设计原则
1. **并行优先**：同类型任务应该并行执行，如多个搜索员同时搜索不同内容
2. **合理步骤**：根据任务复杂度灵活安排步骤数量，简单任务可以 1-2 步，复杂任务可以 10 步以上
3. **质量保证**：关键信息需要核查验证
4. **结果导向**：每步都要有明确的产出
5. **时间基准**：所有涉及时间的描述以{current_year}年{current_month}月为当前时间
6. **模型匹配**：根据任务复杂度选择合适的角色（复杂任务用 qwen3-max 角色）
7. **视觉任务**：涉及图像分析时使用视觉理解类角色（qwen-vl 系列模型）
8. **生成任务**：涉及图像/视频/语音生成时使用多模态生成类角色（wanx/cosyvoice 模型）

## 并行执行说明
- 多个搜索任务可以同时进行，每个搜索员负责不同的搜索方向
- 没有依赖关系的步骤会自动并行执行
- 依赖关系通过 dependencies 字段指定，只有依赖的步骤完成后才会执行

## 典型执行模式
- **简单搜索**：searcher → summarizer
- **多源搜索**：[searcher_1, searcher_2, searcher_3](并行) → analyst → writer
- **信息验证**：searcher → fact_checker → writer
- **深度研究**：[searcher_股价, searcher_财报, searcher_新闻](并行) → analyst → researcher → writer
- **技术任务**：analyst → coder → reviewer
- **战略分析**：[searcher_市场, searcher_竞品](并行) → analyst → strategist → writer
- **图像分析**：image_analyst → summarizer
- **文档OCR**：ocr_reader → extractor → summarizer
- **数据可视化分析**：chart_reader → analyst → writer
- **创意任务**：researcher → creative → copywriter → editor
- **文档处理**：document_analyst → summarizer → translator
- **图像生成**：creative → text_to_image（根据创意生成图像）
- **视频生成**：creative → text_to_video（根据创意生成视频）
- **图片动态化**：image_analyst → image_to_video（分析图片后生成动态视频）
- **配音任务**：writer → voice_synthesizer（撰写文案后生成语音）

## ⚠️ 输出类型特殊规则（必须遵守）
当前任务的输出类型为：**{analysis.get('output_type', 'report')}**

### 如果输出类型是 image（图像生成）：
- **必须包含 text_to_image 步骤**，这是生成图像的唯一方式
- 典型流程：1-2个准备步骤（如 creative 构思提示词）→ text_to_image 生成图像
- **总步骤数不超过 3-4 个**，不要做过多的研究和分析
- 不需要 writer 撰写报告，图像本身就是最终产出

### 如果输出类型是 video（视频生成）：
- **必须包含 text_to_video 或 image_to_video 步骤**
- 典型流程：creative 构思 → text_to_video 生成视频（可多段并行）
- 如果需要多段视频，可以安排多个并行的 text_to_video 步骤
- **总步骤数不超过 5-6 个**

### 如果输出类型是 code（代码生成）：
- **必须包含 coder 步骤**，coder 拥有代码解释器可以实际执行代码
- 典型流程：researcher 调研 → coder 编写并执行代码

### 如果输出类型是 report（默认）：
- 按正常流程规划，最后一步通常是 writer 撰写报告

## 输出格式
请以 JSON 格式输出：
```json
{{
    "steps": [
        {{
            "step_id": "step_1",
            "step_number": 1,
            "name": "步骤名称（简洁，如：搜索论文信息、分析论文内容、撰写解读报告）",
            "description": "详细描述：做什么、怎么做、产出什么（注意：当前是{current_year}年{current_month}月）",
            "agent_type": "searcher|fact_checker|extractor|analyst|researcher|strategist|consultant|writer|copywriter|creative|editor|summarizer|coder|debugger|reviewer|architect|translator|formatter|classifier|document_analyst|legal_reviewer|assistant|image_analyst|ocr_reader|chart_reader|ui_analyst|image_describer|visual_qa|text_to_image|text_to_video|image_to_video|voice_synthesizer",
            "expected_output": "预期产出的具体描述（如：论文核心内容的详细解读、数据分析报告等）",
            "dependencies": [],
            "input_from": "输入来源说明",
            "output_to": "输出去向说明"
        }}
    ],
    "objectives": ["关键目标1", "关键目标2"],
    "success_criteria": ["成功标准1", "成功标准2"],
    "challenges": ["潜在挑战"],
    "execution_mode": "sequential|parallel|mixed",
    "estimated_time": "预估完成时间"
}}
```

## ⚠️ 关键注意事项
- **执行步骤必须是实际动作**：如"搜索信息"、"分析数据"、"撰写报告"、"解读论文"等
- **禁止以下步骤类型**：
  - ❌ "任务改写" / "任务重构" / "指令生成"
  - ❌ "任务分析" / "需求分析" / "任务规划"
  - ❌ "交付准备" / "执行准备" / "框架设计"
  - 这些都是规划阶段的工作，已经完成了！
- **每个步骤必须产出实际内容**：不是"指令"或"计划"，而是"分析结果"、"搜索结果"、"报告内容"等
- 步骤数量不做硬性限制，根据任务实际需要灵活安排
- 同类型的并行任务使用不同的 step_id（如 step_search_1, step_search_2）
- 并行步骤的 dependencies 为空或相同
- 依赖关系要形成有向无环图
- 每个步骤的描述要足够详细，让智能体能独立执行
- 最后一步通常是总结或撰写最终报告
- **重要**：当前是{current_year}年{current_month}月，步骤描述中涉及时间时请以此为准

## 示例：论文解读任务的执行计划
如果任务是"详细解释一篇论文"，正确的执行计划应该是：
1. researcher: 深入阅读论文，提取核心内容、方法论、实验结果
2. analyst: 分析论文的创新点、局限性、与现有研究的关系
3. writer: 撰写通俗易懂的论文解读报告

**错误示例**（不要这样做）：
1. ❌ "任务改写" - 这不是执行步骤
2. ❌ "生成执行指令" - 这不是执行步骤

## ⚠️ 输出格式要求
- 只输出纯 JSON，不要有任何其他文字
- 不要输出 thinking 过程
- JSON 必须是有效的，可以被直接解析
- 步骤数量根据任务复杂度灵活决定，不设上下限

只输出 JSON，不要有任何解释或说明。"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.2)
        
        # 使用流式 API
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        try:
            content = content.strip()
            
            # 清理 THINKING 标签
            import re
            content = re.sub(r'\[THINKING\].*?\[/THINKING\]', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'\[THINKING\]', '', content, flags=re.IGNORECASE)
            content = re.sub(r'\[/THINKING\]', '', content, flags=re.IGNORECASE)
            content = content.strip()
            
            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            content = content.strip()
            
            # 尝试解析 JSON
            plan_data = json.loads(content)
            
            # 验证必要字段
            if not plan_data.get("steps") or len(plan_data.get("steps", [])) == 0:
                raise ValueError("执行计划中没有步骤")
            
            # 构建执行流程
            execution_flow = ExecutionFlow()
            for step_data in plan_data.get("steps", []):
                # 清理步骤描述中的 THINKING 标签
                step_desc = step_data.get("description", "")
                step_desc = re.sub(r'\[THINKING\].*?\[/THINKING\]', '', step_desc, flags=re.DOTALL | re.IGNORECASE)
                step_desc = re.sub(r'\[THINKING\]', '', step_desc, flags=re.IGNORECASE)
                step_desc = re.sub(r'\[/THINKING\]', '', step_desc, flags=re.IGNORECASE)
                step_desc = step_desc.strip()
                
                # 清理步骤名称中的 THINKING 标签
                step_name = step_data.get("name", "未命名步骤")
                step_name = re.sub(r'\[THINKING\].*?\[/THINKING\]', '', step_name, flags=re.DOTALL | re.IGNORECASE)
                step_name = re.sub(r'\[THINKING\]', '', step_name, flags=re.IGNORECASE)
                step_name = re.sub(r'\[/THINKING\]', '', step_name, flags=re.IGNORECASE)
                step_name = step_name.strip() or "未命名步骤"
                
                step = ExecutionStep(
                    step_id=step_data.get("step_id", f"step_{step_data.get('step_number', 1)}"),
                    step_number=step_data.get("step_number", 1),
                    name=step_name,
                    description=step_desc if step_desc else step_data.get("name", "执行任务"),
                    agent_type=step_data.get("agent_type", "researcher"),
                    expected_output=step_data.get("expected_output", ""),
                    dependencies=step_data.get("dependencies", []),
                )
                execution_flow.add_step(step)
            
            # 计算拓扑排序的执行顺序
            execution_flow.execution_order = self._topological_sort(execution_flow.steps)
            
            # 清理 objectives/success_criteria/challenges 中的 THINKING 标签
            def _clean_thinking(text: str) -> str:
                text = re.sub(r'\[THINKING\].*?\[/THINKING\]', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'\[THINKING\]', '', text, flags=re.IGNORECASE)
                text = re.sub(r'\[/THINKING\]', '', text, flags=re.IGNORECASE)
                return text.strip()
            
            if "objectives" in plan_data:
                plan_data["objectives"] = [_clean_thinking(o) for o in plan_data["objectives"] if _clean_thinking(o)]
            if "success_criteria" in plan_data:
                plan_data["success_criteria"] = [_clean_thinking(s) for s in plan_data["success_criteria"] if _clean_thinking(s)]
            if "challenges" in plan_data:
                plan_data["challenges"] = [_clean_thinking(c) for c in plan_data["challenges"] if _clean_thinking(c)]
            
            plan_data["execution_flow"] = execution_flow
            print(f"[Supervisor] 成功解析执行计划: {len(plan_data.get('steps', []))} 个步骤")
            return plan_data
            
        except Exception as e:
            print(f"[Supervisor] 解析执行计划失败: {e}")
            print(f"[Supervisor] 原始内容前500字符: {content[:500] if content else 'None'}")
            
            # 返回更有意义的默认计划 - 基于任务分析生成多步骤计划
            default_flow = ExecutionFlow()
            
            # 根据任务类型生成默认步骤
            task_type = analysis.get("task_type", "comprehensive")
            required_caps = analysis.get("required_capabilities", [])
            
            default_steps = []
            
            # 步骤1: 信息收集/研究
            step1 = ExecutionStep(
                step_id="step_1",
                step_number=1,
                name="深度研究与信息收集",
                description=f"针对任务目标进行深入研究和信息收集。任务核心：{analysis.get('core_intent', refined_task[:200])}",
                agent_type="researcher",
                expected_output="详细的研究结果和关键信息",
                dependencies=[],
            )
            default_steps.append(step1)
            default_flow.add_step(step1)
            
            # 步骤2: 分析整理
            step2 = ExecutionStep(
                step_id="step_2",
                step_number=2,
                name="分析与整理",
                description="对收集的信息进行深度分析，提取关键洞察，整理成结构化内容",
                agent_type="analyst",
                expected_output="结构化的分析结果和关键洞察",
                dependencies=["step_1"],
            )
            default_steps.append(step2)
            default_flow.add_step(step2)
            
            # 步骤3: 撰写报告
            step3 = ExecutionStep(
                step_id="step_3",
                step_number=3,
                name="撰写最终报告",
                description="基于研究和分析结果，撰写完整、专业的最终报告",
                agent_type="writer",
                expected_output="完整的任务报告",
                dependencies=["step_2"],
            )
            default_steps.append(step3)
            default_flow.add_step(step3)
            
            default_flow.execution_order = ["step_1", "step_2", "step_3"]
            
            return {
                "steps": [s.to_dict() for s in default_steps],
                "execution_flow": default_flow,
                "objectives": [analysis.get("core_intent", "完成任务")],
                "success_criteria": ["任务完成"],
                "challenges": [],
                "execution_mode": "sequential",
                "quality_gates": [],
            }
    
    def _topological_sort(self, steps: Dict[str, ExecutionStep]) -> List[str]:
        """拓扑排序 - 确定执行顺序"""
        # 计算入度
        in_degree = {step_id: 0 for step_id in steps}
        for step in steps.values():
            for dep in step.dependencies:
                if dep in in_degree:
                    pass  # 依赖存在
            # 计算被依赖的次数
        
        for step in steps.values():
            for dep in step.dependencies:
                pass  # 入度计算
        
        # 简化：按step_number排序
        sorted_steps = sorted(steps.values(), key=lambda s: s.step_number)
        return [s.step_id for s in sorted_steps]
    
    async def _assign_agents(
        self,
        execution_plan: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """确定智能体分配"""
        
        # 从执行计划中提取需要的智能体类型
        agent_types = set()
        for step in execution_plan.get("steps", []):
            agent_type = step.get("agent_type", "researcher")
            agent_types.add(agent_type)
        
        # 根据所需能力补充智能体
        capabilities = analysis.get("required_capabilities", [])
        capability_to_agent = {
            "搜索": "searcher",
            "分析": "analyst",
            "写作": "writer",
            "编程": "coder",
            "研究": "researcher",
            "翻译": "translator",
            "核查": "fact_checker",
            "总结": "summarizer",
        }
        
        for cap in capabilities:
            if cap in capability_to_agent:
                agent_types.add(capability_to_agent[cap])
        
        return {
            "agents": list(agent_types),
            "primary_agent": execution_plan.get("steps", [{}])[0].get("agent_type", "researcher"),
            "team_size": len(agent_types),
        }
    
    def get_planning_history(self) -> List[TaskPlan]:
        """获取规划历史"""
        return self._planning_history.copy()
    
    async def evaluate_step_result(
        self,
        step: ExecutionStep,
        result: Dict[str, Any],
        execution_flow: ExecutionFlow,
        stream_callback: Optional[StreamCallback] = None,
    ) -> Dict[str, Any]:
        """
        评估步骤执行结果，决定是否需要动态调整
        
        Args:
            step: 已完成的步骤
            result: 步骤执行结果
            execution_flow: 当前执行流程
            stream_callback: 流式输出回调
            
        Returns:
            调整建议，包含是否需要重试、添加新步骤等
        """
        if not self._config.enable_dynamic_adjustment:
            return {"action": "continue", "adjustments": []}
        
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_year = now.year
        current_month = now.month
        current_date = now.strftime("%Y年%m月%d日")
        
        prompt = f"""作为 AI 主管，评估以下步骤的执行结果，决定是否需要调整后续执行计划。

###############################################
# 🕐 系统时间：{current_date}
# 当前是{current_year}年{current_month}月，不是2024年！
###############################################

## 已完成步骤
- 步骤: {step.name}
- 智能体: {step.agent_type}
- 预期产出: {step.expected_output}

## 执行结果
{json.dumps(result, ensure_ascii=False, indent=2)[:1000]}

## 当前执行流程
剩余步骤: {[s.name for s in execution_flow.steps.values() if s.status == ExecutionStepStatus.PENDING]}

## 评估要求
1. 结果质量是否达标？
2. 是否需要补充搜索或核查？
3. 后续步骤是否需要调整？

请以 JSON 格式输出：
```json
{{
    "quality_score": 1-10,
    "action": "continue|retry|add_step|skip_next",
    "reason": "评估理由",
    "adjustments": [
        {{
            "type": "add_step|modify_step|remove_step",
            "step_id": "新步骤ID或要修改的步骤ID",
            "details": {{}}
        }}
    ]
}}
```

只输出 JSON。"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.2)
        
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        try:
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content.strip())
        except:
            return {"action": "continue", "adjustments": [], "quality_score": 7}
    
    async def adjust_execution_flow(
        self,
        execution_flow: ExecutionFlow,
        adjustments: List[Dict[str, Any]],
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionFlow:
        """
        根据评估结果动态调整执行流程
        
        增强功能：
        - 跳过步骤时解除下游步骤对该步骤的依赖
        - 仅允许修改 pending 状态的步骤
        - 返回新增步骤列表（通过修改 execution_flow）
        
        Args:
            execution_flow: 当前执行流程
            adjustments: 调整列表
            stream_callback: 流式输出回调
            
        Returns:
            调整后的执行流程
        """
        for adj in adjustments:
            adj_type = adj.get("type")
            
            if adj_type == "add_step":
                # 添加新步骤，过滤无效依赖
                details = adj.get("details", {})
                raw_deps = details.get("dependencies", [])
                valid_deps = [d for d in raw_deps if d in execution_flow.steps]
                if len(valid_deps) != len(raw_deps):
                    logger.warning(f"添加步骤时过滤了无效依赖: {set(raw_deps) - set(valid_deps)}")
                
                new_step = ExecutionStep(
                    step_id=adj.get("step_id", f"dynamic_step_{len(execution_flow.steps) + 1}"),
                    step_number=len(execution_flow.steps) + 1,
                    name=details.get("name", "动态添加步骤"),
                    description=details.get("description", ""),
                    agent_type=details.get("agent_type", "researcher"),
                    expected_output=details.get("expected_output", ""),
                    dependencies=valid_deps,
                )
                execution_flow.add_step(new_step)
                if stream_callback:
                    await stream_callback(f"\n[动态调整] 添加新步骤: {new_step.name}\n")
            
            elif adj_type == "modify_step":
                # 仅允许修改 pending 状态的步骤
                step_id = adj.get("step_id")
                if step_id in execution_flow.steps:
                    step = execution_flow.steps[step_id]
                    if step.status != ExecutionStepStatus.PENDING:
                        logger.warning(f"跳过修改非 pending 状态的步骤: {step.name} (status={step.status.value})")
                        if stream_callback:
                            await stream_callback(f"\n[动态调整] 跳过修改（步骤非 pending 状态）: {step.name}\n")
                        continue
                    details = adj.get("details", {})
                    if "description" in details:
                        step.description = details["description"]
                    if "dependencies" in details:
                        step.dependencies = details["dependencies"]
                    if stream_callback:
                        await stream_callback(f"\n[动态调整] 修改步骤: {step.name}\n")
            
            elif adj_type == "remove_step":
                # 跳过步骤并解除下游依赖
                step_id = adj.get("step_id")
                if step_id in execution_flow.steps:
                    execution_flow.steps[step_id].status = ExecutionStepStatus.SKIPPED
                    # 解除下游步骤对该步骤的依赖
                    for downstream in execution_flow.steps.values():
                        if step_id in downstream.dependencies:
                            downstream.dependencies = [
                                d for d in downstream.dependencies if d != step_id
                            ]
                    if stream_callback:
                        await stream_callback(f"\n[动态调整] 跳过步骤: {execution_flow.steps[step_id].name}\n")
        
        # 重新计算执行顺序
        execution_flow.execution_order = self._topological_sort(execution_flow.steps)
        return execution_flow
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._planning_history:
            return {
                "total_plans": 0,
                "avg_complexity": 0,
                "avg_steps": 0,
            }
        
        total = len(self._planning_history)
        avg_complexity = sum(p.estimated_complexity for p in self._planning_history) / total
        avg_steps = sum(len(p.execution_plan) for p in self._planning_history) / total
        
        return {
            "total_plans": total,
            "avg_complexity": round(avg_complexity, 1),
            "avg_steps": round(avg_steps, 1),
        }

    # ==================== Task 7.2: 委派模式只读计划生成 ====================

    async def generate_execution_plan(
        self,
        user_task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """
        在委派模式下生成执行计划（只读模式，不执行任何子任务）。

        分析用户任务，复用现有的任务分析逻辑，生成包含子任务列表、
        依赖关系图、角色分配、资源估算和波次预览的 ExecutionPlan。
        返回的计划处于 DRAFT 状态，需要确认后才能执行。

        Args:
            user_task: 用户原始任务描述
            context: 可选的上下文信息

        Returns:
            ExecutionPlan: 处于 DRAFT 状态的执行计划
        """
        # 阶段 1: 快速理解任务并评估复杂度
        quick_result = await self._quick_understand_task(user_task, context)
        complexity = quick_result.get("complexity", 5)
        quick_understanding = quick_result.get("understanding", user_task[:100])

        # 阶段 2: 深度分析
        task_analysis = await self._delegate_analysis(user_task, quick_understanding)

        # 阶段 3: 背景调研（仅复杂度 >= 5 时）
        if self._config.enable_research and complexity >= 5:
            research = await self._delegate_research(user_task, task_analysis)
        else:
            research = ""

        # 阶段 4: 改写任务
        refined_task = await self._rewrite_task(user_task, task_analysis, research)

        # 阶段 5: 制定执行计划（复用现有逻辑）
        execution_plan_data = await self._create_execution_plan(
            refined_task, task_analysis, research
        )

        # 从执行计划数据中提取步骤，转换为 SubTask 列表
        steps = execution_plan_data.get("steps", [])
        subtasks: List[SubTask] = []
        dependency_graph: Dict[str, set] = {}
        agent_assignments: Dict[str, str] = {}

        task_id = f"plan_{int(time.time() * 1000)}"

        for step in steps:
            step_id = step.get("step_id", f"step_{step.get('step_number', 1)}")
            deps = set(step.get("dependencies", []))
            role = step.get("agent_type", "general")

            subtask = SubTask(
                id=step_id,
                parent_task_id=task_id,
                content=step.get("description", step.get("name", "")),
                role_hint=role,
                dependencies=deps,
                priority=step.get("step_number", 0),
                estimated_complexity=complexity / max(len(steps), 1),
            )
            subtasks.append(subtask)
            dependency_graph[step_id] = deps
            agent_assignments[step_id] = role

        # 构建波次预览（按依赖关系分层）
        wave_preview = self._build_wave_preview(subtasks, dependency_graph)

        # 估算资源消耗
        estimated_token_usage, estimated_execution_time = self._estimate_resources(
            subtasks, complexity, dependency_graph
        )

        plan = ExecutionPlan(
            task_id=task_id,
            subtasks=subtasks,
            dependency_graph=dependency_graph,
            agent_assignments=agent_assignments,
            estimated_token_usage=estimated_token_usage,
            estimated_execution_time=estimated_execution_time,
            wave_preview=wave_preview,
            created_at=time.time(),
            status=PlanStatus.DRAFT,
        )

        return plan

    def _estimate_resources(
        self,
        subtasks: List[SubTask],
        complexity: float,
        dependency_graph: Dict[str, set],
    ) -> tuple:
        """
        估算任务的资源消耗。

        基于子任务数量、复杂度和依赖关系估算 token 用量和执行时间。

        Args:
            subtasks: 子任务列表
            complexity: 任务整体复杂度 (1-10)
            dependency_graph: 依赖关系图

        Returns:
            (estimated_token_usage, estimated_execution_time) 元组
        """
        # Token 用量估算
        base_tokens_per_subtask = 500
        total_tokens = 0
        for subtask in subtasks:
            complexity_multiplier = max(1.0, subtask.estimated_complexity)
            total_tokens += int(base_tokens_per_subtask * complexity_multiplier)

        # 加上协调开销（复杂度越高，协调开销越大）
        coordination_overhead = int(len(subtasks) * 100 * (complexity / 5.0))
        total_tokens += coordination_overhead

        # 执行时间估算（秒）
        base_time_per_subtask = 30.0  # 每个子任务基础执行时间
        wave_preview = self._build_wave_preview(subtasks, dependency_graph)
        num_waves = max(len(wave_preview), 1)

        # 每个波次内的任务并行执行，波次之间串行
        total_time = 0.0
        for wave in wave_preview:
            # 波次内最长的子任务决定该波次的时间
            max_subtask_time = 0.0
            for task_id in wave:
                matching = [s for s in subtasks if s.id == task_id]
                if matching:
                    subtask_time = base_time_per_subtask * max(1.0, matching[0].estimated_complexity)
                    max_subtask_time = max(max_subtask_time, subtask_time)
                else:
                    max_subtask_time = max(max_subtask_time, base_time_per_subtask)
            total_time += max_subtask_time

        return total_tokens, total_time

    def _build_wave_preview(
        self,
        subtasks: List[SubTask],
        dependency_graph: Dict[str, set],
    ) -> List[List[str]]:
        """
        根据依赖关系构建波次预览（拓扑分层）。

        将子任务按依赖关系分组为可并行执行的波次。
        无依赖的任务在第一波，依赖第一波的在第二波，以此类推。

        Args:
            subtasks: 子任务列表
            dependency_graph: 依赖关系图

        Returns:
            波次预览列表，每个元素是该波次中的任务 ID 列表
        """
        if not subtasks:
            return []

        all_ids = {s.id for s in subtasks}
        remaining = set(all_ids)
        completed: set = set()
        waves: List[List[str]] = []

        while remaining:
            # 找出所有依赖已满足的任务
            current_wave = []
            for task_id in list(remaining):
                deps = dependency_graph.get(task_id, set())
                # 只考虑存在于当前任务集中的依赖
                effective_deps = deps & all_ids
                if effective_deps.issubset(completed):
                    current_wave.append(task_id)

            if not current_wave:
                # 防止无限循环（存在循环依赖时），将剩余任务放入最后一波
                current_wave = list(remaining)

            waves.append(sorted(current_wave))
            completed.update(current_wave)
            remaining -= set(current_wave)

        return waves
