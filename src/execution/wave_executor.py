"""向后兼容模块 - 请使用 src.wave_executor 代替。

本模块保留用于向后兼容。
"""

from ..wave_executor import WaveExecutor

__all__ = [
    "WaveExecutor",
]
