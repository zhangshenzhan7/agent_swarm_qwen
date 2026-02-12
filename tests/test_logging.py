"""日志基础设施测试。

包含 get_logger / configure_root_logger 的单元测试。
"""

import logging

import pytest

from src.utils.logging import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_FORMAT,
    _ROOT_LOGGER_NAME,
    configure_root_logger,
    get_logger,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _cleanup_loggers():
    """每个测试后清理 qwen_agent_swarm logger 的 handler，避免测试间干扰。"""
    yield
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.handlers.clear()
    root.setLevel(logging.WARNING)  # reset to default


# ---------------------------------------------------------------------------
# get_logger 单元测试
# ---------------------------------------------------------------------------

class TestGetLogger:
    """get_logger 工厂函数测试。"""

    def test_returns_logger_with_correct_name(self):
        """普通模块名应返回 qwen_agent_swarm.{module_name} 格式的 logger。"""
        logger = get_logger("core.main_agent")
        assert logger.name == "qwen_agent_swarm.core.main_agent"

    def test_simple_module_name(self):
        """简单模块名也应正确拼接。"""
        logger = get_logger("scheduler")
        assert logger.name == "qwen_agent_swarm.scheduler"

    def test_empty_string_falls_back_to_root(self):
        """空字符串应回退到默认 logger 名称。"""
        logger = get_logger("")
        assert logger.name == "qwen_agent_swarm"

    def test_none_falls_back_to_root(self):
        """None 应回退到默认 logger 名称。"""
        logger = get_logger(None)
        assert logger.name == "qwen_agent_swarm"

    def test_custom_level(self):
        """传入 level 参数时应设置 logger 级别。"""
        logger = get_logger("test_level", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_default_level_not_set(self):
        """不传 level 时不应主动设置级别（继承父 logger）。"""
        logger = get_logger("test_no_level")
        # logging.NOTSET == 0, 表示未显式设置
        assert logger.level == logging.NOTSET

    def test_returns_same_logger_instance(self):
        """相同模块名应返回同一个 logger 实例。"""
        a = get_logger("same_module")
        b = get_logger("same_module")
        assert a is b


# ---------------------------------------------------------------------------
# configure_root_logger 单元测试
# ---------------------------------------------------------------------------

class TestConfigureRootLogger:
    """configure_root_logger 配置函数测试。"""

    def test_adds_stream_handler(self):
        """调用后应为根 logger 添加一个 StreamHandler。"""
        configure_root_logger()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_sets_level(self):
        """应设置根 logger 的级别。"""
        configure_root_logger(level=logging.DEBUG)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        assert root.level == logging.DEBUG

    def test_no_duplicate_handlers(self):
        """多次调用不应重复添加 handler。"""
        configure_root_logger()
        configure_root_logger()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        assert len(root.handlers) == 1

    def test_custom_format(self):
        """自定义格式字符串应被应用到 handler 的 formatter。"""
        custom_fmt = "%(levelname)s - %(message)s"
        configure_root_logger(format_str=custom_fmt)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        formatter = root.handlers[0].formatter
        assert formatter._fmt == custom_fmt

    def test_default_format(self):
        """默认格式应与 DEFAULT_FORMAT 一致。"""
        configure_root_logger()
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        formatter = root.handlers[0].formatter
        assert formatter._fmt == DEFAULT_FORMAT
        assert formatter.datefmt == DEFAULT_DATE_FORMAT

    def test_child_logger_inherits(self):
        """子 logger 应继承根 logger 的配置。"""
        configure_root_logger(level=logging.DEBUG)
        child = get_logger("child_test")
        # 子 logger 的 effective level 应继承父级
        assert child.getEffectiveLevel() == logging.DEBUG
