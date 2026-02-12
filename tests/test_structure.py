"""结构验证单元测试。

验证重构后的目录结构、文件存在性和向后兼容性。
"""

import os
import pytest
from pathlib import Path


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"


class TestDirectoryStructure:
    """测试目录结构。"""
    
    def test_core_subpackage_exists(self):
        """验证 core 子包存在。"""
        assert (SRC_DIR / "core").is_dir()
        assert (SRC_DIR / "core" / "__init__.py").is_file()
    
    def test_execution_subpackage_exists(self):
        """验证 execution 子包存在。"""
        assert (SRC_DIR / "execution").is_dir()
        assert (SRC_DIR / "execution" / "__init__.py").is_file()
    
    def test_output_subpackage_exists(self):
        """验证 output 子包存在。"""
        assert (SRC_DIR / "output").is_dir()
        assert (SRC_DIR / "output" / "__init__.py").is_file()
    
    def test_memory_subpackage_exists(self):
        """验证 memory 子包存在。"""
        assert (SRC_DIR / "memory").is_dir()
        assert (SRC_DIR / "memory" / "__init__.py").is_file()
    
    def test_main_agent_subpackage_exists(self):
        """验证 main_agent 子包存在。"""
        main_agent_dir = SRC_DIR / "core" / "main_agent"
        assert main_agent_dir.is_dir()
        assert (main_agent_dir / "__init__.py").is_file()
        assert (main_agent_dir / "agent.py").is_file()
        assert (main_agent_dir / "executor.py").is_file()
        assert (main_agent_dir / "monitor.py").is_file()
        assert (main_agent_dir / "planner.py").is_file()
    
    def test_supervisor_subpackage_exists(self):
        """验证 supervisor 子包存在。"""
        supervisor_dir = SRC_DIR / "core" / "supervisor"
        assert supervisor_dir.is_dir()
        assert (supervisor_dir / "__init__.py").is_file()
        assert (supervisor_dir / "flow.py").is_file()
    
    def test_utils_logging_exists(self):
        """验证日志模块存在。"""
        assert (SRC_DIR / "utils" / "logging.py").is_file()


class TestBackwardCompatibility:
    """测试向后兼容性。"""
    
    def test_import_from_src(self):
        """验证从 src 导入核心类。"""
        from src import AgentSwarm, MainAgent, Supervisor
        assert AgentSwarm is not None
        assert MainAgent is not None
        assert Supervisor is not None
    
    def test_import_from_old_paths(self):
        """验证旧路径导入仍然可用。"""
        from src.agent_swarm import AgentSwarm, AgentSwarmConfig
        from src.main_agent import MainAgent, MainAgentConfig
        from src.task_decomposer import TaskDecomposer
        from src.quality_assurance import QualityAssurance
        
        assert AgentSwarm is not None
        assert AgentSwarmConfig is not None
        assert MainAgent is not None
        assert MainAgentConfig is not None
        assert TaskDecomposer is not None
        assert QualityAssurance is not None
    
    def test_import_from_new_paths(self):
        """验证新路径导入可用。"""
        from src.core import TaskDecomposer, QualityAssurance
        from src.core.main_agent import MainAgent
        from src.execution import AgentScheduler, WaveExecutor
        from src.output import ResultAggregator
        from src.memory import MemoryManager
        
        assert TaskDecomposer is not None
        assert QualityAssurance is not None
        assert MainAgent is not None
        assert AgentScheduler is not None
        assert WaveExecutor is not None
        assert ResultAggregator is not None
        assert MemoryManager is not None
    
    def test_class_aliases(self):
        """验证类别名可用。"""
        from src.output import ResultAggregator, ResultAggregatorImpl
        from src.execution.sub_agent import SubAgentExecutor, SubAgentImpl
        
        # ResultAggregator 应该是 ResultAggregatorImpl 的别名
        assert ResultAggregator is ResultAggregatorImpl
        # SubAgentExecutor 应该是 SubAgentImpl 的别名
        assert SubAgentExecutor is SubAgentImpl


class TestLoggingModule:
    """测试日志模块。"""
    
    def test_get_logger(self):
        """验证 get_logger 函数。"""
        from src.utils.logging import get_logger
        
        logger = get_logger("test_module")
        assert logger is not None
        assert logger.name == "qwen_agent_swarm.test_module"
    
    def test_configure_root_logger(self):
        """验证 configure_root_logger 函数。"""
        from src.utils.logging import configure_root_logger
        
        # 应该不抛出异常
        configure_root_logger()


class TestReadmeContent:
    """测试 README 内容。"""
    
    def test_readme_exists(self):
        """验证 README.md 存在。"""
        readme_path = PROJECT_ROOT / "README.md"
        assert readme_path.is_file()
    
    def test_readme_no_absolute_paths(self):
        """验证 README 中没有绝对路径。"""
        readme_path = PROJECT_ROOT / "README.md"
        content = readme_path.read_text(encoding="utf-8")
        
        # 检查是否包含 file:/// 或 /Users/ 开头的路径
        assert "file:///" not in content
        assert "/Users/" not in content
    
    def test_readme_has_required_sections(self):
        """验证 README 包含必要章节。"""
        readme_path = PROJECT_ROOT / "README.md"
        content = readme_path.read_text(encoding="utf-8")
        
        required_sections = [
            "项目简介",
            "核心特性",
            "架构",
            "安装",
            "快速开始",
            "配置",
            "自定义工具",
            "Web",
            "开发",
        ]
        
        for section in required_sections:
            assert section in content, f"README 缺少章节: {section}"


class TestInitFiles:
    """测试 __init__.py 文件。"""
    
    def test_subpackage_init_has_docstring(self):
        """验证子包 __init__.py 有文档字符串。"""
        subpackages = [
            SRC_DIR / "core" / "__init__.py",
            SRC_DIR / "execution" / "__init__.py",
            SRC_DIR / "output" / "__init__.py",
            SRC_DIR / "memory" / "__init__.py",
            SRC_DIR / "core" / "main_agent" / "__init__.py",
            SRC_DIR / "core" / "supervisor" / "__init__.py",
        ]
        
        for init_file in subpackages:
            if init_file.exists():
                content = init_file.read_text(encoding="utf-8")
                # 检查是否以 """ 或 ''' 开头（文档字符串）
                stripped = content.lstrip()
                assert stripped.startswith('"""') or stripped.startswith("'''"), \
                    f"{init_file} 缺少文档字符串"
