"""Tool Registry implementation."""

import asyncio
import time
import uuid
from typing import Dict, Any, List, Optional

from .interfaces.tool_registry import IToolRegistry
from .models.tool import ToolDefinition, ToolCallRecord


class ToolNotFoundError(Exception):
    """工具未找到异常"""
    pass


class ToolTimeoutError(Exception):
    """工具调用超时异常"""
    pass


class ToolRegistry(IToolRegistry):
    """工具注册表实现"""
    
    def __init__(self, default_timeout: float = 30.0, max_retries: int = 3):
        self._tools: Dict[str, ToolDefinition] = {}
        self._call_history: List[ToolCallRecord] = []
        self._default_timeout = default_timeout
        self._max_retries = max_retries
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
    
    def unregister_tool(self, tool_name: str) -> bool:
        """注销工具"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            return True
        return False
    
    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[ToolDefinition]:
        """列出所有已注册工具"""
        return list(self._tools.values())
    
    async def invoke_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any],
        agent_id: str
    ) -> ToolCallRecord:
        """
        调用工具
        
        Args:
            tool_name: 工具名称
            arguments: 调用参数
            agent_id: 调用者智能体ID
            
        Returns:
            工具调用记录
        """
        tool = self.get_tool(tool_name)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{tool_name}' not found")
        
        record_id = str(uuid.uuid4())
        start_time = time.time()
        result = None
        success = False
        error = None
        
        timeout = tool.timeout if tool.timeout > 0 else self._default_timeout
        retries = self._max_retries if tool.retry_on_failure else 1
        
        for attempt in range(retries):
            try:
                result = await asyncio.wait_for(
                    tool.handler(**arguments),
                    timeout=timeout
                )
                success = True
                break
            except asyncio.TimeoutError:
                error = f"Tool call timed out after {timeout}s"
                if attempt < retries - 1:
                    continue
                raise ToolTimeoutError(error)
            except Exception as e:
                error = str(e)
                if attempt < retries - 1 and tool.retry_on_failure:
                    continue
                break
        
        end_time = time.time()
        
        record = ToolCallRecord(
            id=record_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            error=error,
            start_time=start_time,
            end_time=end_time,
            agent_id=agent_id
        )
        
        self._call_history.append(record)
        return record
    
    def get_call_history(self, agent_id: Optional[str] = None) -> List[ToolCallRecord]:
        """获取工具调用历史"""
        if agent_id is None:
            return list(self._call_history)
        return [r for r in self._call_history if r.agent_id == agent_id]
    
    def get_total_calls(self) -> int:
        """获取总调用次数"""
        return len(self._call_history)
