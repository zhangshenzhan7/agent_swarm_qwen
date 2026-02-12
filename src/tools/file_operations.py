"""File operations tool implementation."""

import os
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from pathlib import Path

from ..models.tool import ToolDefinition


@dataclass
class FileInfo:
    """文件信息"""
    name: str
    path: str
    size: int
    is_directory: bool
    extension: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "is_directory": self.is_directory,
            "extension": self.extension,
        }


class FileOperationsTool:
    """
    文件操作工具
    
    提供安全的文件读写操作，支持：
    - 读取文件内容
    - 写入文件内容
    - 列出目录内容
    - 检查文件是否存在
    
    安全注意事项：
    - 限制操作目录范围
    - 禁止访问敏感路径
    - 限制文件大小
    """
    
    def __init__(
        self,
        base_directory: Optional[str] = None,
        max_file_size: int = 1024 * 1024,  # 1MB
        allowed_extensions: Optional[List[str]] = None,
        sandbox_mode: bool = True,
    ):
        """
        初始化文件操作工具
        
        Args:
            base_directory: 基础目录（限制操作范围）
            max_file_size: 最大文件大小（字节）
            allowed_extensions: 允许的文件扩展名
            sandbox_mode: 是否启用沙箱模式
        """
        self._base_directory = base_directory or os.getcwd()
        self._max_file_size = max_file_size
        self._allowed_extensions = allowed_extensions
        self._sandbox_mode = sandbox_mode
        
        # 敏感路径列表
        self._sensitive_paths = [
            "/etc", "/var", "/usr", "/bin", "/sbin",
            "/root", "/home", "/sys", "/proc", "/dev",
            "~/.ssh", "~/.aws", "~/.config",
        ]
    
    def _validate_path(self, path: str) -> Dict[str, Any]:
        """验证路径安全性"""
        # 解析绝对路径
        abs_path = os.path.abspath(os.path.expanduser(path))
        base_abs = os.path.abspath(self._base_directory)
        
        # 检查是否在基础目录内
        if self._sandbox_mode:
            if not abs_path.startswith(base_abs):
                return {
                    "valid": False,
                    "reason": f"Path must be within base directory: {self._base_directory}",
                }
        
        # 检查敏感路径
        for sensitive in self._sensitive_paths:
            sensitive_abs = os.path.abspath(os.path.expanduser(sensitive))
            if abs_path.startswith(sensitive_abs):
                return {
                    "valid": False,
                    "reason": f"Access to sensitive path is not allowed: {sensitive}",
                }
        
        return {"valid": True, "path": abs_path}
    
    async def read_file(self, path: str) -> Dict[str, Any]:
        """
        读取文件内容
        
        Args:
            path: 文件路径
            
        Returns:
            包含文件内容的字典
        """
        # 验证路径
        validation = self._validate_path(path)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["reason"],
            }
        
        abs_path = validation["path"]
        
        # 检查文件是否存在
        if not os.path.exists(abs_path):
            return {
                "success": False,
                "error": f"File not found: {path}",
            }
        
        # 检查是否是文件
        if not os.path.isfile(abs_path):
            return {
                "success": False,
                "error": f"Path is not a file: {path}",
            }
        
        # 检查文件大小
        file_size = os.path.getsize(abs_path)
        if file_size > self._max_file_size:
            return {
                "success": False,
                "error": f"File too large: {file_size} bytes (max: {self._max_file_size})",
            }
        
        # 检查扩展名
        if self._allowed_extensions:
            ext = os.path.splitext(abs_path)[1].lower()
            if ext not in self._allowed_extensions:
                return {
                    "success": False,
                    "error": f"File extension not allowed: {ext}",
                }
        
        try:
            # 读取文件
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            return {
                "success": True,
                "content": content,
                "size": file_size,
                "path": abs_path,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def write_file(
        self,
        path: str,
        content: str,
        append: bool = False,
    ) -> Dict[str, Any]:
        """
        写入文件内容
        
        Args:
            path: 文件路径
            content: 要写入的内容
            append: 是否追加模式
            
        Returns:
            操作结果
        """
        # 验证路径
        validation = self._validate_path(path)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["reason"],
            }
        
        abs_path = validation["path"]
        
        # 检查内容大小
        if len(content.encode('utf-8')) > self._max_file_size:
            return {
                "success": False,
                "error": f"Content too large (max: {self._max_file_size} bytes)",
            }
        
        # 检查扩展名
        if self._allowed_extensions:
            ext = os.path.splitext(abs_path)[1].lower()
            if ext not in self._allowed_extensions:
                return {
                    "success": False,
                    "error": f"File extension not allowed: {ext}",
                }
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            
            # 写入文件
            mode = 'a' if append else 'w'
            with open(abs_path, mode, encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "path": abs_path,
                "size": len(content.encode('utf-8')),
                "mode": "append" if append else "write",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def list_directory(self, path: str) -> Dict[str, Any]:
        """
        列出目录内容
        
        Args:
            path: 目录路径
            
        Returns:
            目录内容列表
        """
        # 验证路径
        validation = self._validate_path(path)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["reason"],
            }
        
        abs_path = validation["path"]
        
        # 检查目录是否存在
        if not os.path.exists(abs_path):
            return {
                "success": False,
                "error": f"Directory not found: {path}",
            }
        
        # 检查是否是目录
        if not os.path.isdir(abs_path):
            return {
                "success": False,
                "error": f"Path is not a directory: {path}",
            }
        
        try:
            files = []
            for item in os.listdir(abs_path):
                item_path = os.path.join(abs_path, item)
                is_dir = os.path.isdir(item_path)
                
                file_info = FileInfo(
                    name=item,
                    path=item_path,
                    size=os.path.getsize(item_path) if not is_dir else 0,
                    is_directory=is_dir,
                    extension=os.path.splitext(item)[1] if not is_dir else "",
                )
                files.append(file_info.to_dict())
            
            return {
                "success": True,
                "path": abs_path,
                "files": files,
                "total": len(files),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def file_exists(self, path: str) -> Dict[str, Any]:
        """
        检查文件是否存在
        
        Args:
            path: 文件路径
            
        Returns:
            检查结果
        """
        # 验证路径
        validation = self._validate_path(path)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["reason"],
            }
        
        abs_path = validation["path"]
        
        exists = os.path.exists(abs_path)
        is_file = os.path.isfile(abs_path) if exists else False
        is_dir = os.path.isdir(abs_path) if exists else False
        
        return {
            "success": True,
            "exists": exists,
            "is_file": is_file,
            "is_directory": is_dir,
            "path": abs_path,
        }
    
    def get_tool_definition(self) -> ToolDefinition:
        """获取工具定义"""
        return ToolDefinition(
            name="file_operations",
            description="执行文件操作：读取、写入、列出目录、检查文件存在。",
            parameters_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "操作类型",
                        "enum": ["read", "write", "list", "exists"],
                    },
                    "path": {
                        "type": "string",
                        "description": "文件或目录路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的内容（仅 write 操作需要）",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "是否追加模式（仅 write 操作）",
                        "default": False,
                    },
                },
                "required": ["operation", "path"],
            },
            handler=self._handle_operation,
            timeout=30.0,
        )
    
    async def _handle_operation(
        self,
        operation: str,
        path: str,
        content: str = "",
        append: bool = False,
    ) -> Dict[str, Any]:
        """工具调用处理函数"""
        if operation == "read":
            return await self.read_file(path)
        elif operation == "write":
            return await self.write_file(path, content, append)
        elif operation == "list":
            return await self.list_directory(path)
        elif operation == "exists":
            return await self.file_exists(path)
        else:
            return {
                "success": False,
                "error": f"Unknown operation: {operation}",
            }


def create_file_operations_tool(
    base_directory: Optional[str] = None,
    max_file_size: int = 1024 * 1024,
    sandbox_mode: bool = True,
) -> ToolDefinition:
    """
    创建文件操作工具定义
    
    Args:
        base_directory: 基础目录
        max_file_size: 最大文件大小
        sandbox_mode: 是否启用沙箱模式
        
    Returns:
        工具定义
    """
    tool = FileOperationsTool(base_directory, max_file_size, sandbox_mode=sandbox_mode)
    return tool.get_tool_definition()
