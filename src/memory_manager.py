"""
记忆管理模块 - 跨任务知识积累和上下文管理

基于 MEM1 驱动的记忆整合机制实现：
1. 短期记忆 - 当前任务的上下文
2. 长期记忆 - 跨任务的知识积累
3. 工作记忆 - 当前执行步骤的临时信息
4. 语义记忆 - 结构化的知识库
"""

import json
import time
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
from collections import OrderedDict


class MemoryType(Enum):
    """记忆类型"""
    SHORT_TERM = "short_term"     # 短期记忆（当前任务）
    LONG_TERM = "long_term"       # 长期记忆（跨任务）
    WORKING = "working"           # 工作记忆（当前步骤）
    SEMANTIC = "semantic"         # 语义记忆（知识库）


@dataclass
class MemoryItem:
    """记忆项"""
    id: str
    content: str
    memory_type: MemoryType
    task_id: Optional[str]
    agent_type: Optional[str]
    tags: List[str]
    importance: float  # 重要性 (0-1)
    created_at: float
    accessed_at: float
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content[:500],  # 截断长内容
            "memory_type": self.memory_type.value,
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "tags": self.tags,
            "importance": self.importance,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "access_count": self.access_count,
            "metadata": self.metadata,
        }


class MemoryManager:
    """
    记忆管理器
    
    功能：
    1. 存储和检索记忆
    2. 记忆衰减和遗忘
    3. 记忆关联和检索
    4. 知识提取和整合
    """
    
    def __init__(
        self,
        max_short_term: int = 100,      # 短期记忆容量
        max_long_term: int = 1000,      # 长期记忆容量
        max_working: int = 20,          # 工作记忆容量
        decay_rate: float = 0.1,        # 记忆衰减率
    ):
        self._max_short_term = max_short_term
        self._max_long_term = max_long_term
        self._max_working = max_working
        self._decay_rate = decay_rate
        
        # 记忆存储
        self._short_term: OrderedDict[str, MemoryItem] = OrderedDict()
        self._long_term: OrderedDict[str, MemoryItem] = OrderedDict()
        self._working: OrderedDict[str, MemoryItem] = OrderedDict()
        self._semantic: Dict[str, MemoryItem] = {}
        
        # 索引
        self._tag_index: Dict[str, List[str]] = {}  # tag -> memory_ids
        self._task_index: Dict[str, List[str]] = {}  # task_id -> memory_ids
        self._agent_index: Dict[str, List[str]] = {}  # agent_type -> memory_ids
    
    def _generate_id(self, content: str) -> str:
        """生成记忆ID"""
        hash_input = f"{content[:100]}_{time.time()}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    def _get_storage(self, memory_type: MemoryType) -> OrderedDict:
        """获取对应类型的存储"""
        if memory_type == MemoryType.SHORT_TERM:
            return self._short_term
        elif memory_type == MemoryType.LONG_TERM:
            return self._long_term
        elif memory_type == MemoryType.WORKING:
            return self._working
        else:
            return self._semantic
    
    def _get_max_capacity(self, memory_type: MemoryType) -> int:
        """获取对应类型的最大容量"""
        if memory_type == MemoryType.SHORT_TERM:
            return self._max_short_term
        elif memory_type == MemoryType.LONG_TERM:
            return self._max_long_term
        elif memory_type == MemoryType.WORKING:
            return self._max_working
        else:
            return 10000  # 语义记忆无限制
    
    def _update_index(self, memory: MemoryItem, remove: bool = False):
        """更新索引"""
        # 标签索引
        for tag in memory.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if remove:
                if memory.id in self._tag_index[tag]:
                    self._tag_index[tag].remove(memory.id)
            else:
                if memory.id not in self._tag_index[tag]:
                    self._tag_index[tag].append(memory.id)
        
        # 任务索引
        if memory.task_id:
            if memory.task_id not in self._task_index:
                self._task_index[memory.task_id] = []
            if remove:
                if memory.id in self._task_index[memory.task_id]:
                    self._task_index[memory.task_id].remove(memory.id)
            else:
                if memory.id not in self._task_index[memory.task_id]:
                    self._task_index[memory.task_id].append(memory.id)
        
        # 智能体索引
        if memory.agent_type:
            if memory.agent_type not in self._agent_index:
                self._agent_index[memory.agent_type] = []
            if remove:
                if memory.id in self._agent_index[memory.agent_type]:
                    self._agent_index[memory.agent_type].remove(memory.id)
            else:
                if memory.id not in self._agent_index[memory.agent_type]:
                    self._agent_index[memory.agent_type].append(memory.id)
    
    def store(
        self,
        content: str,
        memory_type: MemoryType,
        task_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        """
        存储记忆
        
        Args:
            content: 记忆内容
            memory_type: 记忆类型
            task_id: 关联的任务ID
            agent_type: 关联的智能体类型
            tags: 标签列表
            importance: 重要性 (0-1)
            metadata: 元数据
            
        Returns:
            存储的记忆项
        """
        memory_id = self._generate_id(content)
        now = time.time()
        
        memory = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            task_id=task_id,
            agent_type=agent_type,
            tags=tags or [],
            importance=importance,
            created_at=now,
            accessed_at=now,
            access_count=1,
            metadata=metadata or {},
        )
        
        storage = self._get_storage(memory_type)
        max_capacity = self._get_max_capacity(memory_type)
        
        # 容量管理 - 移除最旧的记忆
        while len(storage) >= max_capacity:
            oldest_id, oldest = storage.popitem(last=False)
            self._update_index(oldest, remove=True)
        
        storage[memory_id] = memory
        self._update_index(memory)
        
        return memory
    
    def retrieve(
        self,
        memory_id: str,
        memory_type: Optional[MemoryType] = None,
    ) -> Optional[MemoryItem]:
        """
        检索记忆
        
        Args:
            memory_id: 记忆ID
            memory_type: 记忆类型（可选，不指定则搜索所有类型）
            
        Returns:
            记忆项或None
        """
        if memory_type:
            storage = self._get_storage(memory_type)
            memory = storage.get(memory_id)
        else:
            # 搜索所有类型
            memory = None
            for mt in MemoryType:
                storage = self._get_storage(mt)
                if memory_id in storage:
                    memory = storage[memory_id]
                    break
        
        if memory:
            # 更新访问信息
            memory.accessed_at = time.time()
            memory.access_count += 1
        
        return memory
    
    def search_by_tags(
        self,
        tags: List[str],
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
    ) -> List[MemoryItem]:
        """
        按标签搜索记忆
        
        Args:
            tags: 标签列表
            memory_type: 记忆类型（可选）
            limit: 返回数量限制
            
        Returns:
            匹配的记忆列表
        """
        matching_ids = set()
        for tag in tags:
            if tag in self._tag_index:
                matching_ids.update(self._tag_index[tag])
        
        results = []
        for memory_id in matching_ids:
            memory = self.retrieve(memory_id, memory_type)
            if memory:
                if memory_type is None or memory.memory_type == memory_type:
                    results.append(memory)
        
        # 按重要性和访问时间排序
        results.sort(key=lambda m: (m.importance, m.accessed_at), reverse=True)
        return results[:limit]
    
    def search_by_task(
        self,
        task_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 20,
    ) -> List[MemoryItem]:
        """
        按任务ID搜索记忆
        
        Args:
            task_id: 任务ID
            memory_type: 记忆类型（可选）
            limit: 返回数量限制
            
        Returns:
            匹配的记忆列表
        """
        if task_id not in self._task_index:
            return []
        
        results = []
        for memory_id in self._task_index[task_id]:
            memory = self.retrieve(memory_id, memory_type)
            if memory:
                if memory_type is None or memory.memory_type == memory_type:
                    results.append(memory)
        
        results.sort(key=lambda m: m.created_at, reverse=True)
        return results[:limit]
    
    def search_by_agent(
        self,
        agent_type: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 20,
    ) -> List[MemoryItem]:
        """
        按智能体类型搜索记忆
        
        Args:
            agent_type: 智能体类型
            memory_type: 记忆类型（可选）
            limit: 返回数量限制
            
        Returns:
            匹配的记忆列表
        """
        if agent_type not in self._agent_index:
            return []
        
        results = []
        for memory_id in self._agent_index[agent_type]:
            memory = self.retrieve(memory_id, memory_type)
            if memory:
                if memory_type is None or memory.memory_type == memory_type:
                    results.append(memory)
        
        results.sort(key=lambda m: (m.importance, m.accessed_at), reverse=True)
        return results[:limit]
    
    def get_context_for_task(
        self,
        task_id: str,
        include_related: bool = True,
        max_items: int = 10,
    ) -> str:
        """
        获取任务的上下文信息
        
        Args:
            task_id: 任务ID
            include_related: 是否包含相关记忆
            max_items: 最大记忆数量
            
        Returns:
            格式化的上下文字符串
        """
        memories = self.search_by_task(task_id, limit=max_items)
        
        if not memories:
            return ""
        
        context_parts = ["## 相关记忆\n"]
        for m in memories:
            type_label = {
                MemoryType.SHORT_TERM: "短期",
                MemoryType.LONG_TERM: "长期",
                MemoryType.WORKING: "工作",
                MemoryType.SEMANTIC: "知识",
            }.get(m.memory_type, "未知")
            
            context_parts.append(f"### [{type_label}] {m.tags[:3] if m.tags else '无标签'}")
            context_parts.append(f"{m.content[:300]}...")
            context_parts.append("")
        
        return "\n".join(context_parts)
    
    def promote_to_long_term(
        self,
        memory_id: str,
        importance_boost: float = 0.2,
    ) -> Optional[MemoryItem]:
        """
        将短期记忆提升为长期记忆
        
        Args:
            memory_id: 记忆ID
            importance_boost: 重要性提升值
            
        Returns:
            提升后的记忆项
        """
        memory = self.retrieve(memory_id, MemoryType.SHORT_TERM)
        if not memory:
            return None
        
        # 从短期记忆中移除
        self._update_index(memory, remove=True)
        del self._short_term[memory_id]
        
        # 更新属性
        memory.memory_type = MemoryType.LONG_TERM
        memory.importance = min(1.0, memory.importance + importance_boost)
        
        # 添加到长期记忆
        self._long_term[memory_id] = memory
        self._update_index(memory)
        
        return memory
    
    def clear_working_memory(self):
        """清空工作记忆"""
        for memory in list(self._working.values()):
            self._update_index(memory, remove=True)
        self._working.clear()
    
    def clear_task_memory(self, task_id: str):
        """清空特定任务的记忆"""
        if task_id not in self._task_index:
            return
        
        memory_ids = self._task_index[task_id].copy()
        for memory_id in memory_ids:
            for mt in MemoryType:
                storage = self._get_storage(mt)
                if memory_id in storage:
                    memory = storage[memory_id]
                    self._update_index(memory, remove=True)
                    del storage[memory_id]
                    break
    
    def decay_memories(self):
        """
        记忆衰减 - 降低长时间未访问记忆的重要性
        """
        now = time.time()
        decay_threshold = 3600  # 1小时
        
        for storage in [self._short_term, self._long_term]:
            for memory in storage.values():
                time_since_access = now - memory.accessed_at
                if time_since_access > decay_threshold:
                    decay_factor = 1 - (self._decay_rate * (time_since_access / decay_threshold))
                    memory.importance *= max(0.1, decay_factor)
    
    def extract_knowledge(
        self,
        content: str,
        task_id: Optional[str] = None,
    ) -> List[str]:
        """
        从内容中提取知识点
        
        Args:
            content: 内容
            task_id: 任务ID
            
        Returns:
            提取的知识点列表
        """
        # 简单的知识提取（可以用 LLM 增强）
        knowledge_points = []
        
        # 提取关键句子（包含关键词的句子）
        key_indicators = [
            "是", "为", "指", "包括", "分为", "属于",
            "定义", "概念", "原理", "方法", "步骤",
            "结论", "发现", "表明", "证明", "显示",
        ]
        
        sentences = content.replace("\n", " ").split("。")
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and any(ind in sentence for ind in key_indicators):
                knowledge_points.append(sentence)
        
        return knowledge_points[:10]  # 最多10个知识点
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        return {
            "short_term_count": len(self._short_term),
            "long_term_count": len(self._long_term),
            "working_count": len(self._working),
            "semantic_count": len(self._semantic),
            "total_tags": len(self._tag_index),
            "total_tasks": len(self._task_index),
            "total_agents": len(self._agent_index),
        }
