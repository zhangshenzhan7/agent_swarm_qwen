"""统一日志配置模块。

提供标准化的日志工厂函数和根 logger 配置，确保整个项目使用一致的日志格式和命名规范。
所有 logger 名称遵循 ``qwen_agent_swarm.{module_name}`` 的层级命名约定。
"""

import logging
from typing import Optional

# 默认日志格式：时间戳 [级别] 模块名: 消息
DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
# 默认日期格式
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
# 根 logger 名称前缀
_ROOT_LOGGER_NAME = "qwen_agent_swarm"


def get_logger(module_name: str, level: Optional[int] = None) -> logging.Logger:
    """获取标准化的 logger 实例。

    根据模块名称创建或获取一个 logger，名称格式为
    ``qwen_agent_swarm.{module_name}``。当 ``module_name`` 为空字符串或
    ``None`` 时，回退到默认名称 ``qwen_agent_swarm``。

    Args:
        module_name: 模块名称，将作为 logger 名称的一部分。
        level: 日志级别，默认不设置（继承父 logger 级别）。

    Returns:
        配置好的 Logger 实例。
    """
    if not module_name:
        logger_name = _ROOT_LOGGER_NAME
    else:
        logger_name = f"{_ROOT_LOGGER_NAME}.{module_name}"

    logger = logging.getLogger(logger_name)

    if level is not None:
        logger.setLevel(level)

    return logger


def configure_root_logger(
    level: int = logging.INFO,
    format_str: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
) -> None:
    """配置根 logger。

    为 ``qwen_agent_swarm`` 根 logger 添加 StreamHandler 并设置统一的日志格式。
    如果根 logger 已有 handler，则不会重复添加。

    Args:
        level: 日志级别，默认为 ``logging.INFO``。
        format_str: 日志格式字符串，默认包含时间戳、级别、模块名和消息。
        date_format: 日期格式字符串，默认为 ``%Y-%m-%d %H:%M:%S``。
    """
    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    root_logger.setLevel(level)

    # 避免重复添加 handler
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(format_str, datefmt=date_format)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
