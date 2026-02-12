"""Data analysis tool implementation.

提供数据分析能力，包括：
- 文本数据的统计分析
- CSV / JSON 数据解析与摘要
- 基础统计量计算（均值、中位数、标准差等）
- 数据分布描述

不依赖 pandas/numpy，使用标准库实现，确保零依赖。
"""

import csv
import io
import json
import math
import statistics
from typing import Dict, Any, List, Optional, Union

from ..models.tool import ToolDefinition


class DataAnalysisTool:
    """数据分析工具"""

    def __init__(self, max_data_size: int = 500000):
        """
        Args:
            max_data_size: 最大数据长度（字符）
        """
        self._max_data_size = max_data_size

    async def analyze(
        self,
        data: str,
        data_format: str = "auto",
        operation: str = "summary",
    ) -> Dict[str, Any]:
        """
        分析数据

        Args:
            data: 数据内容（CSV、JSON 或纯文本）
            data_format: 数据格式 (auto, csv, json, text)
            operation: 操作类型 (summary, statistics, distribution, query)

        Returns:
            分析结果
        """
        if not data or not data.strip():
            return {"success": False, "error": "数据内容为空"}

        if len(data) > self._max_data_size:
            return {"success": False, "error": f"数据过长，最大 {self._max_data_size} 字符"}

        # 自动检测格式
        if data_format == "auto":
            data_format = self._detect_format(data)

        # 解析数据
        parsed = self._parse_data(data, data_format)
        if not parsed["success"]:
            return parsed

        rows = parsed["rows"]
        headers = parsed.get("headers", [])

        # 执行操作
        if operation == "summary":
            return self._summarize(rows, headers, data_format)
        elif operation == "statistics":
            return self._compute_statistics(rows, headers)
        elif operation == "distribution":
            return self._compute_distribution(rows, headers)
        elif operation == "query":
            return self._summarize(rows, headers, data_format)
        else:
            return {"success": False, "error": f"未知操作: {operation}"}

    def _detect_format(self, data: str) -> str:
        """自动检测数据格式"""
        stripped = data.strip()

        # JSON
        if stripped.startswith(("{", "[")):
            try:
                json.loads(stripped)
                return "json"
            except json.JSONDecodeError:
                pass

        # CSV（包含逗号分隔且有多行）
        lines = stripped.split("\n")
        if len(lines) > 1:
            first_line_commas = lines[0].count(",")
            if first_line_commas > 0:
                # 检查多行逗号数量是否一致
                consistent = sum(
                    1 for line in lines[1:5] if line.count(",") == first_line_commas
                )
                if consistent >= min(len(lines) - 1, 3):
                    return "csv"

            # TSV
            first_line_tabs = lines[0].count("\t")
            if first_line_tabs > 0:
                consistent = sum(
                    1 for line in lines[1:5] if line.count("\t") == first_line_tabs
                )
                if consistent >= min(len(lines) - 1, 3):
                    return "csv"  # csv reader 也可以处理 TSV

        return "text"

    def _parse_data(self, data: str, data_format: str) -> Dict[str, Any]:
        """解析数据为统一的行列格式"""
        if data_format == "csv":
            return self._parse_csv(data)
        elif data_format == "json":
            return self._parse_json(data)
        elif data_format == "text":
            return self._parse_text(data)
        else:
            return {"success": False, "error": f"不支持的格式: {data_format}"}

    def _parse_csv(self, data: str) -> Dict[str, Any]:
        """解析 CSV 数据"""
        try:
            # 自动检测分隔符
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(data[:2000])
            except csv.Error:
                dialect = csv.excel

            reader = csv.reader(io.StringIO(data), dialect)
            all_rows = list(reader)

            if not all_rows:
                return {"success": False, "error": "CSV 数据为空"}

            # 尝试检测是否有表头
            has_header = sniffer.has_header(data[:2000]) if len(all_rows) > 1 else False

            if has_header:
                headers = all_rows[0]
                rows = all_rows[1:]
            else:
                headers = [f"col_{i}" for i in range(len(all_rows[0]))]
                rows = all_rows

            return {
                "success": True,
                "headers": headers,
                "rows": rows,
                "has_header": has_header,
            }
        except Exception as e:
            return {"success": False, "error": f"CSV 解析失败: {e}"}

    def _parse_json(self, data: str) -> Dict[str, Any]:
        """解析 JSON 数据"""
        try:
            parsed = json.loads(data.strip())

            if isinstance(parsed, list):
                if not parsed:
                    return {"success": False, "error": "JSON 数组为空"}

                # 对象数组
                if isinstance(parsed[0], dict):
                    all_keys = set()
                    for item in parsed:
                        if isinstance(item, dict):
                            all_keys.update(item.keys())
                    headers = sorted(all_keys)
                    rows = []
                    for item in parsed:
                        if isinstance(item, dict):
                            rows.append([str(item.get(h, "")) for h in headers])
                    return {"success": True, "headers": headers, "rows": rows}

                # 简单值数组
                return {
                    "success": True,
                    "headers": ["value"],
                    "rows": [[str(v)] for v in parsed],
                }

            elif isinstance(parsed, dict):
                # 单个对象
                headers = list(parsed.keys())
                rows = [[str(v) for v in parsed.values()]]
                return {"success": True, "headers": headers, "rows": rows}

            return {"success": False, "error": "JSON 格式无法转换为表格数据"}

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON 解析失败: {e}"}

    def _parse_text(self, data: str) -> Dict[str, Any]:
        """解析纯文本数据（按行分割）"""
        lines = [line for line in data.strip().split("\n") if line.strip()]
        if not lines:
            return {"success": False, "error": "文本数据为空"}

        return {
            "success": True,
            "headers": ["line"],
            "rows": [[line] for line in lines],
        }

    def _summarize(
        self, rows: List[List[str]], headers: List[str], data_format: str
    ) -> Dict[str, Any]:
        """生成数据摘要"""
        total_rows = len(rows)
        total_cols = len(headers)

        # 列类型检测
        column_info = []
        for col_idx, header in enumerate(headers):
            col_values = [row[col_idx] for row in rows if col_idx < len(row)]
            non_empty = [v for v in col_values if v.strip()]
            null_count = len(col_values) - len(non_empty)

            # 尝试检测数值列
            numeric_values = []
            for v in non_empty:
                try:
                    numeric_values.append(float(v))
                except ValueError:
                    pass

            is_numeric = len(numeric_values) > len(non_empty) * 0.7 and len(numeric_values) > 0
            unique_count = len(set(non_empty))

            info: Dict[str, Any] = {
                "name": header,
                "type": "numeric" if is_numeric else "text",
                "non_null": len(non_empty),
                "null": null_count,
                "unique": unique_count,
            }

            if is_numeric and numeric_values:
                info["min"] = min(numeric_values)
                info["max"] = max(numeric_values)
                info["mean"] = round(statistics.mean(numeric_values), 4)
            elif non_empty:
                # 文本列：显示前几个唯一值样例
                sample_values = sorted(set(non_empty))[:5]
                info["sample_values"] = sample_values

            column_info.append(info)

        # 显示前几行数据
        preview_rows = rows[:5]
        preview = [dict(zip(headers, row)) for row in preview_rows]

        return {
            "success": True,
            "format": data_format,
            "total_rows": total_rows,
            "total_columns": total_cols,
            "columns": column_info,
            "preview": preview,
        }

    def _compute_statistics(
        self, rows: List[List[str]], headers: List[str]
    ) -> Dict[str, Any]:
        """计算统计量"""
        stats_result = {}

        for col_idx, header in enumerate(headers):
            col_values = [row[col_idx] for row in rows if col_idx < len(row)]
            non_empty = [v for v in col_values if v.strip()]

            numeric_values = []
            for v in non_empty:
                try:
                    numeric_values.append(float(v))
                except ValueError:
                    pass

            if len(numeric_values) >= 2:
                sorted_vals = sorted(numeric_values)
                n = len(sorted_vals)
                q1_idx = n // 4
                q3_idx = (3 * n) // 4

                stats_result[header] = {
                    "count": n,
                    "mean": round(statistics.mean(numeric_values), 4),
                    "median": round(statistics.median(numeric_values), 4),
                    "stdev": round(statistics.stdev(numeric_values), 4),
                    "min": min(numeric_values),
                    "max": max(numeric_values),
                    "q1": sorted_vals[q1_idx],
                    "q3": sorted_vals[q3_idx],
                    "range": round(max(numeric_values) - min(numeric_values), 4),
                }
            elif len(numeric_values) == 1:
                stats_result[header] = {
                    "count": 1,
                    "mean": numeric_values[0],
                    "median": numeric_values[0],
                    "min": numeric_values[0],
                    "max": numeric_values[0],
                }
            else:
                # 文本列统计
                stats_result[header] = {
                    "count": len(non_empty),
                    "unique": len(set(non_empty)),
                    "type": "text",
                    "most_common": self._most_common(non_empty, 5),
                }

        return {
            "success": True,
            "total_rows": len(rows),
            "statistics": stats_result,
        }

    def _compute_distribution(
        self, rows: List[List[str]], headers: List[str]
    ) -> Dict[str, Any]:
        """计算数据分布"""
        distributions = {}

        for col_idx, header in enumerate(headers):
            col_values = [row[col_idx] for row in rows if col_idx < len(row)]
            non_empty = [v for v in col_values if v.strip()]

            numeric_values = []
            for v in non_empty:
                try:
                    numeric_values.append(float(v))
                except ValueError:
                    pass

            if len(numeric_values) >= 5:
                # 数值列直方图
                min_val = min(numeric_values)
                max_val = max(numeric_values)

                if min_val == max_val:
                    distributions[header] = {
                        "type": "constant",
                        "value": min_val,
                        "count": len(numeric_values),
                    }
                else:
                    num_bins = min(10, int(math.sqrt(len(numeric_values))))
                    bin_width = (max_val - min_val) / num_bins
                    bins = [0] * num_bins
                    for v in numeric_values:
                        bin_idx = min(int((v - min_val) / bin_width), num_bins - 1)
                        bins[bin_idx] += 1

                    histogram = []
                    for i in range(num_bins):
                        low = round(min_val + i * bin_width, 4)
                        high = round(min_val + (i + 1) * bin_width, 4)
                        histogram.append({
                            "range": f"{low} ~ {high}",
                            "count": bins[i],
                        })

                    distributions[header] = {
                        "type": "numeric",
                        "histogram": histogram,
                    }
            else:
                # 文本列频率
                distributions[header] = {
                    "type": "categorical",
                    "frequency": self._most_common(non_empty, 10),
                }

        return {
            "success": True,
            "total_rows": len(rows),
            "distributions": distributions,
        }

    def _most_common(self, values: List[str], n: int = 5) -> List[Dict[str, Any]]:
        """获取最常见的值"""
        freq: Dict[str, int] = {}
        for v in values:
            freq[v] = freq.get(v, 0) + 1

        sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:n]
        return [{"value": k, "count": v} for k, v in sorted_freq]

    def get_tool_definition(self) -> ToolDefinition:
        """获取工具定义"""
        return ToolDefinition(
            name="data_analysis",
            description="分析结构化数据（CSV、JSON），提供数据摘要、统计量计算和分布分析。",
            parameters_schema={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "要分析的数据内容（CSV、JSON 或纯文本）",
                    },
                    "data_format": {
                        "type": "string",
                        "description": "数据格式",
                        "enum": ["auto", "csv", "json", "text"],
                        "default": "auto",
                    },
                    "operation": {
                        "type": "string",
                        "description": "分析操作类型",
                        "enum": ["summary", "statistics", "distribution"],
                        "default": "summary",
                    },
                },
                "required": ["data"],
            },
            handler=self._handle_analyze,
            timeout=30.0,
        )

    async def _handle_analyze(
        self,
        data: str,
        data_format: str = "auto",
        operation: str = "summary",
    ) -> Dict[str, Any]:
        """工具调用处理函数"""
        return await self.analyze(data, data_format, operation)


def create_data_analysis_tool(max_data_size: int = 500000) -> ToolDefinition:
    """
    创建数据分析工具定义

    Args:
        max_data_size: 最大数据长度

    Returns:
        工具定义
    """
    tool = DataAnalysisTool(max_data_size=max_data_size)
    return tool.get_tool_definition()
