"""Tool configuration management module.

This module provides configuration management for tools including:
- CodeExecutionConfig: Configuration for code execution tool
- ToolConfig: Main configuration manager supporting environment variables and config files

联网搜索和网页抽取能力已通过 DashScope API 内置提供（enable_search + search_strategy），
无需单独的搜索工具配置。
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import yaml


@dataclass
class CodeExecutionConfig:
    """代码执行工具配置
    
    Attributes:
        backend: 执行后端类型 (restricted, docker, aliyun_fc)
        timeout: 执行超时时间（秒）
        max_memory: 最大内存限制（字节）
        max_output_size: 最大输出大小（字符）
        allowed_languages: 允许的编程语言列表
        docker_image: Docker 镜像名称
        docker_memory_limit: Docker 内存限制
        docker_cpu_limit: Docker CPU 限制
        aliyun_fc_access_key: 阿里云 FC Access Key
        aliyun_fc_secret_key: 阿里云 FC Secret Key
        aliyun_fc_region: 阿里云 FC 区域
        aliyun_fc_service: 阿里云 FC 服务名称
    """
    backend: str = "restricted"
    timeout: float = 30.0
    max_memory: int = 128 * 1024 * 1024  # 128MB
    max_output_size: int = 10000
    allowed_languages: List[str] = field(default_factory=lambda: ["python", "shell"])
    # Docker 配置
    docker_image: str = "python:3.11-slim"
    docker_memory_limit: str = "128m"
    docker_cpu_limit: float = 0.5
    # 阿里云 FC 配置
    aliyun_fc_access_key: Optional[str] = None
    aliyun_fc_secret_key: Optional[str] = None
    aliyun_fc_region: Optional[str] = None
    aliyun_fc_service: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "backend": self.backend,
            "timeout": self.timeout,
            "max_memory": self.max_memory,
            "max_output_size": self.max_output_size,
            "allowed_languages": self.allowed_languages,
            "docker_image": self.docker_image,
            "docker_memory_limit": self.docker_memory_limit,
            "docker_cpu_limit": self.docker_cpu_limit,
            "aliyun_fc_access_key": self.aliyun_fc_access_key,
            "aliyun_fc_secret_key": self.aliyun_fc_secret_key,
            "aliyun_fc_region": self.aliyun_fc_region,
            "aliyun_fc_service": self.aliyun_fc_service,
        }


# Valid backend options
VALID_EXEC_BACKENDS = ["restricted", "docker", "aliyun_fc"]
VALID_LANGUAGES = ["python", "shell", "javascript"]


class ToolConfig:
    """工具配置管理
    
    支持从环境变量和配置文件加载配置，并提供配置验证功能。
    
    配置优先级（从高到低）：
    1. 环境变量
    2. 配置文件
    3. 默认值
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """初始化配置管理器
        
        Args:
            config_file: 配置文件路径（可选）
        """
        self._code_execution_config = CodeExecutionConfig()
        self._config_file = config_file
        
        # 如果提供了配置文件，先从文件加载
        if config_file:
            self.load_from_file(config_file)
        
        # 然后从环境变量加载（环境变量优先级更高）
        self.load_from_env()
    
    def load_from_env(self) -> None:
        """从环境变量加载配置
        
        环境变量映射：
        - TOOL_EXEC_BACKEND -> code_execution.backend
        - TOOL_EXEC_TIMEOUT -> code_execution.timeout
        - TOOL_EXEC_MAX_MEMORY -> code_execution.max_memory
        - TOOL_EXEC_MAX_OUTPUT_SIZE -> code_execution.max_output_size
        - TOOL_EXEC_ALLOWED_LANGUAGES -> code_execution.allowed_languages (逗号分隔)
        - TOOL_EXEC_DOCKER_IMAGE -> code_execution.docker_image
        - TOOL_EXEC_DOCKER_MEMORY_LIMIT -> code_execution.docker_memory_limit
        - TOOL_EXEC_DOCKER_CPU_LIMIT -> code_execution.docker_cpu_limit
        - ALIYUN_ACCESS_KEY -> 阿里云通用 Access Key
        - ALIYUN_SECRET_KEY -> 阿里云通用 Secret Key
        - ALIYUN_FC_REGION -> 阿里云 FC 区域
        - ALIYUN_FC_SERVICE -> 阿里云 FC 服务名称
        """
        # Code Execution 配置
        if backend := os.environ.get("TOOL_EXEC_BACKEND"):
            self._code_execution_config.backend = backend
        
        if timeout := os.environ.get("TOOL_EXEC_TIMEOUT"):
            try:
                self._code_execution_config.timeout = float(timeout)
            except ValueError:
                pass
        
        if max_memory := os.environ.get("TOOL_EXEC_MAX_MEMORY"):
            try:
                self._code_execution_config.max_memory = int(max_memory)
            except ValueError:
                pass
        
        if max_output_size := os.environ.get("TOOL_EXEC_MAX_OUTPUT_SIZE"):
            try:
                self._code_execution_config.max_output_size = int(max_output_size)
            except ValueError:
                pass
        
        if allowed_languages := os.environ.get("TOOL_EXEC_ALLOWED_LANGUAGES"):
            # 逗号分隔的语言列表
            languages = [lang.strip() for lang in allowed_languages.split(",")]
            self._code_execution_config.allowed_languages = languages
        
        if docker_image := os.environ.get("TOOL_EXEC_DOCKER_IMAGE"):
            self._code_execution_config.docker_image = docker_image
        
        if docker_memory_limit := os.environ.get("TOOL_EXEC_DOCKER_MEMORY_LIMIT"):
            self._code_execution_config.docker_memory_limit = docker_memory_limit
        
        if docker_cpu_limit := os.environ.get("TOOL_EXEC_DOCKER_CPU_LIMIT"):
            try:
                self._code_execution_config.docker_cpu_limit = float(docker_cpu_limit)
            except ValueError:
                pass
        
        # 阿里云通用配置
        if access_key := os.environ.get("ALIYUN_ACCESS_KEY"):
            self._code_execution_config.aliyun_fc_access_key = access_key
        
        if secret_key := os.environ.get("ALIYUN_SECRET_KEY"):
            self._code_execution_config.aliyun_fc_secret_key = secret_key
        
        if fc_region := os.environ.get("ALIYUN_FC_REGION"):
            self._code_execution_config.aliyun_fc_region = fc_region
        
        if fc_service := os.environ.get("ALIYUN_FC_SERVICE"):
            self._code_execution_config.aliyun_fc_service = fc_service
    
    def load_from_file(self, path: str) -> None:
        """从配置文件加载配置
        
        支持 YAML 格式的配置文件。
        
        Args:
            path: 配置文件路径
            
        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: 配置文件格式错误
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        if not config_data:
            return
        
        tools_config = config_data.get("tools", {})
        
        # 加载 Code Execution 配置
        code_exec_data = tools_config.get("code_execution", {})
        if code_exec_data:
            self._load_code_execution_config(code_exec_data)
    
    def _load_code_execution_config(self, data: Dict[str, Any]) -> None:
        """从字典加载 Code Execution 配置"""
        if "backend" in data:
            self._code_execution_config.backend = data["backend"]
        if "timeout" in data:
            self._code_execution_config.timeout = float(data["timeout"])
        if "max_memory" in data:
            self._code_execution_config.max_memory = int(data["max_memory"])
        if "max_output_size" in data:
            self._code_execution_config.max_output_size = int(data["max_output_size"])
        if "allowed_languages" in data:
            self._code_execution_config.allowed_languages = list(data["allowed_languages"])
        
        # Docker 配置
        docker_config = data.get("docker", {})
        if "image" in docker_config:
            self._code_execution_config.docker_image = docker_config["image"]
        if "memory_limit" in docker_config:
            self._code_execution_config.docker_memory_limit = docker_config["memory_limit"]
        if "cpu_limit" in docker_config:
            self._code_execution_config.docker_cpu_limit = float(docker_config["cpu_limit"])
        
        # 直接在 code_execution 下的 docker 配置
        if "docker_image" in data:
            self._code_execution_config.docker_image = data["docker_image"]
        if "docker_memory_limit" in data:
            self._code_execution_config.docker_memory_limit = data["docker_memory_limit"]
        if "docker_cpu_limit" in data:
            self._code_execution_config.docker_cpu_limit = float(data["docker_cpu_limit"])
        
        # 阿里云 FC 配置
        if "aliyun_fc_access_key" in data:
            self._code_execution_config.aliyun_fc_access_key = data["aliyun_fc_access_key"]
        if "aliyun_fc_secret_key" in data:
            self._code_execution_config.aliyun_fc_secret_key = data["aliyun_fc_secret_key"]
        if "aliyun_fc_region" in data:
            self._code_execution_config.aliyun_fc_region = data["aliyun_fc_region"]
        if "aliyun_fc_service" in data:
            self._code_execution_config.aliyun_fc_service = data["aliyun_fc_service"]
    
    def get_code_execution_config(self) -> CodeExecutionConfig:
        """获取代码执行配置
        
        Returns:
            CodeExecutionConfig 实例
        """
        return self._code_execution_config
    
    def validate(self) -> List[str]:
        """验证配置参数的有效性
        
        Returns:
            验证错误列表，如果配置有效则返回空列表
        """
        return self._validate_code_execution_config()
    
    def _validate_code_execution_config(self) -> List[str]:
        """验证 Code Execution 配置"""
        errors: List[str] = []
        config = self._code_execution_config
        
        # 验证 backend
        if config.backend not in VALID_EXEC_BACKENDS:
            errors.append(
                f"Invalid code_execution.backend: '{config.backend}'. "
                f"Valid options: {VALID_EXEC_BACKENDS}"
            )
        
        # 验证 timeout
        if config.timeout <= 0:
            errors.append(
                f"Invalid code_execution.timeout: {config.timeout}. "
                "Must be a positive number."
            )
        
        # 验证 max_memory
        if config.max_memory <= 0:
            errors.append(
                f"Invalid code_execution.max_memory: {config.max_memory}. "
                "Must be a positive integer."
            )
        
        # 验证 max_output_size
        if config.max_output_size <= 0:
            errors.append(
                f"Invalid code_execution.max_output_size: {config.max_output_size}. "
                "Must be a positive integer."
            )
        
        # 验证 allowed_languages
        if not config.allowed_languages:
            errors.append(
                "Invalid code_execution.allowed_languages: empty list. "
                "At least one language must be allowed."
            )
        else:
            for lang in config.allowed_languages:
                if lang not in VALID_LANGUAGES:
                    errors.append(
                        f"Invalid language in code_execution.allowed_languages: '{lang}'. "
                        f"Valid options: {VALID_LANGUAGES}"
                    )
        
        # 验证 docker_cpu_limit
        if config.docker_cpu_limit <= 0:
            errors.append(
                f"Invalid code_execution.docker_cpu_limit: {config.docker_cpu_limit}. "
                "Must be a positive number."
            )
        
        # 如果使用 Docker 后端，验证 Docker 配置
        if config.backend == "docker":
            if not config.docker_image:
                errors.append(
                    "Missing docker_image for docker execution backend."
                )
        
        # 如果使用阿里云 FC 后端，验证必需的配置
        if config.backend == "aliyun_fc":
            if not config.aliyun_fc_access_key:
                errors.append(
                    "Missing aliyun_fc_access_key for aliyun_fc execution backend."
                )
            if not config.aliyun_fc_secret_key:
                errors.append(
                    "Missing aliyun_fc_secret_key for aliyun_fc execution backend."
                )
            if not config.aliyun_fc_region:
                errors.append(
                    "Missing aliyun_fc_region for aliyun_fc execution backend."
                )
            if not config.aliyun_fc_service:
                errors.append(
                    "Missing aliyun_fc_service for aliyun_fc execution backend."
                )
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典
        
        Returns:
            配置字典
        """
        return {
            "tools": {
                "code_execution": self._code_execution_config.to_dict(),
            }
        }
    
    def __repr__(self) -> str:
        """返回配置的字符串表示"""
        return (
            f"ToolConfig(\n"
            f"  code_execution={self._code_execution_config}\n"
            f")"
        )
