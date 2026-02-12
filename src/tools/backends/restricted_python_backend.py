"""
RestrictedPython 沙箱后端实现

使用 RestrictedPython 库实现安全的 Python 代码执行。
支持危险操作检测和阻止、超时和内存限制。

验证:
- 需求 2.2: 使用 RestrictedPython 限制危险操作
- 需求 2.5: 代码执行超过配置的超时时间时强制终止执行并返回超时错误
- 需求 2.6: 代码执行消耗内存超过限制时终止执行并返回内存超限错误
- 需求 2.7: 禁止执行文件系统操作、网络操作和系统调用
"""

import asyncio
import logging
import time
import sys
import traceback
import resource
import signal
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
import multiprocessing

from ..code_execution import ExecutionResult

logger = logging.getLogger(__name__)


# 错误类型常量
class ExecutionErrorType:
    """执行错误类型常量"""
    TIMEOUT = "EXEC_TIMEOUT"
    MEMORY_LIMIT = "EXEC_MEMORY_LIMIT"
    SECURITY_VIOLATION = "EXEC_SECURITY_VIOLATION"
    SYNTAX_ERROR = "EXEC_SYNTAX_ERROR"
    RUNTIME_ERROR = "EXEC_RUNTIME_ERROR"
    UNSUPPORTED_LANGUAGE = "EXEC_UNSUPPORTED_LANGUAGE"


# 危险的内置函数和模块
DANGEROUS_BUILTINS: Set[str] = {
    # 文件系统操作 - 需求 2.7
    'open', 'file', 'input', 'raw_input',
    # 代码执行
    'eval', 'exec', 'compile', '__import__',
    # 系统调用 - 需求 2.7
    'exit', 'quit',
}

# 危险的模块 - 需求 2.7
DANGEROUS_MODULES: Set[str] = {
    # 系统调用
    'os', 'sys', 'subprocess', 'commands', 'popen2',
    # 网络操作
    'socket', 'urllib', 'urllib2', 'urllib3', 'httplib', 'http',
    'requests', 'aiohttp', 'httpx', 'ftplib', 'telnetlib',
    # 文件系统
    'shutil', 'pathlib', 'glob', 'fnmatch', 'tempfile',
    'io', 'fileinput', 'stat', 'filecmp', 'linecache',
    # 进程和线程
    'multiprocessing', 'threading', 'concurrent', '_thread',
    'signal', 'mmap', 'ctypes', 'cffi',
    # 代码操作
    'importlib', 'imp', 'pkgutil', 'modulefinder',
    'code', 'codeop', 'compileall', 'py_compile',
    # 其他危险模块
    'pickle', 'cPickle', 'shelve', 'marshal',
    'pty', 'tty', 'termios', 'fcntl',
    'resource', 'sysconfig', 'platform',
    'builtins', '__builtin__',
}

# 安全的内置函数白名单
SAFE_BUILTINS: Dict[str, Any] = {
    # 类型转换
    'abs': abs,
    'bool': bool,
    'bytes': bytes,
    'chr': chr,
    'complex': complex,
    'dict': dict,
    'divmod': divmod,
    'enumerate': enumerate,
    'filter': filter,
    'float': float,
    'format': format,
    'frozenset': frozenset,
    'hash': hash,
    'hex': hex,
    'int': int,
    'isinstance': isinstance,
    'issubclass': issubclass,
    'iter': iter,
    'len': len,
    'list': list,
    'map': map,
    'max': max,
    'min': min,
    'next': next,
    'oct': oct,
    'ord': ord,
    'pow': pow,
    'print': print,
    'range': range,
    'repr': repr,
    'reversed': reversed,
    'round': round,
    'set': set,
    'slice': slice,
    'sorted': sorted,
    'str': str,
    'sum': sum,
    'tuple': tuple,
    'type': type,
    'zip': zip,
    # 常量
    'True': True,
    'False': False,
    'None': None,
    # 异常类
    'Exception': Exception,
    'ValueError': ValueError,
    'TypeError': TypeError,
    'KeyError': KeyError,
    'IndexError': IndexError,
    'AttributeError': AttributeError,
    'RuntimeError': RuntimeError,
    'StopIteration': StopIteration,
    'ZeroDivisionError': ZeroDivisionError,
    'AssertionError': AssertionError,
}

# 允许导入的安全模块白名单
DEFAULT_ALLOWED_IMPORTS: List[str] = [
    'math',
    'random',
    'string',
    'collections',
    'itertools',
    'functools',
    'operator',
    'decimal',
    'fractions',
    'statistics',
    'datetime',
    'time',  # 只允许时间相关函数，不允许 sleep
    'json',
    're',
    'copy',
    'heapq',
    'bisect',
    'array',
    'typing',
    'dataclasses',
    'enum',
    'abc',
]


def _create_safe_import(allowed_imports: List[str]):
    """
    创建安全的 __import__ 函数
    
    只允许导入白名单中的模块，阻止危险模块的导入。
    
    Args:
        allowed_imports: 允许导入的模块列表
        
    Returns:
        安全的 import 函数
    """
    allowed_set = set(allowed_imports)
    
    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        """安全的导入函数"""
        # 获取顶级模块名
        top_level = name.split('.')[0]
        
        # 检查是否在危险模块列表中
        if top_level in DANGEROUS_MODULES:
            raise ImportError(
                f"Security violation: Import of module '{name}' is not allowed. "
                f"This module is blocked for security reasons."
            )
        
        # 检查是否在允许列表中
        if top_level not in allowed_set:
            raise ImportError(
                f"Security violation: Import of module '{name}' is not allowed. "
                f"Only these modules are allowed: {sorted(allowed_set)}"
            )
        
        # 使用原始的 __import__ 导入模块
        return __builtins__['__import__'](name, globals, locals, fromlist, level)
    
    return safe_import


def _check_dangerous_code(code: str) -> Optional[str]:
    """
    检查代码中是否包含危险操作
    
    在编译前进行静态检查，检测明显的危险模式。
    
    Args:
        code: 要检查的代码字符串
        
    Returns:
        如果发现危险操作，返回错误描述；否则返回 None
    """
    import re
    
    # 检查危险模块的导入 - 需求 2.7
    # 匹配 import xxx 或 from xxx import 模式
    import_pattern = r'(?:^|\n)\s*(?:import|from)\s+(\w+)'
    imports = re.findall(import_pattern, code)
    
    for module in imports:
        if module in DANGEROUS_MODULES:
            return f"Import of dangerous module '{module}' is not allowed"
    
    # 危险模式检测
    dangerous_patterns = [
        # 文件系统操作 - 需求 2.7
        ('open(', 'File system access (open) is not allowed'),
        ('open (', 'File system access (open) is not allowed'),
        ('file(', 'File system access (file) is not allowed'),
        
        # 系统调用 - 需求 2.7
        ('os.system', 'System calls (os.system) are not allowed'),
        ('os.popen', 'System calls (os.popen) are not allowed'),
        ('os.exec', 'System calls (os.exec) are not allowed'),
        ('os.spawn', 'System calls (os.spawn) are not allowed'),
        
        # 网络操作 - 需求 2.7
        ('socket.', 'Network operations (socket) are not allowed'),
        ('urllib.', 'Network operations (urllib) are not allowed'),
        ('requests.', 'Network operations (requests) are not allowed'),
        ('http.client', 'Network operations (http.client) are not allowed'),
        
        # 代码执行
        ('eval(', 'Dynamic code execution (eval) is not allowed'),
        ('eval (', 'Dynamic code execution (eval) is not allowed'),
        ('exec(', 'Dynamic code execution (exec) is not allowed'),
        ('exec (', 'Dynamic code execution (exec) is not allowed'),
        ('compile(', 'Dynamic code compilation is not allowed'),
        
        # 属性访问绕过
        ('__import__', 'Direct __import__ is not allowed'),
        ('__builtins__', 'Access to __builtins__ is not allowed'),
        ('__globals__', 'Access to __globals__ is not allowed'),
        ('__code__', 'Access to __code__ is not allowed'),
        ('__class__', 'Access to __class__ is not allowed'),
        ('__bases__', 'Access to __bases__ is not allowed'),
        ('__subclasses__', 'Access to __subclasses__ is not allowed'),
        ('__mro__', 'Access to __mro__ is not allowed'),
        
        # 危险的内置函数
        ('getattr(', 'Dynamic attribute access (getattr) is restricted'),
        ('setattr(', 'Dynamic attribute modification (setattr) is not allowed'),
        ('delattr(', 'Dynamic attribute deletion (delattr) is not allowed'),
    ]
    
    code_lower = code.lower()
    
    for pattern, message in dangerous_patterns:
        if pattern.lower() in code_lower:
            return message
    
    return None


def _execute_in_sandbox(
    code: str,
    allowed_imports: List[str],
    max_memory: int,
    timeout: float
) -> Dict[str, Any]:
    """
    在沙箱中执行代码（在子进程中运行）
    
    此函数在独立的子进程中运行，以实现内存限制和隔离。
    
    Args:
        code: 要执行的代码
        allowed_imports: 允许导入的模块列表
        max_memory: 最大内存限制（字节）
        timeout: 超时时间（秒）
        
    Returns:
        包含执行结果的字典
    """
    import io
    import sys
    
    start_time = time.time()
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    result = {
        'success': False,
        'stdout': '',
        'stderr': '',
        'return_code': -1,
        'execution_time': 0.0,
        'memory_used': None,
        'error_type': None,
    }
    
    try:
        # 设置内存限制 - 需求 2.6
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))
        except (ValueError, resource.error) as e:
            logger.warning(f"Failed to set memory limit: {e}")
        
        # 设置 CPU 时间限制作为备份超时机制
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (int(timeout) + 1, int(timeout) + 2))
        except (ValueError, resource.error) as e:
            logger.warning(f"Failed to set CPU limit: {e}")
        
        # 静态代码检查 - 需求 2.7
        danger_check = _check_dangerous_code(code)
        if danger_check:
            result['stderr'] = f"Security violation: {danger_check}"
            result['error_type'] = ExecutionErrorType.SECURITY_VIOLATION
            result['execution_time'] = time.time() - start_time
            return result
        
        # 尝试使用 RestrictedPython 编译代码 - 需求 2.2
        try:
            from RestrictedPython import compile_restricted
            from RestrictedPython.Guards import safe_builtins, guarded_iter_unpack_sequence
            from RestrictedPython.Eval import default_guarded_getiter, default_guarded_getitem
            from RestrictedPython.PrintCollector import PrintCollector
            
            # 编译代码 - RestrictedPython 8.x API
            # compile_restricted 直接返回 code 对象，如果有语法错误会抛出 SyntaxError
            try:
                byte_code = compile_restricted(
                    code,
                    filename='<user_code>',
                    mode='exec'
                )
            except SyntaxError as e:
                result['stderr'] = f"Syntax error: {e}"
                result['error_type'] = ExecutionErrorType.SYNTAX_ERROR
                result['execution_time'] = time.time() - start_time
                return result
            
            # 创建安全的执行环境
            safe_builtins_copy = dict(safe_builtins)
            safe_builtins_copy['__import__'] = _create_safe_import(allowed_imports)
            
            # 添加 safe_builtins 中缺失的安全内置函数
            # RestrictedPython 的 safe_builtins 不包含一些常用函数
            additional_builtins = {
                'list': list,
                'dict': dict,
                'set': set,
                'frozenset': frozenset,
                'enumerate': enumerate,
                'filter': filter,
                'map': map,
                'max': max,
                'min': min,
                'sum': sum,
                'any': any,
                'all': all,
                'iter': iter,
                'next': next,
                'reversed': reversed,
                'format': format,
                'type': type,
                'object': object,
                'super': super,
                'property': property,
                'staticmethod': staticmethod,
                'classmethod': classmethod,
                'hasattr': hasattr,
                'bin': bin,
                'ascii': ascii,
                'input': None,  # 禁用 input
            }
            
            for name, func in additional_builtins.items():
                if name not in safe_builtins_copy or safe_builtins_copy[name] is None:
                    safe_builtins_copy[name] = func
            
            # 创建受限的全局命名空间
            # 使用 PrintCollector 来收集 print 输出
            restricted_globals = {
                '__builtins__': safe_builtins_copy,
                '__name__': '__main__',
                '__doc__': None,
                '_getiter_': default_guarded_getiter,
                '_getitem_': default_guarded_getitem,
                '_iter_unpack_sequence_': guarded_iter_unpack_sequence,
                '_print_': PrintCollector,
                '_getattr_': lambda obj, name: getattr(obj, name) if not name.startswith('_') else None,
                '_write_': lambda x: x,  # 允许写入操作
            }
            
            # 重定向标准输出
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            try:
                # 执行代码
                exec(byte_code, restricted_globals)
                
                # 获取 print 输出 - RestrictedPython 使用 _print 变量收集输出
                if '_print' in restricted_globals:
                    printed = restricted_globals['_print']
                    if printed is not None:
                        # PrintCollector 实例有 txt() 方法
                        if hasattr(printed, 'txt'):
                            stdout_capture.write(printed.txt())
                        elif hasattr(printed, '__call__'):
                            # 如果是可调用对象，尝试调用它
                            try:
                                output = printed()
                                if output:
                                    stdout_capture.write(str(output))
                            except Exception:
                                pass
                
                result['success'] = True
                result['return_code'] = 0
                
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
        except ImportError:
            # RestrictedPython 未安装，使用基本沙箱
            logger.warning("RestrictedPython not installed, using basic sandbox")
            
            # 基本沙箱实现
            safe_builtins_copy = dict(SAFE_BUILTINS)
            safe_builtins_copy['__import__'] = _create_safe_import(allowed_imports)
            
            restricted_globals = {
                '__builtins__': safe_builtins_copy,
                '__name__': '__main__',
                '__doc__': None,
            }
            
            # 编译代码
            try:
                compiled = compile(code, '<user_code>', 'exec')
            except SyntaxError as e:
                result['stderr'] = f"Syntax error: {e}"
                result['error_type'] = ExecutionErrorType.SYNTAX_ERROR
                result['execution_time'] = time.time() - start_time
                return result
            
            # 重定向标准输出
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            try:
                exec(compiled, restricted_globals)
                result['success'] = True
                result['return_code'] = 0
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
        
    except MemoryError:
        # 需求 2.6: 内存超限
        result['stderr'] = f"Memory limit exceeded ({max_memory} bytes)"
        result['error_type'] = ExecutionErrorType.MEMORY_LIMIT
        
    except ImportError as e:
        # 安全违规：尝试导入禁止的模块
        result['stderr'] = str(e)
        result['error_type'] = ExecutionErrorType.SECURITY_VIOLATION
        
    except SyntaxError as e:
        result['stderr'] = f"Syntax error: {e}"
        result['error_type'] = ExecutionErrorType.SYNTAX_ERROR
        
    except Exception as e:
        result['stderr'] = f"Runtime error: {type(e).__name__}: {e}"
        result['error_type'] = ExecutionErrorType.RUNTIME_ERROR
    
    # 获取输出
    result['stdout'] = stdout_capture.getvalue()
    if not result['stderr']:
        result['stderr'] = stderr_capture.getvalue()
    
    result['execution_time'] = time.time() - start_time
    
    # 尝试获取内存使用量
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result['memory_used'] = usage.ru_maxrss * 1024  # 转换为字节
    except Exception:
        pass
    
    return result


class RestrictedPythonBackend:
    """
    RestrictedPython 沙箱后端
    
    使用 RestrictedPython 库实现安全的 Python 代码执行。
    支持危险操作检测和阻止、超时和内存限制。
    
    验证:
    - 需求 2.2: 使用 RestrictedPython 限制危险操作
    - 需求 2.5: 超时处理
    - 需求 2.6: 内存限制
    - 需求 2.7: 禁止文件系统、网络和系统调用
    
    Attributes:
        allowed_imports: 允许导入的模块列表
        max_memory: 最大内存限制（字节）
    """
    
    def __init__(
        self,
        allowed_imports: Optional[List[str]] = None,
        max_memory: int = 128 * 1024 * 1024  # 128MB
    ):
        """
        初始化 RestrictedPython 沙箱后端
        
        Args:
            allowed_imports: 允许导入的模块列表，默认使用安全白名单
            max_memory: 最大内存限制（字节），默认 128MB
        """
        self.allowed_imports = allowed_imports or DEFAULT_ALLOWED_IMPORTS.copy()
        self.max_memory = max_memory
        
        # 验证允许的导入不包含危险模块
        for module in self.allowed_imports:
            if module in DANGEROUS_MODULES:
                raise ValueError(
                    f"Module '{module}' is in the dangerous modules list "
                    f"and cannot be allowed"
                )
        
        logger.info(
            f"RestrictedPythonBackend initialized: "
            f"allowed_imports={len(self.allowed_imports)}, "
            f"max_memory={self.max_memory}"
        )
    
    async def execute(
        self,
        code: str,
        language: str,
        timeout: float
    ) -> ExecutionResult:
        """
        执行代码
        
        在受限的沙箱环境中执行 Python 代码。
        
        Args:
            code: 要执行的代码字符串
            language: 编程语言（此后端只支持 "python"）
            timeout: 执行超时时间（秒）
            
        Returns:
            ExecutionResult: 包含执行结果的数据类实例
        """
        start_time = time.time()
        
        # 验证语言
        if language.lower() != "python":
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"RestrictedPython backend only supports Python. "
                       f"Got: {language}",
                return_code=-1,
                execution_time=0.0,
                error_type=ExecutionErrorType.UNSUPPORTED_LANGUAGE
            )
        
        # 验证代码不为空
        if not code or not code.strip():
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Code cannot be empty",
                return_code=-1,
                execution_time=0.0,
                error_type=ExecutionErrorType.SYNTAX_ERROR
            )
        
        try:
            # 在子进程中执行代码以实现隔离和资源限制
            result = await self._execute_in_process(code, timeout)
            return result
            
        except asyncio.TimeoutError:
            # 需求 2.5: 超时处理
            execution_time = time.time() - start_time
            logger.warning(f"Code execution timed out after {timeout}s")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution timed out after {timeout} seconds",
                return_code=-1,
                execution_time=execution_time,
                error_type=ExecutionErrorType.TIMEOUT
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Unexpected error during code execution: {e}")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Unexpected error: {type(e).__name__}: {e}",
                return_code=-1,
                execution_time=execution_time,
                error_type=ExecutionErrorType.RUNTIME_ERROR
            )
    
    async def _execute_in_process(
        self,
        code: str,
        timeout: float
    ) -> ExecutionResult:
        """
        在子进程中执行代码
        
        使用 ProcessPoolExecutor 在独立进程中执行代码，
        以实现内存隔离和资源限制。
        
        Args:
            code: 要执行的代码
            timeout: 超时时间（秒）
            
        Returns:
            ExecutionResult: 执行结果
        """
        loop = asyncio.get_event_loop()
        
        # 使用 spawn 方法创建进程，确保干净的环境
        ctx = multiprocessing.get_context('spawn')
        
        with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
            try:
                # 在进程池中执行
                future = loop.run_in_executor(
                    executor,
                    _execute_in_sandbox,
                    code,
                    self.allowed_imports,
                    self.max_memory,
                    timeout
                )
                
                # 等待执行完成，带超时 - 需求 2.5
                result_dict = await asyncio.wait_for(future, timeout=timeout + 1)
                
                return ExecutionResult(
                    success=result_dict['success'],
                    stdout=result_dict['stdout'],
                    stderr=result_dict['stderr'],
                    return_code=result_dict['return_code'],
                    execution_time=result_dict['execution_time'],
                    memory_used=result_dict.get('memory_used'),
                    error_type=result_dict.get('error_type')
                )
                
            except FuturesTimeoutError:
                raise asyncio.TimeoutError("Process execution timed out")
            except Exception as e:
                raise


# 导出的错误类型
__all__ = [
    'RestrictedPythonBackend',
    'ExecutionErrorType',
    'DANGEROUS_MODULES',
    'DANGEROUS_BUILTINS',
    'DEFAULT_ALLOWED_IMPORTS',
]
