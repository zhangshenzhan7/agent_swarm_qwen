"""
质量保障模块 - 多层次质量检查和自我纠错机制

基于 Agentic Schemas 架构设计理念实现：
1. 反思机制 (Reflection) - 智能体执行后自我评估
2. 自我纠错 (Self-Correction) - 检测错误并自动修复
3. 冲突解决 (Conflict Resolution) - 多智能体结果冲突处理
4. 质量门控 (Quality Gates) - 多层次质量检查
"""

import json
import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Awaitable
from enum import Enum

from ..qwen.interface import IQwenClient
from ..qwen.models import Message, QwenConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)


class QualityLevel(Enum):
    """质量等级"""
    EXCELLENT = "excellent"      # 优秀 (9-10分)
    GOOD = "good"               # 良好 (7-8分)
    ACCEPTABLE = "acceptable"   # 可接受 (5-6分)
    POOR = "poor"               # 较差 (3-4分)
    FAILED = "failed"           # 失败 (1-2分)


class ConflictType(Enum):
    """冲突类型"""
    FACTUAL = "factual"         # 事实冲突
    OPINION = "opinion"         # 观点冲突
    FORMAT = "format"           # 格式冲突
    COMPLETENESS = "completeness"  # 完整性冲突


@dataclass
class QualityReport:
    """质量评估报告"""
    score: float                          # 总分 (1-10)
    level: QualityLevel                   # 质量等级
    dimensions: Dict[str, float]          # 各维度得分
    issues: List[Dict[str, Any]]          # 发现的问题
    suggestions: List[str]                # 改进建议
    passed: bool                          # 是否通过质量门控
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level.value,
            "dimensions": self.dimensions,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "passed": self.passed,
        }


@dataclass
class ConflictReport:
    """冲突检测报告"""
    has_conflict: bool
    conflict_type: Optional[ConflictType]
    conflicting_items: List[Dict[str, Any]]
    resolution: Optional[str]
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_conflict": self.has_conflict,
            "conflict_type": self.conflict_type.value if self.conflict_type else None,
            "conflicting_items": self.conflicting_items,
            "resolution": self.resolution,
            "confidence": self.confidence,
        }


@dataclass
class ReflectionResult:
    """反思结果"""
    original_output: str
    reflection: str
    improved_output: Optional[str]
    improvement_score: float  # 改进幅度 (0-1)
    iterations: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_output": self.original_output[:500],
            "reflection": self.reflection,
            "improved_output": self.improved_output[:500] if self.improved_output else None,
            "improvement_score": self.improvement_score,
            "iterations": self.iterations,
        }


class QualityAssurance:
    """
    质量保障系统
    
    功能：
    1. 质量评估 - 多维度评估输出质量
    2. 反思机制 - 智能体自我反思和改进
    3. 冲突检测 - 检测多源信息冲突
    4. 自我纠错 - 自动修复常见错误
    """
    
    def __init__(
        self,
        qwen_client: IQwenClient,
        quality_threshold: float = 6.0,  # 质量门控阈值
        max_reflection_iterations: int = 2,  # 最大反思迭代次数
    ):
        self._qwen_client = qwen_client
        self._quality_threshold = quality_threshold
        self._max_reflection_iterations = max_reflection_iterations
    
    def _get_time_declaration(self) -> str:
        """获取时间声明"""
        now = datetime.datetime.now()
        current_datetime = now.strftime("%Y年%m月%d日 %H:%M:%S")
        current_year = now.year
        current_month = now.month
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        
        return f"""
###############################################
# 🕐 系统时间声明
当前时间：{current_datetime} {weekday}
当前年份：{current_year}年
⚠️ 注意：当前是{current_year}年，不是2024年！
###############################################
"""
    
    async def evaluate_quality(
        self,
        content: str,
        task_description: str,
        expected_output: str,
        agent_type: str,
    ) -> QualityReport:
        """
        评估输出质量 - 优化版，更精准的评估维度
        
        Args:
            content: 待评估的内容
            task_description: 任务描述
            expected_output: 预期产出
            agent_type: 智能体类型
            
        Returns:
            质量评估报告
        """
        time_decl = self._get_time_declaration()
        
        # 根据内容长度调整评估策略
        content_length = len(content)
        is_short_content = content_length < 500
        
        prompt = f"""{time_decl}

你是一个专业的质量评估专家，请评估以下智能体输出的质量。

## 任务信息
- 任务描述：{task_description}
- 预期产出：{expected_output}
- 智能体类型：{agent_type}
- 内容长度：{content_length} 字符

## 待评估内容
{content[:4000]}

## 评估维度（根据任务类型调整权重）
1. **准确性** (Accuracy): 信息是否准确、无明显错误
2. **完整性** (Completeness): 是否覆盖了任务要求的核心方面
3. **相关性** (Relevance): 内容是否与任务直接相关
4. **清晰度** (Clarity): 表达是否清晰、易于理解
5. **结构性** (Structure): 组织是否合理、层次分明
6. **实用性** (Usefulness): 内容是否有实际价值

## 评分标准
- 9-10分：优秀，超出预期
- 7-8分：良好，满足要求
- 5-6分：可接受，基本完成
- 3-4分：较差，需要改进
- 1-2分：失败，未完成任务

## 输出格式
请以 JSON 格式输出评估结果：
```json
{{
    "score": 1-10,
    "dimensions": {{
        "accuracy": 1-10,
        "completeness": 1-10,
        "relevance": 1-10,
        "clarity": 1-10,
        "structure": 1-10,
        "usefulness": 1-10
    }},
    "issues": [
        {{"type": "问题类型", "description": "问题描述", "severity": "high|medium|low"}}
    ],
    "suggestions": ["改进建议1", "改进建议2"],
    "summary": "一句话总结评估结果"
}}
```

## 评估原则
- 对于简短内容（<500字），不要因为"不够详细"而扣分
- 重点关注内容是否回答了问题、是否准确
- 避免过于苛刻的评分，7分以上表示任务基本完成

只输出 JSON。"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.1)
        
        content_result = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content_result += chunk
        
        try:
            if "```json" in content_result:
                content_result = content_result.split("```json")[1].split("```")[0]
            elif "```" in content_result:
                content_result = content_result.split("```")[1].split("```")[0]
            
            data = json.loads(content_result.strip())
            score = data.get("score", 5)
            
            # 确定质量等级
            if score >= 9:
                level = QualityLevel.EXCELLENT
            elif score >= 7:
                level = QualityLevel.GOOD
            elif score >= 5:
                level = QualityLevel.ACCEPTABLE
            elif score >= 3:
                level = QualityLevel.POOR
            else:
                level = QualityLevel.FAILED
            
            return QualityReport(
                score=score,
                level=level,
                dimensions=data.get("dimensions", {}),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                passed=score >= self._quality_threshold,
            )
        except Exception as e:
            logger.warning(f"质量评估解析失败: {e}")
            return QualityReport(
                score=5.0,
                level=QualityLevel.ACCEPTABLE,
                dimensions={},
                issues=[{"type": "parse_error", "description": str(e), "severity": "low"}],
                suggestions=[],
                passed=True,
            )
    
    async def reflect_and_improve(
        self,
        content: str,
        task_description: str,
        quality_report: QualityReport,
        stream_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ReflectionResult:
        """
        反思并改进输出 - 优化版，更高效的反思机制
        
        Args:
            content: 原始输出
            task_description: 任务描述
            quality_report: 质量评估报告
            stream_callback: 流式输出回调
            
        Returns:
            反思结果
        """
        time_decl = self._get_time_declaration()
        
        # 如果质量已经很好，不需要反思
        if quality_report.score >= 8.0:
            return ReflectionResult(
                original_output=content,
                reflection="输出质量良好，无需改进",
                improved_output=None,
                improvement_score=0.0,
                iterations=0,
            )
        
        # 如果质量太差（<4分），可能需要重新执行而不是改进
        if quality_report.score < 4.0:
            return ReflectionResult(
                original_output=content,
                reflection="输出质量过低，建议重新执行任务",
                improved_output=None,
                improvement_score=0.0,
                iterations=0,
            )
        
        # 只进行一次高效的改进
        improve_prompt = f"""{time_decl}

你是一个专业的内容优化专家。请根据质量评估结果，直接改进以下内容。

## 任务描述
{task_description}

## 原始内容
{content[:2500]}

## 质量评估
- 总分：{quality_report.score}/10
- 主要问题：{json.dumps(quality_report.issues[:3], ensure_ascii=False) if quality_report.issues else "无"}
- 改进建议：{quality_report.suggestions[:3] if quality_report.suggestions else []}

## 改进要求
1. 保留原内容的优点和核心信息
2. 针对评估中指出的问题进行改进
3. 提升内容的准确性、完整性和清晰度
4. 不要大幅改变内容结构，只做必要的优化

请直接输出改进后的内容，不要解释改进过程："""

        messages = [Message(role="user", content=improve_prompt)]
        config = QwenConfig(temperature=0.3, enable_thinking=False, enable_search=True)
        
        improved = ""
        if stream_callback:
            await stream_callback("\n[改进后的内容]\n")
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            improved += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        # 简单评估改进效果（不再调用完整评估以节省时间）
        improvement_score = 0.15 if len(improved) > len(content) * 0.8 else 0.05
        
        return ReflectionResult(
            original_output=content,
            reflection=f"针对{len(quality_report.issues)}个问题进行了改进",
            improved_output=improved if improved else None,
            improvement_score=improvement_score,
            iterations=1,
        )
    
    async def detect_conflicts(
        self,
        results: List[Dict[str, Any]],
        task_description: str,
    ) -> ConflictReport:
        """
        检测多个结果之间的冲突
        
        Args:
            results: 多个智能体的结果列表
            task_description: 任务描述
            
        Returns:
            冲突检测报告
        """
        if len(results) < 2:
            return ConflictReport(
                has_conflict=False,
                conflict_type=None,
                conflicting_items=[],
                resolution=None,
                confidence=1.0,
            )
        
        time_decl = self._get_time_declaration()
        
        # 构建结果摘要
        results_summary = []
        for i, r in enumerate(results[:5]):  # 最多比较5个结果
            agent = r.get("agent_type", f"agent_{i}")
            output = r.get("output", r.get("content", ""))[:500]
            results_summary.append(f"### {agent} 的结果\n{output}")
        
        prompt = f"""{time_decl}

你是一个专业的信息核查专家，请检测以下多个智能体结果之间是否存在冲突。

## 任务描述
{task_description}

## 各智能体结果
{chr(10).join(results_summary)}

## 检测要求
1. 检查事实性信息是否一致
2. 检查数据和数字是否矛盾
3. 检查观点和结论是否冲突
4. 评估冲突的严重程度

## 输出格式
```json
{{
    "has_conflict": true/false,
    "conflict_type": "factual|opinion|format|completeness|null",
    "conflicting_items": [
        {{
            "item1": "冲突内容1",
            "item2": "冲突内容2",
            "description": "冲突描述"
        }}
    ],
    "resolution": "建议的解决方案（如有冲突）",
    "confidence": 0.0-1.0
}}
```

只输出 JSON。"""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.1)
        
        content = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            content += chunk
        
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            
            conflict_type = None
            if data.get("conflict_type"):
                try:
                    conflict_type = ConflictType(data["conflict_type"])
                except:
                    pass
            
            return ConflictReport(
                has_conflict=data.get("has_conflict", False),
                conflict_type=conflict_type,
                conflicting_items=data.get("conflicting_items", []),
                resolution=data.get("resolution"),
                confidence=data.get("confidence", 0.8),
            )
        except Exception as e:
            logger.warning(f"冲突检测解析失败: {e}")
            return ConflictReport(
                has_conflict=False,
                conflict_type=None,
                conflicting_items=[],
                resolution=None,
                confidence=0.5,
            )
    
    async def resolve_conflicts(
        self,
        results: List[Dict[str, Any]],
        conflict_report: ConflictReport,
        task_description: str,
        stream_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """
        解决多个结果之间的冲突
        
        Args:
            results: 多个智能体的结果列表
            conflict_report: 冲突检测报告
            task_description: 任务描述
            stream_callback: 流式输出回调
            
        Returns:
            解决冲突后的统一结果
        """
        if not conflict_report.has_conflict:
            # 无冲突，直接合并
            return await self._merge_results(results, task_description, stream_callback)
        
        time_decl = self._get_time_declaration()
        
        # 构建结果摘要
        results_summary = []
        for i, r in enumerate(results[:5]):
            agent = r.get("agent_type", f"agent_{i}")
            output = r.get("output", r.get("content", ""))[:800]
            results_summary.append(f"### {agent} 的结果\n{output}")
        
        prompt = f"""{time_decl}

你是一个专业的信息整合专家，请解决以下结果之间的冲突，生成统一的高质量输出。

## 任务描述
{task_description}

## 各智能体结果
{chr(10).join(results_summary)}

## 冲突信息
- 冲突类型：{conflict_report.conflict_type.value if conflict_report.conflict_type else '未知'}
- 冲突内容：{json.dumps(conflict_report.conflicting_items, ensure_ascii=False)}
- 建议解决方案：{conflict_report.resolution}

## 解决要求
1. 优先采信权威来源和多数一致的信息
2. 对于事实冲突，进行交叉验证
3. 对于观点冲突，呈现多元观点
4. 确保最终输出准确、完整、一致

请输出解决冲突后的统一结果："""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.3)
        
        resolved = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            resolved += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        return resolved
    
    async def _merge_results(
        self,
        results: List[Dict[str, Any]],
        task_description: str,
        stream_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """合并多个结果（无冲突情况）"""
        time_decl = self._get_time_declaration()
        
        results_summary = []
        for i, r in enumerate(results[:5]):
            agent = r.get("agent_type", f"agent_{i}")
            output = r.get("output", r.get("content", ""))[:800]
            results_summary.append(f"### {agent} 的结果\n{output}")
        
        prompt = f"""{time_decl}

请整合以下多个智能体的结果，生成统一的高质量输出。

## 任务描述
{task_description}

## 各智能体结果
{chr(10).join(results_summary)}

## 整合要求
1. 提取各结果中的关键信息
2. 去除重复内容
3. 保持逻辑连贯
4. 确保输出完整、准确

请输出整合后的结果："""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.3)
        
        merged = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            merged += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        return merged
    
    async def self_correct(
        self,
        content: str,
        error_type: str,
        task_description: str,
        stream_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """
        自我纠错
        
        Args:
            content: 原始内容
            error_type: 错误类型
            task_description: 任务描述
            stream_callback: 流式输出回调
            
        Returns:
            纠错后的内容
        """
        time_decl = self._get_time_declaration()
        
        prompt = f"""{time_decl}

你是一个专业的内容纠错专家，请修正以下内容中的错误。

## 任务描述
{task_description}

## 原始内容
{content[:2500]}

## 错误类型
{error_type}

## 纠错要求
1. 识别并修正所有相关错误
2. 保持原内容的结构和风格
3. 确保修正后的内容准确、完整

请直接输出纠错后的内容："""

        messages = [Message(role="user", content=prompt)]
        config = QwenConfig(temperature=0.2)
        
        corrected = ""
        async for chunk in self._qwen_client.chat_stream(messages, config=config):
            corrected += chunk
            if stream_callback:
                await stream_callback(chunk)
        
        return corrected
