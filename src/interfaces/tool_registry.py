"""Tool Registry interface."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from ..models.tool import ToolDefinition, ToolCallRecord


class IToolRegistry(ABC):
    """工具注册表接口"""
    
    @abstractmethod
    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具"""
        pass
    
    @abstractmethod
    def unregister_tool(self, tool_name: str) -> bool:
        """注销工具"""
        pass
    
    @abstractmethod
    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        pass
    
    @abstractmethod
    def list_tools(self) -> List[ToolDefinition]:
        """列出所有已注册工具"""
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def get_call_history(self, agent_id: Optional[str] = None) -> List[ToolCallRecord]:
        """获取工具调用历史"""
        pass
    
    @abstractmethod
    def get_total_calls(self) -> int:
        """获取总调用次数"""
        pass
