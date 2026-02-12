"""
自适应编排器 - 基于 FlashResearch 架构的实时任务编排

核心功能：
1. 自适应研究规划 - 根据任务复杂度动态调整广度和深度
2. 实时编排层 - 监控任务执行，动态调整资源分配
3. 多维度并行化 - 支持广度和深度的并行执行
4. 推测性执行 - 允许子任务在父任务完成前开始

参考：FlashResearch: Real-time Agent Orchestration for Efficient Deep Research
"""

import asyncio
import time
import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Awaitable, Set
from enum import Enum
from collections import defaultdict

from .qwen.interface import IQwenClient
from .qwen.models import Message, QwenConfig


class TaskPriority(Enum):
    """任务优先级"""
    CRITICAL = 1    # 关键路径任务
    HIGH = 2        # 高优先级
    NORMAL = 3      # 普通优先级
    LOW = 4         # 低优先级
    SPECULATIVE = 5 # 推测性任务


class OrchestrationSignal(Enum):
    """编排信号"""
    CONTINUE = "continue"       # 继续执行
    TERMINATE = "terminate"     # 终止任务
    ESCALATE = "escalate"       # 升级（需要更多资源）
    PRUNE = "prune"            # 剪枝（终止子树）
    SPECULATE = "speculate"    # 推测性执行


@dataclass
class TaskNode:
    """任务节点 - 研究树中的节点"""
    id: str
    query: str                              # 任务查询
    parent_id: Optional[str]                # 父节点ID
    depth: int                              # 深度
    priority: TaskPriority = TaskPriority.NORMAL
    status: str = "pending"                 # pending, running, completed, failed, pruned
    agent_type: str = "researcher"          # 执行智能体类型
    
    # 执行结果
    findings: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    output: Optional[str] = None
    error: Optional[str] = None
    
    # 质量评估
    goal_satisfaction: float = 0.0          # 目标满足度 [0, 1]
    quality_score: float = 0.0              # 质量分数 [0, 1]
    
    # 时间追踪
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # 子节点
    children: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "priority": self.priority.value,
            "status": self.status,
            "agent_type": self.agent_type,
            "findings": self.findings,
            "output": self.output[:500] if self.output else None,
            "error": self.error,
            "goal_satisfaction": self.goal_satisfaction,
            "quality_score": self.quality_score,
            "children": self.children,
        }


@dataclass
class OrchestrationConfig:
    """编排配置"""
    max_depth: int = 3                      # 最大深度
    max_breadth: int = 4                    # 最大广度
    flex_breadth: int = 2                   # 弹性广度（可额外扩展）
    goal_satisfaction_threshold: float = 0.8  # 目标满足阈值
    quality_threshold: float = 0.7          # 质量阈值
    evaluation_interval: float = 5.0        # 评估间隔（秒）
    enable_speculative: bool = True         # 启用推测性执行
    time_budget: float = 300.0              # 时间预算（秒）
    max_concurrent_tasks: int = 8           # 最大并发任务数


class AdaptiveOrchestrator:
    """
    自适应编排器
    
    实现 FlashResearch 的核心思想：
    1. 自适应规划：根据任务复杂度动态调整广度和深度
    2. 实时编排：监控执行状态，动态调整资源分配
    3. 多维并行：支持广度和深度的并行执行
    4. 推测性执行：允许子任务提前开始
    """
    
    def __init__(
        self,
        qwen_client: IQwenClient,
        config: Optional[OrchestrationConfig] = None,
    ):
        self._qwen_client = qwen_client
        self._config = config or OrchestrationConfig()
        
        # 任务树
        self._nodes: Dict[str, TaskNode] = {}
        self._root_id: Optional[str] = None
        
        # 任务池
        self._task_pool: asyncio.Queue = asyncio.Queue()
        self._running_tasks: Set[str] = set()
        self._completed_tasks: Set[str] = set()
        
        # 累积发现
        self._accumulated_findings: List[str] = []
        
        # 回调
        self._on_node_update: Optional[Callable[[TaskNode], Awaitable[None]]] = None
        self._on_finding: Optional[Callable[[str, str], Awaitable[None]]] = None
        
        # 统计
        self._stats = {
            "total_nodes": 0,
            "completed_nodes": 0,
            "pruned_nodes": 0,
            "speculative_hits": 0,
            "speculative_misses": 0,
        }
    
    def set_callbacks(
        self,
        on_node_update: Optional[Callable[[TaskNode], Awaitable[None]]] = None,
        on_finding: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ):
        """设置回调函数"""
        self._on_node_update = on_node_update
        self._on_finding = on_finding
    
    async def orchestrate(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行自适应编排
        
        Args:
            query: 用户查询
            context: 上下文信息
            
        Returns:
            编排结果
        """
        start_time = time.time()
        
        # 创建根节点
        root = TaskNode(
            id="root",
            query=query,
            parent_id=None,
            depth=0,
            priority=TaskPriority.CRITICAL,
            context=context or {},
        )
        self._nodes["root"] = root
        self._root_id = "root"
        self._stats["total_nodes"] = 1
        
        # 自适应规划：确定初始广度
        initial_breadth = await self._adaptive_breadth_planning(query, [])
        
        # 生成子查询
        subqueries = await self._generate_subqueries(query, initial_breadth)
        
        # 创建子节点并加入任务池
        for i, subquery in enumerate(subqueries):
            child = TaskNode(
                id=f"node_1_{i}",
                query=subquery,
                parent_id="root",
                depth=1,
                agent_type=self._select_agent_type(subquery),
            )
            self._nodes[child.id] = child
            root.children.append(child.id)
            await self._task_pool.put(child.id)
            self._stats["total_nodes"] += 1
        
        # 启动并行执行
        workers = [
            asyncio.create_task(self._worker(i))
            for i in range(min(self._config.max_concurrent_tasks, len(subqueries)))
        ]
        
        # 启动实时编排监控
        orchestrator_task = asyncio.create_task(self._orchestration_loop(start_time))
        
        # 等待所有任务完成或超时
        try:
            await asyncio.wait_for(
                self._wait_for_completion(),
                timeout=self._config.time_budget
            )
        except asyncio.TimeoutError:
            print(f"[Orchestrator] 达到时间预算 {self._config.time_budget}s")
        
        # 停止工作线程
        for _ in workers:
            await self._task_pool.put(None)
        
        orchestrator_task.cancel()
        
        # 聚合结果
        result = await self._aggregate_results()
        
        elapsed = time.time() - start_time
        result["stats"] = {
            **self._stats,
            "elapsed_time": elapsed,
            "throughput": self._stats["completed_nodes"] / elapsed if elapsed > 0 else 0,
        }
        
        return result
    
    async def _adaptive_breadth_planning(
        self,
        query: str,
        accumulated_findings: List[str],
    ) -> int:
        """
        自适应广度规划 - 根据查询复杂度确定子查询数量
        
        基于 FlashResearch 的效用模型：
        - 广泛的主题需要更多子查询
        - 具体的问题需要更少但更深入的子查询
        """
        prompt = f"""你是一个研究规划专家。请评估以下查询，确定最优的子查询数量。

## 查询
{query}

## 已有发现
{json.dumps(accumulated_findings[-5:], ensure_ascii=False) if accumulated_findings else "无"}

## 评估标准
- 广泛的主题（如"气候变化的影响"）需要 3-4 个子查询覆盖不同方面
- 具体的问题（如"Python 如何实现单例模式"）只需要 1-2 个子查询
- 避免冗余：子查询应该覆盖不同的方面，不要重复

## 输出格式
请输出一个 JSON：
```json
{{
    "complexity": "broad|moderate|specific",
    "recommended_breadth": 1-{self._config.max_breadth + self._config.flex_breadth},
    "reason": "简短理由"
}}
```

只输出 JSON。"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.1, enable_thinking=False)
        
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
        
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            data = json.loads(content.strip())
            breadth = data.get("recommended_breadth", 3)
            return min(breadth, self._config.max_breadth + self._config.flex_breadth)
        except:
            return 3  # 默认广度
    
    async def _generate_subqueries(self, query: str, breadth: int) -> List[str]:
        """生成子查询"""
        if breadth <= 1:
            return [query]
        
        prompt = f"""请将以下查询分解为 {breadth} 个独立的子查询，每个子查询覆盖不同的方面。

## 原始查询
{query}

## 要求
1. 每个子查询应该清晰、具体
2. 子查询之间不要重叠
3. 覆盖查询的主要方面

## 输出格式
```json
{{
    "subqueries": ["子查询1", "子查询2", ...]
}}
```

只输出 JSON。"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.3, enable_thinking=False)
        
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
        
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            data = json.loads(content.strip())
            return data.get("subqueries", [query])[:breadth]
        except:
            return [query]
    
    def _select_agent_type(self, query: str) -> str:
        """根据查询选择智能体类型"""
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ['搜索', '查找', '最新', 'search', 'find']):
            return "searcher"
        elif any(kw in query_lower for kw in ['分析', '比较', '评估', 'analyze', 'compare']):
            return "analyst"
        elif any(kw in query_lower for kw in ['代码', '实现', '编程', 'code', 'implement']):
            return "coder"
        elif any(kw in query_lower for kw in ['总结', '概述', '摘要', 'summarize', 'summary']):
            return "summarizer"
        elif any(kw in query_lower for kw in ['撰写', '写', '报告', 'write', 'report']):
            return "writer"
        else:
            return "researcher"
    
    async def _worker(self, worker_id: int):
        """工作线程 - 从任务池获取任务并执行"""
        while True:
            node_id = await self._task_pool.get()
            if node_id is None:
                break
            
            node = self._nodes.get(node_id)
            if not node or node.status != "pending":
                continue
            
            self._running_tasks.add(node_id)
            await self._execute_node(node)
            self._running_tasks.discard(node_id)
            self._completed_tasks.add(node_id)
    
    async def _execute_node(self, node: TaskNode):
        """执行单个节点"""
        node.status = "running"
        node.started_at = time.time()
        
        if self._on_node_update:
            await self._on_node_update(node)
        
        try:
            # 构建提示词
            parent_context = ""
            if node.parent_id and node.parent_id in self._nodes:
                parent = self._nodes[node.parent_id]
                if parent.output:
                    parent_context = f"\n## 上游结果\n{parent.output[:1000]}"
            
            prompt = f"""请针对以下查询进行研究并提供详细的发现。

## 查询
{node.query}
{parent_context}

## 要求
1. 提供准确、有价值的信息
2. 结构化输出，便于后续整合
3. 标注关键发现

请直接输出研究结果。"""

            messages = [Message(role="user", content=prompt)]
            config = QwenConfig(
                temperature=0.3,
                enable_thinking=False,
                enable_search=True,
            )
            
            output = ""
            async for chunk in self._qwen_client.chat_stream(messages, config=config):
                output += chunk
            
            node.output = output
            node.status = "completed"
            node.completed_at = time.time()
            
            # 提取发现
            findings = self._extract_findings(output)
            node.findings = findings
            self._accumulated_findings.extend(findings)
            
            if self._on_finding:
                for finding in findings:
                    await self._on_finding(node.id, finding)
            
            self._stats["completed_nodes"] += 1
            
        except Exception as e:
            node.status = "failed"
            node.error = str(e)
            node.completed_at = time.time()
        
        if self._on_node_update:
            await self._on_node_update(node)
    
    def _extract_findings(self, output: str) -> List[str]:
        """从输出中提取关键发现"""
        findings = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            # 提取要点
            if line.startswith(('- ', '• ', '* ', '1.', '2.', '3.')):
                finding = line.lstrip('-•* 0123456789.').strip()
                if len(finding) > 20:
                    findings.append(finding)
        
        return findings[:10]  # 最多10个发现
    
    async def _orchestration_loop(self, start_time: float):
        """实时编排循环 - 监控执行状态并动态调整"""
        while True:
            await asyncio.sleep(self._config.evaluation_interval)
            
            elapsed = time.time() - start_time
            if elapsed >= self._config.time_budget:
                break
            
            # 评估当前状态
            for node_id in list(self._running_tasks):
                node = self._nodes.get(node_id)
                if not node:
                    continue
                
                # 评估目标满足度和质量
                if node.output:
                    signal = await self._evaluate_node(node)
                    await self._handle_signal(node, signal)
    
    async def _evaluate_node(self, node: TaskNode) -> OrchestrationSignal:
        """评估节点 - 确定编排信号"""
        if not node.output:
            return OrchestrationSignal.CONTINUE
        
        # 简化评估：基于输出长度和关键词
        output_len = len(node.output)
        has_findings = len(node.findings) > 0
        
        if output_len > 500 and has_findings:
            node.goal_satisfaction = 0.8
            node.quality_score = 0.8
            return OrchestrationSignal.CONTINUE
        elif output_len > 200:
            node.goal_satisfaction = 0.6
            node.quality_score = 0.6
            # 可能需要深入
            if node.depth < self._config.max_depth:
                return OrchestrationSignal.SPECULATE
            return OrchestrationSignal.CONTINUE
        else:
            node.goal_satisfaction = 0.3
            node.quality_score = 0.3
            return OrchestrationSignal.ESCALATE
    
    async def _handle_signal(self, node: TaskNode, signal: OrchestrationSignal):
        """处理编排信号"""
        if signal == OrchestrationSignal.TERMINATE:
            node.status = "pruned"
            self._stats["pruned_nodes"] += 1
            # 剪枝子树
            await self._prune_subtree(node.id)
        
        elif signal == OrchestrationSignal.SPECULATE and self._config.enable_speculative:
            # 推测性执行：创建子节点
            if node.depth < self._config.max_depth and len(node.children) == 0:
                await self._speculative_expand(node)
        
        elif signal == OrchestrationSignal.ESCALATE:
            # 升级：增加资源或重试
            node.priority = TaskPriority.HIGH
    
    async def _speculative_expand(self, node: TaskNode):
        """推测性扩展 - 在父节点完成前创建子节点"""
        # 基于当前发现生成子查询
        if not node.findings:
            return
        
        # 选择最有价值的发现进行深入
        top_finding = node.findings[0] if node.findings else node.query
        
        child = TaskNode(
            id=f"spec_{node.id}_{len(node.children)}",
            query=f"深入研究：{top_finding}",
            parent_id=node.id,
            depth=node.depth + 1,
            priority=TaskPriority.SPECULATIVE,
            agent_type="researcher",
        )
        
        self._nodes[child.id] = child
        node.children.append(child.id)
        await self._task_pool.put(child.id)
        self._stats["total_nodes"] += 1
    
    async def _prune_subtree(self, node_id: str):
        """剪枝子树"""
        node = self._nodes.get(node_id)
        if not node:
            return
        
        for child_id in node.children:
            child = self._nodes.get(child_id)
            if child and child.status == "pending":
                child.status = "pruned"
                self._stats["pruned_nodes"] += 1
            await self._prune_subtree(child_id)
    
    async def _wait_for_completion(self):
        """等待所有任务完成"""
        while True:
            pending = [
                n for n in self._nodes.values()
                if n.status in ("pending", "running")
            ]
            if not pending:
                break
            await asyncio.sleep(0.5)
    
    async def _aggregate_results(self) -> Dict[str, Any]:
        """聚合所有结果"""
        # 收集所有完成节点的输出
        outputs = []
        for node in self._nodes.values():
            if node.status == "completed" and node.output:
                outputs.append({
                    "query": node.query,
                    "output": node.output,
                    "depth": node.depth,
                    "agent_type": node.agent_type,
                })
        
        # 按深度排序
        outputs.sort(key=lambda x: x["depth"])
        
        return {
            "success": True,
            "outputs": outputs,
            "findings": self._accumulated_findings,
            "tree": {
                node_id: node.to_dict()
                for node_id, node in self._nodes.items()
            },
        }
    
    def get_tree_visualization(self) -> str:
        """获取树的可视化表示"""
        lines = []
        
        def visualize_node(node_id: str, prefix: str = ""):
            node = self._nodes.get(node_id)
            if not node:
                return
            
            status_icon = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "pruned": "✂️",
            }.get(node.status, "❓")
            
            lines.append(f"{prefix}{status_icon} [{node.agent_type}] {node.query[:50]}...")
            
            for i, child_id in enumerate(node.children):
                is_last = i == len(node.children) - 1
                child_prefix = prefix + ("    " if is_last else "│   ")
                visualize_node(child_id, child_prefix)
        
        if self._root_id:
            visualize_node(self._root_id)
        
        return "\n".join(lines)
