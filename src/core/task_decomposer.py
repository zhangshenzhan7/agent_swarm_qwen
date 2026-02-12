"""Task Decomposer implementation."""

import re
import uuid
import json
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

from ..interfaces.task_decomposer import ITaskDecomposer
from ..models.task import Task, SubTask, TaskDecomposition
from ..models.agent import PREDEFINED_ROLES
from ..qwen import IQwenClient, Message, QwenConfig


# 复杂度关键词权重
COMPLEXITY_KEYWORDS = {
    # 高复杂度关键词
    "研究": 2.0, "分析": 1.5, "比较": 1.5, "综合": 2.0, "评估": 1.5,
    "设计": 2.0, "开发": 2.0, "实现": 1.5, "优化": 1.5, "重构": 1.5,
    "调研": 1.5, "报告": 1.0, "总结": 1.0, "翻译": 1.0,
    "对比": 1.5, "对比分析": 2.0, "选型": 1.5, "建议": 1.0,
    "维度": 1.0, "场景": 1.0, "趋势": 1.5, "预测": 1.5,
    "research": 2.0, "analyze": 1.5, "compare": 1.5, "synthesize": 2.0,
    "evaluate": 1.5, "design": 2.0, "develop": 2.0, "implement": 1.5,
    "optimize": 1.5, "refactor": 1.5, "investigate": 1.5,
    # 数量词
    "多个": 1.0, "所有": 1.5, "每个": 1.0, "各种": 1.0,
    "multiple": 1.0, "all": 1.5, "each": 1.0, "various": 1.0,
    # 范围词
    "全面": 1.5, "详细": 1.0, "深入": 1.5, "系统": 1.5,
    "comprehensive": 1.5, "detailed": 1.0, "in-depth": 1.5, "systematic": 1.5,
}

# 角色关键词映射
ROLE_KEYWORDS = {
    "searcher": ["搜索", "查找", "检索", "收集", "search", "find", "collect", "gather"],
    "analyst": ["分析", "数据", "统计", "趋势", "analyze", "data", "statistics", "trend"],
    "fact_checker": ["核实", "验证", "确认", "事实", "verify", "validate", "confirm", "fact"],
    "writer": ["撰写", "编写", "文档", "报告", "write", "document", "report", "draft"],
    "translator": ["翻译", "转换", "语言", "translate", "convert", "language"],
    "coder": ["代码", "编程", "开发", "实现", "code", "program", "develop", "implement"],
    "researcher": ["研究", "调研", "学术", "论文", "research", "study", "academic", "paper"],
    "summarizer": ["总结", "摘要", "概括", "归纳", "summarize", "summary", "abstract", "conclude"],
}


class TaskDecomposer(ITaskDecomposer):
    """任务分解器实现"""
    
    def __init__(
        self,
        qwen_client: Optional[IQwenClient] = None,
        complexity_threshold: float = 3.0,
    ):
        """
        初始化任务分解器
        
        Args:
            qwen_client: Qwen 客户端，用于智能分解
            complexity_threshold: 复杂度阈值，超过此值才进行分解
        """
        self._qwen_client = qwen_client
        self._complexity_threshold = complexity_threshold
    
    async def analyze_complexity(self, task: Task) -> float:
        """
        分析任务复杂度
        
        基于以下因素评估：
        1. 任务内容长度
        2. 关键词权重
        3. 句子数量
        4. 问号数量（表示多个问题）
        
        Args:
            task: 待分析的任务
            
        Returns:
            复杂度评分 (0.0 - 10.0)
        """
        content = task.content.lower()
        score = 0.0
        
        # 1. 长度因素 (0-2分)
        length = len(content)
        if length > 500:
            score += 2.0
        elif length > 200:
            score += 1.5
        elif length > 100:
            score += 1.0
        elif length > 50:
            score += 0.5
        
        # 2. 关键词权重 (0-4分)
        keyword_score = 0.0
        for keyword, weight in COMPLEXITY_KEYWORDS.items():
            if keyword in content:
                keyword_score += weight
        score += min(keyword_score, 4.0)
        
        # 3. 句子数量 (0-2分)
        sentences = re.split(r'[。.!?！？]', content)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) > 5:
            score += 2.0
        elif len(sentences) > 3:
            score += 1.0
        elif len(sentences) > 1:
            score += 0.5
        
        # 4. 问号数量 (0-2分)
        question_count = content.count('?') + content.count('？')
        if question_count > 3:
            score += 2.0
        elif question_count > 1:
            score += 1.0
        elif question_count > 0:
            score += 0.5
        
        # 确保分数在 0-10 范围内
        return min(max(score, 0.0), 10.0)
    
    async def decompose(self, task: Task) -> TaskDecomposition:
        """
        分解任务为子任务
        
        如果有 Qwen 客户端，使用 AI 进行智能分解；
        否则使用基于规则的简单分解。
        
        Args:
            task: 待分解的任务
            
        Returns:
            任务分解结果
        """
        # 分析复杂度
        complexity = await self.analyze_complexity(task)
        
        # 如果复杂度低于阈值，不分解
        if complexity < self._complexity_threshold:
            # 根据任务内容选择合适角色
            role_hint = self._suggest_single_role(task.content)
            subtask = SubTask(
                id=str(uuid.uuid4()),
                parent_task_id=task.id,
                content=task.content,
                role_hint=role_hint,
                dependencies=set(),
                priority=0,
                estimated_complexity=complexity,
            )
            return TaskDecomposition(
                original_task_id=task.id,
                subtasks=[subtask],
                execution_order=[[subtask.id]],
                total_estimated_time=complexity * 10,  # 估算时间
            )
        
        # 使用 AI 或规则进行分解
        if self._qwen_client:
            # AI 分解已在 prompt 中处理了角色分配和依赖关系，不再覆盖
            subtasks = await self._ai_decompose(task)
        else:
            subtasks = await self._rule_based_decompose(task)
            # 仅规则分解时需要后处理（AI 分解已自带角色和依赖）
            subtasks = await self.identify_dependencies(subtasks)
            subtasks = await self.suggest_roles(subtasks)
        
        # 计算执行顺序
        execution_order = self._compute_execution_order(subtasks)
        
        # 估算总时间
        total_time = sum(st.estimated_complexity * 10 for st in subtasks)
        
        return TaskDecomposition(
            original_task_id=task.id,
            subtasks=subtasks,
            execution_order=execution_order,
            total_estimated_time=total_time,
        )
    
    async def _ai_decompose(self, task: Task) -> List[SubTask]:
        """使用 AI 进行任务分解 - 优化版"""
        import datetime
        
        # 获取当前日期时间
        now = datetime.datetime.now()
        current_datetime = now.strftime("%Y年%m月%d日 %H:%M:%S")
        current_year = now.year
        current_month = now.month
        current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        
        system_prompt = f"""你是一个专业的任务分解专家，负责将复杂任务分解为可执行的子任务。

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
- ⚠️ 但如果原始任务中明确指定了年份（如"2025年"），则子任务描述必须保留该年份，不得替换为当前系统年份
###############################################

## 分解原则
1. **灵活分解**：子任务数量控制在 3-12 个，不宜过多导致输出碎片化
2. **独立性原则**：每个子任务应尽量独立，减少依赖
3. **并行优先**：能并行的任务不要串行
4. **明确性原则**：子任务描述要具体、可执行
5. **时间基准**：默认以{current_year}年{current_month}月为当前时间，但若原始任务明确指定年份（如"2025年"），则子任务必须使用任务指定年份，不得替换
6. **主题聚焦**：所有子任务必须严格围绕原始任务的核心主题，禁止引入无关领域内容。搜索任务必须明确限定搜索范围在原始任务涉及的主题内
7. **完整交付**：最后一个子任务必须是"撰写完整综合报告"（角色为writer），要求整合所有前序子任务结果，产出单份结构化最终交付物（含决策矩阵/对比表格）
8. **去重原则**：不同子任务之间内容不得重叠。如"搜索A的X数据"和"搜索A的Y数据"应合并为"搜索A的X和Y数据"
9. **显式对象**：每个子任务描述中必须明确列出原始任务涉及的具体对象名称，禁止用泛称（如"相关框架"）替代具体名称（如"React、Vue、Angular"）

## 角色分配指南
- **searcher**（搜索员）：需要搜索信息、收集资料时使用
- **fact_checker**（核查员）：需要验证信息真实性时使用
- **analyst**（分析师）：需要数据分析、趋势分析时使用
- **researcher**（研究员）：需要深度研究、综合分析时使用
- **writer**（撰稿员）：需要撰写报告、文档时使用
- **coder**（程序员）：需要编写代码、技术实现时使用
- **translator**（翻译员）：需要翻译内容时使用
- **summarizer**（总结员）：需要总结归纳时使用

## 依赖关系设置
- 只有当后续任务必须使用前序任务的输出时才设置依赖
- 搜索类任务通常可以并行
- 分析/写作任务通常依赖搜索结果
- 总结任务通常放在最后

## 输出格式
请以 JSON 格式返回：
```json
{{
    "subtasks": [
        {{
            "content": "具体的子任务描述（清晰、可执行，涉及时间时以{current_year}年{current_month}月为当前时间）",
            "role_hint": "searcher|fact_checker|analyst|researcher|writer|coder|translator|summarizer",
            "dependencies": [],
            "priority": 5,
            "estimated_complexity": 3.0
        }}
    ]
}}
```

## 示例
任务："研究人工智能在医疗领域的应用现状和发展趋势"
分解：
1. [searcher] 搜索AI医疗应用的最新案例和数据 (无依赖, 优先级5)
2. [searcher] 搜索AI医疗的政策法规和市场规模 (无依赖, 优先级5)
3. [analyst] 分析AI医疗的应用场景和发展趋势 (依赖1,2, 优先级4)
4. [writer] 撰写研究报告 (依赖3, 优先级3)

只输出 JSON，不要其他内容。记住：当前是{current_year}年{current_month}月！"""
        
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=f"请分解以下任务（根据复杂度分解为3-12个子任务，优先并行）：\n\n{task.content}"),
        ]
        
        try:
            response = await self._qwen_client.chat(messages)
            result = self._parse_decomposition_response(response.content, task.id)
            # 限制子任务数量
            if len(result) > 12:
                result = result[:12]
            return result
        except Exception:
            # AI 分解失败，回退到规则分解
            return await self._rule_based_decompose(task)
    
    def _parse_decomposition_response(
        self, response: str, task_id: str
    ) -> List[SubTask]:
        """解析 AI 分解响应"""
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            raise ValueError("No JSON found in response")
        
        data = json.loads(json_match.group())
        subtasks_data = data.get("subtasks", [])
        
        if not subtasks_data:
            raise ValueError("No subtasks in response")
        
        # 创建子任务
        subtasks = []
        subtask_ids = []
        
        for i, st_data in enumerate(subtasks_data):
            subtask_id = str(uuid.uuid4())
            subtask_ids.append(subtask_id)
            
            subtask = SubTask(
                id=subtask_id,
                parent_task_id=task_id,
                content=st_data.get("content", ""),
                role_hint=st_data.get("role_hint", "searcher"),
                dependencies=set(),  # 稍后处理
                priority=st_data.get("priority", 0),
                estimated_complexity=st_data.get("estimated_complexity", 1.0),
            )
            subtasks.append(subtask)
        
        # 处理依赖关系
        for i, st_data in enumerate(subtasks_data):
            dep_indices = st_data.get("dependencies", [])
            for dep_idx in dep_indices:
                if 0 <= dep_idx < len(subtask_ids) and dep_idx != i:
                    subtasks[i].dependencies.add(subtask_ids[dep_idx])
        
        return subtasks
    
    async def _rule_based_decompose(self, task: Task) -> List[SubTask]:
        """基于规则的任务分解"""
        content = task.content
        subtasks = []
        
        # 按句子分割
        sentences = re.split(r'[。.!?！？]', content)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
        
        if len(sentences) <= 1:
            # 单句任务，尝试按逗号分割
            parts = re.split(r'[，,、]', content)
            parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]
            
            if len(parts) > 1:
                sentences = parts
        
        # 为每个部分创建子任务
        for i, sentence in enumerate(sentences):
            subtask = SubTask(
                id=str(uuid.uuid4()),
                parent_task_id=task.id,
                content=sentence,
                role_hint="searcher",
                dependencies=set(),
                priority=len(sentences) - i,  # 前面的优先级更高
                estimated_complexity=1.0 + len(sentence) / 100,
            )
            subtasks.append(subtask)
        
        # 如果没有分解出子任务，创建一个
        if not subtasks:
            subtask = SubTask(
                id=str(uuid.uuid4()),
                parent_task_id=task.id,
                content=content,
                role_hint="searcher",
                dependencies=set(),
                priority=0,
                estimated_complexity=2.0,
            )
            subtasks.append(subtask)
        
        return subtasks
    
    async def identify_dependencies(self, subtasks: List[SubTask]) -> List[SubTask]:
        """
        识别子任务之间的依赖关系
        
        基于关键词和语义分析识别依赖。
        """
        if len(subtasks) <= 1:
            return subtasks
        
        # 依赖关键词
        dependency_keywords = [
            "基于", "根据", "使用", "利用", "参考",
            "based on", "using", "with", "from", "after",
            "然后", "接着", "之后", "最后",
            "then", "next", "finally", "after that",
        ]
        
        for i, subtask in enumerate(subtasks):
            content_lower = subtask.content.lower()
            
            # 检查是否包含依赖关键词
            has_dependency_keyword = any(
                kw in content_lower for kw in dependency_keywords
            )
            
            if has_dependency_keyword and i > 0:
                # 添加对前一个任务的依赖
                subtask.dependencies.add(subtasks[i - 1].id)
        
        return subtasks
    
    async def suggest_roles(self, subtasks: List[SubTask]) -> List[SubTask]:
        """
        为子任务建议执行角色
        
        基于关键词匹配建议最合适的角色。
        """
        for subtask in subtasks:
            content_lower = subtask.content.lower()
            
            # 计算每个角色的匹配分数
            role_scores: Dict[str, float] = defaultdict(float)
            
            for role, keywords in ROLE_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in content_lower:
                        role_scores[role] += 1.0
            
            # 选择得分最高的角色
            if role_scores:
                best_role = max(role_scores.items(), key=lambda x: x[1])[0]
                subtask.role_hint = best_role
            else:
                # 默认使用 searcher
                subtask.role_hint = "searcher"
        
        return subtasks

    def _suggest_single_role(self, content: str) -> str:
        """为不分解的单任务选择最合适的角色"""
        content_lower = content.lower()
        role_scores: Dict[str, float] = defaultdict(float)

        for role, keywords in ROLE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in content_lower:
                    role_scores[role] += 1.0

        if role_scores:
            return max(role_scores.items(), key=lambda x: x[1])[0]
        return "researcher"
    
    def _compute_execution_order(
        self, subtasks: List[SubTask]
    ) -> List[List[str]]:
        """
        计算执行顺序（拓扑排序）
        
        返回分层的执行顺序，每层内的任务可以并行执行。
        """
        if not subtasks:
            return []
        
        # 构建依赖图
        subtask_map = {st.id: st for st in subtasks}
        in_degree: Dict[str, int] = {st.id: 0 for st in subtasks}
        dependents: Dict[str, List[str]] = defaultdict(list)
        
        for subtask in subtasks:
            for dep_id in subtask.dependencies:
                if dep_id in subtask_map:
                    in_degree[subtask.id] += 1
                    dependents[dep_id].append(subtask.id)
        
        # 拓扑排序
        execution_order = []
        remaining = set(st.id for st in subtasks)
        
        while remaining:
            # 找出所有入度为 0 的任务
            ready = [
                st_id for st_id in remaining
                if in_degree[st_id] == 0
            ]
            
            if not ready:
                # 存在循环依赖，打破循环
                ready = [min(remaining)]
            
            # 按优先级排序
            ready.sort(
                key=lambda x: subtask_map[x].priority,
                reverse=True
            )
            
            execution_order.append(ready)
            
            # 更新入度
            for st_id in ready:
                remaining.remove(st_id)
                for dependent_id in dependents[st_id]:
                    if dependent_id in remaining:
                        in_degree[dependent_id] -= 1
        
        return execution_order
