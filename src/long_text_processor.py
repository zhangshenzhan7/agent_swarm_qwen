"""Long text processing module for handling context window limits."""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Awaitable
from enum import Enum

from .qwen.models import QwenModel


class ChunkingStrategy(Enum):
    """分块策略"""
    FIXED_SIZE = "fixed_size"           # 固定大小分块
    SENTENCE_BASED = "sentence_based"   # 基于句子分块
    PARAGRAPH_BASED = "paragraph_based" # 基于段落分块
    SEMANTIC = "semantic"               # 语义分块（保持语义完整性）


@dataclass
class TextChunk:
    """文本块"""
    index: int
    content: str
    start_position: int
    end_position: int
    token_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "index": self.index,
            "content": self.content,
            "start_position": self.start_position,
            "end_position": self.end_position,
            "token_count": self.token_count,
            "metadata": self.metadata,
        }


@dataclass
class ChunkResult:
    """分块处理结果"""
    chunk_index: int
    success: bool
    output: Any
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "chunk_index": self.chunk_index,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


@dataclass
class MergedResult:
    """合并后的结果"""
    success: bool
    final_output: Any
    chunk_results: List[ChunkResult]
    total_chunks: int
    successful_chunks: int
    failed_chunks: int
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "success": self.success,
            "final_output": self.final_output,
            "chunk_results": [cr.to_dict() for cr in self.chunk_results],
            "total_chunks": self.total_chunks,
            "successful_chunks": self.successful_chunks,
            "failed_chunks": self.failed_chunks,
        }


# 模型上下文窗口限制（token 数）
MODEL_CONTEXT_LIMITS: Dict[QwenModel, int] = {
    QwenModel.QWEN_TURBO: 8000,
    QwenModel.QWEN_PLUS: 32000,
    QwenModel.QWEN_MAX: 32000,
    QwenModel.QWEN_MAX_LONGCONTEXT: 1000000,  # 100万 token
    QwenModel.QWEN_LOCAL: 8000,
    QwenModel.QWEN2_5_72B: 128000,
    QwenModel.QWEN2_5_32B: 128000,
    QwenModel.QWEN2_5_14B: 128000,
    QwenModel.QWEN2_5_7B: 128000,
    # Qwen 3 系列
    QwenModel.QWEN3_MAX: 32000,
    QwenModel.QWEN3_MAX_PREVIEW: 32000,
}

# 默认安全边际（预留给系统提示和响应的 token）
DEFAULT_SAFETY_MARGIN = 2000


@dataclass
class LongTextConfig:
    """长文本处理配置"""
    model: QwenModel = QwenModel.QWEN_PLUS
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.SEMANTIC
    overlap_tokens: int = 200  # 块之间的重叠 token 数
    safety_margin: int = DEFAULT_SAFETY_MARGIN
    max_retries: int = 2
    
    @property
    def context_limit(self) -> int:
        """获取模型上下文限制"""
        return MODEL_CONTEXT_LIMITS.get(self.model, 8000)
    
    @property
    def effective_chunk_size(self) -> int:
        """获取有效的块大小（扣除安全边际）"""
        return self.context_limit - self.safety_margin



class LongTextProcessor:
    """长文本处理器"""
    
    def __init__(self, config: Optional[LongTextConfig] = None):
        """
        初始化长文本处理器
        
        Args:
            config: 长文本处理配置
        """
        self._config = config or LongTextConfig()
    
    # ==================== 文本长度检测 ====================
    
    def estimate_token_count(self, text: str) -> int:
        """
        估算文本的 token 数量
        
        使用简单的启发式方法：
        - 中文：约 1.5 字符/token
        - 英文：约 4 字符/token
        - 混合文本：取加权平均
        
        Args:
            text: 输入文本
            
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        
        # 统计中文字符数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        # 统计英文单词数
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        # 统计数字
        numbers = len(re.findall(r'\d+', text))
        # 统计标点符号
        punctuation = len(re.findall(r'[^\w\s]', text))
        
        # 估算 token 数
        chinese_tokens = chinese_chars / 1.5
        english_tokens = english_words * 1.3  # 平均每个单词约 1.3 token
        number_tokens = numbers * 0.5
        punct_tokens = punctuation * 0.5
        
        total = chinese_tokens + english_tokens + number_tokens + punct_tokens
        
        # 添加一些缓冲
        return int(total * 1.1)
    
    def needs_chunking(self, text: str) -> bool:
        """
        检测文本是否需要分块处理
        
        Args:
            text: 输入文本
            
        Returns:
            是否需要分块
        """
        token_count = self.estimate_token_count(text)
        return token_count > self._config.effective_chunk_size
    
    def get_text_info(self, text: str) -> Dict[str, Any]:
        """
        获取文本信息
        
        Args:
            text: 输入文本
            
        Returns:
            文本信息字典
        """
        token_count = self.estimate_token_count(text)
        effective_limit = self._config.effective_chunk_size
        
        return {
            "char_count": len(text),
            "estimated_tokens": token_count,
            "context_limit": self._config.context_limit,
            "effective_limit": effective_limit,
            "needs_chunking": token_count > effective_limit,
            "estimated_chunks": max(1, (token_count // effective_limit) + 1),
        }
    
    # ==================== 自动分块策略 ====================
    
    def chunk_text(self, text: str) -> List[TextChunk]:
        """
        将文本分块
        
        根据配置的策略自动分块。
        
        Args:
            text: 输入文本
            
        Returns:
            文本块列表
        """
        strategy = self._config.chunking_strategy
        
        if strategy == ChunkingStrategy.FIXED_SIZE:
            return self._chunk_fixed_size(text)
        elif strategy == ChunkingStrategy.SENTENCE_BASED:
            return self._chunk_by_sentences(text)
        elif strategy == ChunkingStrategy.PARAGRAPH_BASED:
            return self._chunk_by_paragraphs(text)
        elif strategy == ChunkingStrategy.SEMANTIC:
            return self._chunk_semantic(text)
        else:
            return self._chunk_fixed_size(text)
    
    def _chunk_fixed_size(self, text: str) -> List[TextChunk]:
        """固定大小分块"""
        chunks = []
        chunk_size = self._config.effective_chunk_size
        overlap = self._config.overlap_tokens
        
        # 将 token 数转换为大致的字符数
        chars_per_token = len(text) / max(1, self.estimate_token_count(text))
        char_chunk_size = int(chunk_size * chars_per_token)
        char_overlap = int(overlap * chars_per_token)
        
        start = 0
        index = 0
        
        while start < len(text):
            end = min(start + char_chunk_size, len(text))
            chunk_content = text[start:end]
            
            chunk = TextChunk(
                index=index,
                content=chunk_content,
                start_position=start,
                end_position=end,
                token_count=self.estimate_token_count(chunk_content),
            )
            chunks.append(chunk)
            
            # 下一个块的起始位置（考虑重叠）
            start = end - char_overlap if end < len(text) else end
            index += 1
        
        return chunks
    
    def _chunk_by_sentences(self, text: str) -> List[TextChunk]:
        """基于句子分块"""
        # 分割句子
        sentence_pattern = r'(?<=[。.!?！？])\s*'
        sentences = re.split(sentence_pattern, text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return self._group_into_chunks(sentences, text)
    
    def _chunk_by_paragraphs(self, text: str) -> List[TextChunk]:
        """基于段落分块"""
        # 分割段落
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        return self._group_into_chunks(paragraphs, text)
    
    def _chunk_semantic(self, text: str) -> List[TextChunk]:
        """语义分块（保持语义完整性）"""
        # 首先尝试按段落分
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        # 如果段落太少，按句子分
        if len(paragraphs) <= 1:
            sentence_pattern = r'(?<=[。.!?！？])\s*'
            units = re.split(sentence_pattern, text)
            units = [s.strip() for s in units if s.strip()]
        else:
            units = paragraphs
        
        return self._group_into_chunks(units, text)
    
    def _group_into_chunks(
        self, 
        units: List[str], 
        original_text: str
    ) -> List[TextChunk]:
        """
        将文本单元组合成块
        
        Args:
            units: 文本单元列表（句子或段落）
            original_text: 原始文本
            
        Returns:
            文本块列表
        """
        chunks = []
        current_content = []
        current_tokens = 0
        chunk_size = self._config.effective_chunk_size
        index = 0
        start_pos = 0
        
        for unit in units:
            unit_tokens = self.estimate_token_count(unit)
            
            # 如果单个单元就超过限制，需要进一步分割
            if unit_tokens > chunk_size:
                # 先保存当前累积的内容
                if current_content:
                    content = "\n".join(current_content)
                    end_pos = original_text.find(content, start_pos)
                    if end_pos == -1:
                        end_pos = start_pos + len(content)
                    else:
                        end_pos += len(content)
                    
                    chunk = TextChunk(
                        index=index,
                        content=content,
                        start_position=start_pos,
                        end_position=end_pos,
                        token_count=current_tokens,
                    )
                    chunks.append(chunk)
                    index += 1
                    start_pos = end_pos
                    current_content = []
                    current_tokens = 0
                
                # 对超长单元进行固定大小分割
                sub_chunks = self._split_long_unit(unit, start_pos, index)
                for sub_chunk in sub_chunks:
                    sub_chunk.index = index
                    chunks.append(sub_chunk)
                    index += 1
                    start_pos = sub_chunk.end_position
                
                continue
            
            # 检查是否会超过限制
            if current_tokens + unit_tokens > chunk_size and current_content:
                # 保存当前块
                content = "\n".join(current_content)
                end_pos = original_text.find(content, start_pos)
                if end_pos == -1:
                    end_pos = start_pos + len(content)
                else:
                    end_pos += len(content)
                
                chunk = TextChunk(
                    index=index,
                    content=content,
                    start_position=start_pos,
                    end_position=end_pos,
                    token_count=current_tokens,
                )
                chunks.append(chunk)
                index += 1
                start_pos = end_pos
                current_content = []
                current_tokens = 0
            
            current_content.append(unit)
            current_tokens += unit_tokens
        
        # 保存最后一个块
        if current_content:
            content = "\n".join(current_content)
            chunk = TextChunk(
                index=index,
                content=content,
                start_position=start_pos,
                end_position=len(original_text),
                token_count=current_tokens,
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_long_unit(
        self, 
        unit: str, 
        start_pos: int, 
        base_index: int
    ) -> List[TextChunk]:
        """分割超长的文本单元"""
        chunks = []
        chunk_size = self._config.effective_chunk_size
        chars_per_token = len(unit) / max(1, self.estimate_token_count(unit))
        char_chunk_size = int(chunk_size * chars_per_token)
        
        start = 0
        index = 0
        
        while start < len(unit):
            end = min(start + char_chunk_size, len(unit))
            
            # 尝试在标点处断开
            if end < len(unit):
                # 向后查找最近的标点
                for i in range(end, max(start, end - 100), -1):
                    if unit[i] in '。.!?！？，,;；':
                        end = i + 1
                        break
            
            chunk_content = unit[start:end]
            chunk = TextChunk(
                index=base_index + index,
                content=chunk_content,
                start_position=start_pos + start,
                end_position=start_pos + end,
                token_count=self.estimate_token_count(chunk_content),
            )
            chunks.append(chunk)
            
            start = end
            index += 1
        
        return chunks

    
    # ==================== 分块结果合并 ====================
    
    async def process_chunks(
        self,
        chunks: List[TextChunk],
        processor: Callable[[TextChunk], Awaitable[Any]],
    ) -> List[ChunkResult]:
        """
        处理所有文本块
        
        Args:
            chunks: 文本块列表
            processor: 处理函数
            
        Returns:
            处理结果列表
        """
        results = []
        
        for chunk in chunks:
            try:
                output = await processor(chunk)
                result = ChunkResult(
                    chunk_index=chunk.index,
                    success=True,
                    output=output,
                )
            except Exception as e:
                result = ChunkResult(
                    chunk_index=chunk.index,
                    success=False,
                    output=None,
                    error=str(e),
                )
            
            results.append(result)
        
        return results
    
    def merge_results(
        self,
        chunk_results: List[ChunkResult],
        merge_strategy: str = "concatenate",
    ) -> MergedResult:
        """
        合并分块处理结果
        
        Args:
            chunk_results: 分块处理结果列表
            merge_strategy: 合并策略
                - "concatenate": 简单拼接
                - "summarize": 汇总（需要后处理）
                - "structured": 结构化合并
            
        Returns:
            合并后的结果
        """
        successful = [r for r in chunk_results if r.success]
        failed = [r for r in chunk_results if not r.success]
        
        if merge_strategy == "concatenate":
            final_output = self._merge_concatenate(successful)
        elif merge_strategy == "structured":
            final_output = self._merge_structured(successful)
        else:
            final_output = self._merge_concatenate(successful)
        
        return MergedResult(
            success=len(failed) == 0,
            final_output=final_output,
            chunk_results=chunk_results,
            total_chunks=len(chunk_results),
            successful_chunks=len(successful),
            failed_chunks=len(failed),
        )
    
    def _merge_concatenate(self, results: List[ChunkResult]) -> str:
        """简单拼接合并"""
        # 按块索引排序
        sorted_results = sorted(results, key=lambda r: r.chunk_index)
        
        outputs = []
        for result in sorted_results:
            if result.output is not None:
                if isinstance(result.output, str):
                    outputs.append(result.output)
                else:
                    outputs.append(str(result.output))
        
        return "\n\n".join(outputs)
    
    def _merge_structured(self, results: List[ChunkResult]) -> Dict[str, Any]:
        """结构化合并"""
        sorted_results = sorted(results, key=lambda r: r.chunk_index)
        
        return {
            "chunks": [
                {
                    "index": r.chunk_index,
                    "output": r.output,
                }
                for r in sorted_results
            ],
            "total_chunks": len(results),
        }
    
    async def process_long_text(
        self,
        text: str,
        processor: Callable[[TextChunk], Awaitable[Any]],
        merge_strategy: str = "concatenate",
    ) -> MergedResult:
        """
        处理长文本的完整流程
        
        自动检测、分块、处理、合并。
        
        Args:
            text: 输入文本
            processor: 处理函数
            merge_strategy: 合并策略
            
        Returns:
            合并后的结果
        """
        # 检测是否需要分块
        if not self.needs_chunking(text):
            # 不需要分块，直接处理
            chunk = TextChunk(
                index=0,
                content=text,
                start_position=0,
                end_position=len(text),
                token_count=self.estimate_token_count(text),
            )
            
            try:
                output = await processor(chunk)
                result = ChunkResult(
                    chunk_index=0,
                    success=True,
                    output=output,
                )
            except Exception as e:
                result = ChunkResult(
                    chunk_index=0,
                    success=False,
                    output=None,
                    error=str(e),
                )
            
            return MergedResult(
                success=result.success,
                final_output=result.output,
                chunk_results=[result],
                total_chunks=1,
                successful_chunks=1 if result.success else 0,
                failed_chunks=0 if result.success else 1,
            )
        
        # 分块
        chunks = self.chunk_text(text)
        
        # 处理每个块
        chunk_results = await self.process_chunks(chunks, processor)
        
        # 合并结果
        return self.merge_results(chunk_results, merge_strategy)
    
    def get_config(self) -> LongTextConfig:
        """获取配置"""
        return self._config
    
    def set_model(self, model: QwenModel) -> None:
        """设置模型（会影响上下文限制）"""
        self._config.model = model
    
    def set_chunking_strategy(self, strategy: ChunkingStrategy) -> None:
        """设置分块策略"""
        self._config.chunking_strategy = strategy
