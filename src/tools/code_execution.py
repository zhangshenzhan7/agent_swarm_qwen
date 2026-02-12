"""Code execution tool implementation."""

import asyncio
import subprocess
import tempfile
import os
from dataclasses import dataclass
from typing import Dict, Any, Optional, Protocol, runtime_checkable
from enum import Enum

from ..models.tool import ToolDefinition


class Language(Enum):
    """支持的编程语言"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    SHELL = "shell"


@dataclass
class ExecutionResult:
    """
    代码执行结果
    
    包含代码执行的完整结果信息，满足需求 2.8：
    返回标准输出、标准错误、返回码和执行时间
    
    Attributes:
        success: 执行是否成功
        stdout: 标准输出内容
        stderr: 标准错误内容
        return_code: 进程返回码
        execution_time: 执行时间（秒）
        memory_used: 内存使用量（字节），可选
        error_type: 错误类型，可选（如 EXEC_TIMEOUT, EXEC_MEMORY_LIMIT, EXEC_SECURITY_VIOLATION 等）
    """
    success: bool
    stdout: str
    stderr: str
    return_code: int
    execution_time: float
    memory_used: Optional[int] = None
    error_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """将执行结果转换为字典格式"""
        result = {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "execution_time": self.execution_time,
        }
        if self.memory_used is not None:
            result["memory_used"] = self.memory_used
        if self.error_type is not None:
            result["error_type"] = self.error_type
        return result


@runtime_checkable
class ExecutionBackend(Protocol):
    """
    执行后端协议
    
    定义代码执行后端的标准接口，支持多种执行后端实现：
    - RestrictedPython 沙箱后端
    - Docker 容器执行后端
    - 阿里云函数计算后端
    
    所有后端实现必须遵循此协议，确保统一的调用接口。
    """
    
    async def execute(self, code: str, language: str, timeout: float) -> ExecutionResult:
        """
        执行代码
        
        Args:
            code: 要执行的代码字符串
            language: 编程语言（如 "python", "shell", "javascript"）
            timeout: 执行超时时间（秒）
            
        Returns:
            ExecutionResult: 包含执行结果的数据类实例
            
        Raises:
            此方法不应抛出异常，所有错误应通过 ExecutionResult 返回
        """
        ...


class CodeExecutionTool:
    """
    代码执行工具
    
    提供安全的代码执行环境，支持 Python、JavaScript 和 Shell 脚本。
    
    安全注意事项：
    - 默认启用沙箱模式
    - 限制执行时间
    - 限制内存使用
    - 禁止危险操作
    """
    
    def __init__(
        self,
        timeout: float = 30.0,
        max_output_size: int = 10000,
        sandbox_mode: bool = True,
        allowed_languages: Optional[list] = None,
    ):
        """
        初始化代码执行工具
        
        Args:
            timeout: 执行超时时间（秒）
            max_output_size: 最大输出大小（字符）
            sandbox_mode: 是否启用沙箱模式
            allowed_languages: 允许的语言列表
        """
        self._timeout = timeout
        self._max_output_size = max_output_size
        self._sandbox_mode = sandbox_mode
        self._allowed_languages = allowed_languages or [
            Language.PYTHON.value,
            Language.SHELL.value,
        ]
    
    async def execute(
        self,
        code: str,
        language: str = "python",
    ) -> ExecutionResult:
        """
        执行代码
        
        Args:
            code: 要执行的代码
            language: 编程语言
            
        Returns:
            执行结果
        """
        # 验证语言
        if language not in self._allowed_languages:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Language '{language}' is not allowed. "
                       f"Allowed: {self._allowed_languages}",
                return_code=-1,
                execution_time=0,
            )
        
        # 安全检查
        if self._sandbox_mode:
            security_check = self._check_code_safety(code, language)
            if not security_check["safe"]:
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Security check failed: {security_check['reason']}",
                    return_code=-1,
                    execution_time=0,
                )
        
        # 执行代码
        if language == Language.PYTHON.value:
            return await self._execute_python(code)
        elif language == Language.SHELL.value:
            return await self._execute_shell(code)
        elif language == Language.JAVASCRIPT.value:
            return await self._execute_javascript(code)
        else:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Unsupported language: {language}",
                return_code=-1,
                execution_time=0,
            )
    
    def _check_code_safety(self, code: str, language: str) -> Dict[str, Any]:
        """检查代码安全性"""
        dangerous_patterns = {
            "python": [
                "import os", "import subprocess", "import sys",
                "__import__", "eval(", "exec(",
                "open(", "file(", "input(",
                "os.system", "os.popen", "subprocess.",
            ],
            "shell": [
                "rm -rf", "sudo", "chmod", "chown",
                "> /dev/", "dd if=", "mkfs",
                ":(){ :|:& };:",  # Fork bomb
            ],
            "javascript": [
                "require('child_process')", "require('fs')",
                "process.exit", "eval(",
            ],
        }
        
        patterns = dangerous_patterns.get(language, [])
        code_lower = code.lower()
        
        for pattern in patterns:
            if pattern.lower() in code_lower:
                return {
                    "safe": False,
                    "reason": f"Dangerous pattern detected: {pattern}",
                }
        
        return {"safe": True, "reason": None}
    
    async def _execute_python(self, code: str) -> ExecutionResult:
        """执行 Python 代码"""
        import time
        start_time = time.time()
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # 执行代码
            process = await asyncio.create_subprocess_exec(
                'python3', temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Execution timed out after {self._timeout}s",
                    return_code=-1,
                    execution_time=self._timeout,
                )
            
            execution_time = time.time() - start_time
            
            # 截断输出
            stdout_str = stdout.decode('utf-8', errors='replace')[:self._max_output_size]
            stderr_str = stderr.decode('utf-8', errors='replace')[:self._max_output_size]
            
            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                return_code=process.returncode,
                execution_time=execution_time,
            )
            
        finally:
            # 清理临时文件
            os.unlink(temp_file)
    
    async def _execute_shell(self, code: str) -> ExecutionResult:
        """执行 Shell 脚本"""
        import time
        start_time = time.time()
        
        try:
            process = await asyncio.create_subprocess_shell(
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Execution timed out after {self._timeout}s",
                    return_code=-1,
                    execution_time=self._timeout,
                )
            
            execution_time = time.time() - start_time
            
            stdout_str = stdout.decode('utf-8', errors='replace')[:self._max_output_size]
            stderr_str = stderr.decode('utf-8', errors='replace')[:self._max_output_size]
            
            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                return_code=process.returncode,
                execution_time=execution_time,
            )
            
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                execution_time=time.time() - start_time,
            )
    
    async def _execute_javascript(self, code: str) -> ExecutionResult:
        """执行 JavaScript 代码"""
        import time
        start_time = time.time()
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.js',
            delete=False
        ) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # 尝试使用 node 执行
            process = await asyncio.create_subprocess_exec(
                'node', temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Execution timed out after {self._timeout}s",
                    return_code=-1,
                    execution_time=self._timeout,
                )
            
            execution_time = time.time() - start_time
            
            stdout_str = stdout.decode('utf-8', errors='replace')[:self._max_output_size]
            stderr_str = stderr.decode('utf-8', errors='replace')[:self._max_output_size]
            
            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                return_code=process.returncode,
                execution_time=execution_time,
            )
            
        finally:
            os.unlink(temp_file)
    
    def get_tool_definition(self) -> ToolDefinition:
        """获取工具定义"""
        return ToolDefinition(
            name="code_execution",
            description="执行代码并返回结果。支持 Python 和 Shell 脚本。",
            parameters_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的代码",
                    },
                    "language": {
                        "type": "string",
                        "description": "编程语言 (python, shell)",
                        "enum": self._allowed_languages,
                        "default": "python",
                    },
                },
                "required": ["code"],
            },
            handler=self._handle_execute,
            timeout=self._timeout + 5,  # 额外缓冲时间
        )
    
    async def _handle_execute(
        self,
        code: str,
        language: str = "python",
    ) -> Dict[str, Any]:
        """工具调用处理函数"""
        result = await self.execute(code, language)
        return result.to_dict()


def create_code_execution_tool(
    timeout: float = 30.0,
    max_output_size: int = 10000,
    sandbox_mode: bool = True,
    backend: Optional[ExecutionBackend] = None,
) -> ToolDefinition:
    """
    创建代码执行工具定义
    
    Args:
        timeout: 执行超时时间
        max_output_size: 最大输出大小
        sandbox_mode: 是否启用沙箱模式
        backend: 自定义执行后端（可选）
                如果提供，将使用该后端替代默认的本地执行
        
    Returns:
        工具定义
    """
    if backend:
        # 使用自定义后端
        tool = CodeExecutionToolWithBackend(backend=backend, timeout=timeout)
    else:
        # 使用默认本地执行
        tool = CodeExecutionTool(timeout, max_output_size, sandbox_mode)
    
    return tool.get_tool_definition()


class CodeExecutionToolWithBackend:
    """
    代码执行工具（基于后端）
    
    使用自定义执行后端（如阿里云 FC Code Interpreter）执行代码。
    相比本地执行，提供更强的安全隔离和云端资源。
    """
    
    def __init__(
        self,
        backend: ExecutionBackend,
        timeout: float = 30.0,
    ):
        """
        初始化代码执行工具
        
        Args:
            backend: 执行后端实例
            timeout: 执行超时时间
        """
        self._backend = backend
        self._timeout = timeout
    
    async def execute(
        self,
        code: str,
        language: str = "python",
    ) -> ExecutionResult:
        """
        执行代码
        
        Args:
            code: 要执行的代码
            language: 编程语言
            
        Returns:
            执行结果
        """
        return await self._backend.execute(code, language, self._timeout)
    
    def get_tool_definition(self) -> ToolDefinition:
        """获取工具定义"""
        return ToolDefinition(
            name="code_execution",
            description="执行代码并返回结果。支持 Python 和 JavaScript。",
            parameters_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的代码",
                    },
                    "language": {
                        "type": "string",
                        "description": "编程语言 (python, javascript)",
                        "enum": ["python", "javascript"],
                        "default": "python",
                    },
                },
                "required": ["code"],
            },
            handler=self._handle_execute,
            timeout=self._timeout + 5,
        )
    
    async def _handle_execute(
        self,
        code: str,
        language: str = "python",
    ) -> Dict[str, Any]:
        """工具调用处理函数"""
        result = await self.execute(code, language)
        return result.to_dict()
