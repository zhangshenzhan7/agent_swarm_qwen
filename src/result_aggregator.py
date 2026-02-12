"""Result Aggregator implementation."""

import time
from collections import Counter
from typing import List, Dict, Any, Optional, Set

from .interfaces.result_aggregator import (
    IResultAggregator,
    ConflictResolution,
    ResultConflict,
    AggregationResult,
)
from .models.result import SubTaskResult
from .models.task import TaskDecomposition, SubTask
from .models.agent import SubAgent
from .models.enums import AgentStatus, OutputType


class ResultAggregatorError(Exception):
    """结果聚合器错误"""
    pass


class ValidationError(ResultAggregatorError):
    """验证错误"""
    pass


class ResultAggregatorImpl(IResultAggregator):
    """结果聚合器实现"""
    
    def __init__(self):
        """初始化结果聚合器"""
        self._validation_errors: List[Dict[str, Any]] = []
    
    async def collect_results(self, agents: List[SubAgent]) -> List[SubTaskResult]:
        """
        收集所有子智能体的结果
        
        从已完成或失败的子智能体中收集执行结果。
        只收集处于终态（COMPLETED, FAILED, TERMINATED）的智能体结果。
        
        Args:
            agents: 子智能体列表
            
        Returns:
            子任务结果列表
        """
        results: List[SubTaskResult] = []
        
        for agent in agents:
            # 只收集终态智能体的结果
            if agent.status in (
                AgentStatus.COMPLETED, 
                AgentStatus.FAILED, 
                AgentStatus.TERMINATED
            ):
                # 从 SubAgentImpl 获取结果（如果有 last_result 属性）
                if hasattr(agent, 'last_result') and agent.last_result is not None:
                    results.append(agent.last_result)
                elif hasattr(agent, '_last_result') and agent._last_result is not None:
                    results.append(agent._last_result)
                else:
                    # 如果没有结果，创建一个失败结果
                    result = SubTaskResult(
                        subtask_id=agent.assigned_subtask.id,
                        agent_id=agent.id,
                        success=False,
                        output=None,
                        error="No result available from agent",
                        tool_calls=[],
                        execution_time=0.0,
                        token_usage={},
                    )
                    results.append(result)
        
        return results
    
    async def validate_results(self, results: List[SubTaskResult]) -> List[SubTaskResult]:
        """
        验证结果的格式和完整性
        
        检查每个结果是否包含必要的字段，并验证数据类型。
        
        Args:
            results: 待验证的结果列表
            
        Returns:
            验证后的结果列表
        """
        self._validation_errors = []
        validated_results: List[SubTaskResult] = []
        
        for result in results:
            errors = self._validate_single_result(result)
            
            if errors:
                self._validation_errors.append({
                    "subtask_id": result.subtask_id,
                    "agent_id": result.agent_id,
                    "errors": errors,
                })
            
            # 即使有验证错误，也保留结果（标记为验证失败）
            validated_results.append(result)
        
        return validated_results
    
    def _validate_single_result(self, result: SubTaskResult) -> List[str]:
        """
        验证单个结果
        
        Args:
            result: 待验证的结果
            
        Returns:
            错误消息列表（空列表表示验证通过）
        """
        errors: List[str] = []
        
        # 验证必要字段
        if not result.subtask_id:
            errors.append("Missing subtask_id")
        
        if not result.agent_id:
            errors.append("Missing agent_id")
        
        # 验证执行时间
        if result.execution_time < 0:
            errors.append("Invalid execution_time: must be non-negative")
        
        # 验证成功结果必须有输出
        if result.success and result.output is None:
            errors.append("Successful result must have output")
        
        # 验证失败结果应该有错误信息
        if not result.success and not result.error:
            errors.append("Failed result should have error message")
        
        # 验证 token_usage 格式
        if result.token_usage:
            if not isinstance(result.token_usage, dict):
                errors.append("token_usage must be a dictionary")
        
        return errors
    
    def get_validation_errors(self) -> List[Dict[str, Any]]:
        """获取验证错误列表"""
        return list(self._validation_errors)


    async def detect_conflicts(self, results: List[SubTaskResult]) -> List[ResultConflict]:
        """
        检测结果之间的冲突
        
        检测以下类型的冲突：
        1. 重复子任务：同一子任务有多个结果
        2. 输出冲突：相关子任务的输出存在矛盾
        3. 状态不一致：依赖任务成功但被依赖任务失败
        
        Args:
            results: 结果列表
            
        Returns:
            检测到的冲突列表
        """
        conflicts: List[ResultConflict] = []
        
        # 检测重复子任务结果
        duplicate_conflicts = self._detect_duplicate_results(results)
        conflicts.extend(duplicate_conflicts)
        
        # 检测输出冲突（相似任务产生矛盾输出）
        output_conflicts = self._detect_output_conflicts(results)
        conflicts.extend(output_conflicts)
        
        return conflicts
    
    def _detect_duplicate_results(
        self, results: List[SubTaskResult]
    ) -> List[ResultConflict]:
        """
        检测重复的子任务结果
        
        Args:
            results: 结果列表
            
        Returns:
            重复冲突列表
        """
        conflicts: List[ResultConflict] = []
        
        # 按子任务ID分组
        subtask_results: Dict[str, List[SubTaskResult]] = {}
        for result in results:
            if result.subtask_id not in subtask_results:
                subtask_results[result.subtask_id] = []
            subtask_results[result.subtask_id].append(result)
        
        # 检测重复
        for subtask_id, result_list in subtask_results.items():
            if len(result_list) > 1:
                # 检查结果是否一致
                success_values = [r.success for r in result_list]
                if len(set(success_values)) > 1:
                    # 成功/失败状态不一致
                    conflict = ResultConflict(
                        subtask_ids=[subtask_id],
                        conflict_type="duplicate_inconsistent",
                        description=(
                            f"Subtask {subtask_id} has {len(result_list)} results "
                            f"with inconsistent success status"
                        ),
                    )
                    conflicts.append(conflict)
                else:
                    # 有重复但状态一致
                    conflict = ResultConflict(
                        subtask_ids=[subtask_id],
                        conflict_type="duplicate",
                        description=(
                            f"Subtask {subtask_id} has {len(result_list)} duplicate results"
                        ),
                    )
                    conflicts.append(conflict)
        
        return conflicts
    
    def _detect_output_conflicts(
        self, results: List[SubTaskResult]
    ) -> List[ResultConflict]:
        """
        检测输出冲突
        
        检测成功结果中可能存在的矛盾输出。
        
        Args:
            results: 结果列表
            
        Returns:
            输出冲突列表
        """
        conflicts: List[ResultConflict] = []
        
        # 只检查成功的结果
        successful_results = [r for r in results if r.success and r.output is not None]
        
        # 检测数值类型输出的冲突
        numeric_outputs: Dict[str, List[tuple]] = {}
        for result in successful_results:
            if isinstance(result.output, (int, float)):
                # 按输出类型分组
                key = "numeric"
                if key not in numeric_outputs:
                    numeric_outputs[key] = []
                numeric_outputs[key].append((result.subtask_id, result.output))
        
        # 检测数值输出的显著差异
        for key, outputs in numeric_outputs.items():
            if len(outputs) > 1:
                values = [v for _, v in outputs]
                if max(values) > 0 and min(values) > 0:
                    ratio = max(values) / min(values)
                    if ratio > 10:  # 差异超过10倍
                        conflict = ResultConflict(
                            subtask_ids=[sid for sid, _ in outputs],
                            conflict_type="output_divergence",
                            description=(
                                f"Numeric outputs have significant divergence "
                                f"(ratio: {ratio:.2f})"
                            ),
                        )
                        conflicts.append(conflict)
        
        return conflicts
    
    def resolve_conflict(
        self,
        conflict: ResultConflict,
        results: List[SubTaskResult],
        strategy: ConflictResolution,
    ) -> Optional[SubTaskResult]:
        """
        解决单个冲突
        
        Args:
            conflict: 要解决的冲突
            results: 相关结果列表
            strategy: 解决策略
            
        Returns:
            解决后选择的结果，如果无法解决返回 None
        """
        # 获取冲突相关的结果
        conflict_results = [
            r for r in results 
            if r.subtask_id in conflict.subtask_ids
        ]
        
        if not conflict_results:
            return None
        
        if strategy == ConflictResolution.FIRST_WINS:
            # 选择第一个结果
            conflict.resolution = "Selected first result"
            return conflict_results[0]
        
        elif strategy == ConflictResolution.LAST_WINS:
            # 选择最后一个结果
            conflict.resolution = "Selected last result"
            return conflict_results[-1]
        
        elif strategy == ConflictResolution.MAJORITY_VOTE:
            # 多数投票（基于成功/失败状态）
            success_count = sum(1 for r in conflict_results if r.success)
            failure_count = len(conflict_results) - success_count
            
            if success_count >= failure_count:
                # 选择第一个成功的结果
                for r in conflict_results:
                    if r.success:
                        conflict.resolution = f"Majority vote: success ({success_count}/{len(conflict_results)})"
                        return r
            else:
                # 选择第一个失败的结果
                for r in conflict_results:
                    if not r.success:
                        conflict.resolution = f"Majority vote: failure ({failure_count}/{len(conflict_results)})"
                        return r
            
            return conflict_results[0]
        
        elif strategy == ConflictResolution.MANUAL:
            # 手动解决，不自动选择
            conflict.resolution = "Requires manual resolution"
            return None
        
        return None

    async def aggregate(
        self, 
        results: List[SubTaskResult],
        decomposition: TaskDecomposition,
        conflict_resolution: ConflictResolution = ConflictResolution.MAJORITY_VOTE,
        output_type: OutputType = OutputType.REPORT
    ) -> AggregationResult:
        """
        聚合所有结果为最终输出
        
        按任务分解结构整合子结果，处理冲突，标注缺失部分。
        
        Args:
            results: 子任务结果列表
            decomposition: 原始任务分解
            conflict_resolution: 冲突解决策略
            output_type: 目标输出类型，默认为 REPORT 以保持向后兼容
            
        Returns:
            聚合结果
        """
        start_time = time.time()
        
        # 验证结果
        validated_results = await self.validate_results(results)
        
        # 检测冲突
        conflicts = await self.detect_conflicts(validated_results)
        
        # 解决冲突并去重
        resolved_results = self._resolve_conflicts_and_deduplicate(
            validated_results, conflicts, conflict_resolution
        )
        
        # 识别缺失的子任务
        missing_subtasks = self._identify_missing_subtasks(
            resolved_results, decomposition
        )
        
        # 按执行顺序整合结果
        integrated = self._integrate_results(
            resolved_results, decomposition, missing_subtasks, output_type
        )
        
        # 提取 combined_output 字符串作为 final_output
        if isinstance(integrated, dict):
            final_output = integrated.get("combined_output", "")
        else:
            final_output = str(integrated) if integrated else ""
        
        # 计算整体成功状态
        success = self._calculate_overall_success(
            resolved_results, missing_subtasks, decomposition
        )
        
        aggregation_time = time.time() - start_time
        
        return AggregationResult(
            task_id=decomposition.original_task_id,
            success=success,
            final_output=final_output,
            sub_results=resolved_results,
            conflicts=conflicts,
            missing_subtasks=missing_subtasks,
            aggregation_time=aggregation_time,
        )
    
    def _resolve_conflicts_and_deduplicate(
        self,
        results: List[SubTaskResult],
        conflicts: List[ResultConflict],
        strategy: ConflictResolution,
    ) -> List[SubTaskResult]:
        """
        解决冲突并去重
        
        Args:
            results: 结果列表
            conflicts: 冲突列表
            strategy: 解决策略
            
        Returns:
            去重后的结果列表
        """
        # 获取有冲突的子任务ID
        conflicting_subtask_ids: Set[str] = set()
        for conflict in conflicts:
            if conflict.conflict_type in ("duplicate", "duplicate_inconsistent"):
                conflicting_subtask_ids.update(conflict.subtask_ids)
        
        # 按子任务ID分组
        subtask_results: Dict[str, List[SubTaskResult]] = {}
        for result in results:
            if result.subtask_id not in subtask_results:
                subtask_results[result.subtask_id] = []
            subtask_results[result.subtask_id].append(result)
        
        # 去重
        resolved_results: List[SubTaskResult] = []
        for subtask_id, result_list in subtask_results.items():
            if len(result_list) == 1:
                resolved_results.append(result_list[0])
            else:
                # 有重复，需要解决
                # 找到对应的冲突
                related_conflict = None
                for conflict in conflicts:
                    if subtask_id in conflict.subtask_ids:
                        related_conflict = conflict
                        break
                
                if related_conflict:
                    resolved = self.resolve_conflict(
                        related_conflict, result_list, strategy
                    )
                    if resolved:
                        resolved_results.append(resolved)
                    else:
                        # 无法解决，保留第一个
                        resolved_results.append(result_list[0])
                else:
                    # 没有冲突记录，保留第一个
                    resolved_results.append(result_list[0])
        
        return resolved_results
    
    def _identify_missing_subtasks(
        self,
        results: List[SubTaskResult],
        decomposition: TaskDecomposition,
    ) -> List[str]:
        """
        识别缺失的子任务
        
        Args:
            results: 结果列表
            decomposition: 任务分解
            
        Returns:
            缺失的子任务ID列表
        """
        # 获取所有预期的子任务ID
        expected_subtask_ids = {st.id for st in decomposition.subtasks}
        
        # 获取已有结果的子任务ID
        result_subtask_ids = {r.subtask_id for r in results}
        
        # 计算缺失的子任务
        missing = expected_subtask_ids - result_subtask_ids
        
        return list(missing)
    
    def _integrate_results(
        self,
        results: List[SubTaskResult],
        decomposition: TaskDecomposition,
        missing_subtasks: List[str],
        output_type: OutputType = OutputType.REPORT,
    ) -> Dict[str, Any]:
        """
        整合结果为最终输出 - 根据 output_type 采用不同整合策略

        - CODE：按文件路径分组合并代码片段
        - COMPOSITE：按子任务输出类型分组
        - 其他类型（含 REPORT）：保持现有文本拼接逻辑

        Args:
            results: 结果列表
            decomposition: 任务分解
            missing_subtasks: 缺失的子任务ID列表
            output_type: 目标输出类型

        Returns:
            整合后的输出
        """
        # 创建子任务ID到结果的映射
        result_map: Dict[str, SubTaskResult] = {
            r.subtask_id: r for r in results
        }

        # 创建子任务ID到子任务的映射
        subtask_map: Dict[str, SubTask] = {
            st.id: st for st in decomposition.subtasks
        }

        # 收集所有成功的输出内容
        successful_outputs = []
        for result in results:
            if result.success and result.output is not None:
                subtask = subtask_map.get(result.subtask_id)
                successful_outputs.append({
                    "subtask_id": result.subtask_id,
                    "subtask_content": subtask.content if subtask else "Unknown",
                    "role": subtask.role_hint if subtask else "unknown",
                    "output": result.output,
                })

        # 根据 output_type 选择整合策略
        if output_type == OutputType.CODE:
            combined_output = self._integrate_code_results(successful_outputs)
        elif output_type == OutputType.COMPOSITE:
            combined_output = self._integrate_composite_results(successful_outputs)
        else:
            # REPORT 及其他类型：保持现有文本拼接逻辑
            combined_output = self._generate_combined_output(successful_outputs)

        # 按执行层组织详细结果
        execution_layers = []
        for layer_idx, layer in enumerate(decomposition.execution_order):
            layer_results: List[Dict[str, Any]] = []

            for subtask_id in layer:
                subtask = subtask_map.get(subtask_id)
                result = result_map.get(subtask_id)

                if result:
                    layer_results.append({
                        "subtask_id": subtask_id,
                        "subtask_content": subtask.content if subtask else "Unknown",
                        "role": subtask.role_hint if subtask else "unknown",
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                        "execution_time": result.execution_time,
                    })
                elif subtask_id in missing_subtasks:
                    layer_results.append({
                        "subtask_id": subtask_id,
                        "subtask_content": subtask.content if subtask else "Unknown",
                        "role": subtask.role_hint if subtask else "unknown",
                        "success": False,
                        "output": None,
                        "error": "MISSING: No result received for this subtask",
                        "execution_time": 0.0,
                    })

            execution_layers.append({
                "layer": layer_idx,
                "results": layer_results,
            })

        # 构建最终输出
        integrated_output: Dict[str, Any] = {
            "task_id": decomposition.original_task_id,
            "combined_output": combined_output,
            "summary": {
                "total_subtasks": len(decomposition.subtasks),
                "completed_subtasks": len([r for r in results if r.success]),
                "failed_subtasks": len([r for r in results if not r.success]),
                "missing_subtasks": len(missing_subtasks),
                "success_rate": len([r for r in results if r.success]) / max(len(results), 1) * 100,
            },
            "execution_layers": execution_layers,
            "outputs": successful_outputs,
        }

        return integrated_output
    def _integrate_code_results(
        self, successful_outputs: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        CODE 类型整合策略：按文件路径分组合并代码片段

        从每个子任务输出中提取 file_path 信息，将同一文件路径的代码片段
        合并在一起。如果输出是字典且包含 file_path 键，则使用该值；
        否则尝试从文本内容中提取文件路径标记。

        Args:
            successful_outputs: 成功的输出列表

        Returns:
            文件路径到合并代码内容的映射字典
        """
        file_groups: Dict[str, List[str]] = {}

        for output_item in successful_outputs:
            raw_output = output_item.get("output")

            if isinstance(raw_output, dict):
                # 输出是字典，查找 file_path 和 content 键
                file_path = raw_output.get("file_path", "")
                content = str(raw_output.get("content", raw_output.get("output", "")))

                if file_path:
                    file_groups.setdefault(file_path, []).append(content)
                else:
                    # 没有 file_path，归入未分类
                    file_groups.setdefault("_unclassified", []).append(content)
            elif isinstance(raw_output, str):
                # 输出是字符串，尝试从内容中提取文件路径标记
                # 支持格式: "# file: path/to/file.py" 或 "// file: path/to/file.py"
                extracted = self._extract_file_paths_from_content(raw_output)
                if extracted:
                    for fp, code in extracted.items():
                        file_groups.setdefault(fp, []).append(code)
                else:
                    file_groups.setdefault("_unclassified", []).append(raw_output)
            elif raw_output is not None:
                file_groups.setdefault("_unclassified", []).append(str(raw_output))

        # 合并同一文件路径的代码片段
        merged: Dict[str, str] = {}
        for file_path, snippets in file_groups.items():
            merged[file_path] = "\n".join(snippets)

        return merged

    def _extract_file_paths_from_content(self, content: str) -> Dict[str, str]:
        """
        从文本内容中提取文件路径标记和对应代码

        支持格式:
        - "# file: path/to/file.py"
        - "// file: path/to/file.py"

        Args:
            content: 文本内容

        Returns:
            文件路径到代码内容的映射，如果未找到标记则返回空字典
        """
        import re

        # 匹配 "# file: xxx" 或 "// file: xxx" 格式的文件路径标记
        pattern = r'(?:^|\n)\s*(?:#|//)\s*file:\s*(\S+)\s*\n'
        matches = list(re.finditer(pattern, content))

        if not matches:
            return {}

        result: Dict[str, str] = {}
        for i, match in enumerate(matches):
            file_path = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            code = content[start:end].strip()
            if code:
                result.setdefault(file_path, [])
                result[file_path].append(code)

        # Join multiple snippets for the same file
        return {fp: "\n".join(snippets) for fp, snippets in result.items()}

    def _integrate_composite_results(
        self, successful_outputs: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        COMPOSITE 类型整合策略：按子任务输出类型分组

        从每个子任务输出中提取 output_type 字段，将结果按输出类型分组。
        如果子任务输出没有 output_type 字段，默认归入 "report" 组。

        Args:
            successful_outputs: 成功的输出列表

        Returns:
            输出类型到结果列表的映射字典
        """
        type_groups: Dict[str, List[Dict[str, Any]]] = {}

        for output_item in successful_outputs:
            raw_output = output_item.get("output")

            # 尝试从输出中提取 output_type
            if isinstance(raw_output, dict):
                out_type = raw_output.get("output_type", "report")
            else:
                out_type = "report"

            type_groups.setdefault(out_type, []).append(output_item)

        return type_groups
    
    def _generate_combined_output(self, successful_outputs: List[Dict[str, Any]]) -> str:
        """
        生成综合输出 - writer 最终报告为主体，其余作为补充
        
        优化策略：
        1. 如果有 writer 角色的最终报告，以其为唯一主体输出
        2. 如果 writer 报告不足，用 analyst/researcher 内容补充
        3. searcher/fact_checker 的原始数据仅在无分析层时展示
        4. 避免重复展示多份相似报告
        
        Args:
            successful_outputs: 成功的输出列表
            
        Returns:
            综合输出文本
        """
        if not successful_outputs:
            return "任务执行未产生有效输出。"
        
        # 分层收集输出
        writer_outputs = []
        analyst_outputs = []
        data_outputs = []
        
        for output in successful_outputs:
            role = output.get("role", "unknown")
            content = str(output.get("output", "")).strip()
            if not content:
                continue
            
            item = {
                "role": role,
                "task": output.get("subtask_content", ""),
                "content": content,
                "length": len(content),
            }
            
            if role in ("writer", "summarizer"):
                writer_outputs.append(item)
            elif role in ("analyst", "researcher"):
                analyst_outputs.append(item)
            else:
                data_outputs.append(item)
        
        # 策略：writer > analyst > data，优先使用高层输出
        if writer_outputs:
            # 取最长的 writer 输出作为主报告（通常是最后的综合报告）
            main_report = max(writer_outputs, key=lambda x: x["length"])
            result = main_report["content"]
            
            # 如果主报告不够长，用 analyst 输出补充
            if len(result) < 3000 and analyst_outputs:
                supplements = []
                for item in analyst_outputs:
                    supplements.append(item["content"])
                result = result + "\n\n---\n\n" + "\n\n".join(supplements)
            
            return result
        
        elif analyst_outputs:
            # 没有 writer，用 analyst 输出
            sections = [item["content"] for item in analyst_outputs]
            result = "\n\n".join(sections)
            
            # 如果分析层不够，补充数据层
            if len(result) < 3000 and data_outputs:
                data_sections = [item["content"] for item in data_outputs]
                result = result + "\n\n---\n## 补充数据\n\n" + "\n\n".join(data_sections)
            
            return result
        
        else:
            # 只有数据层
            sections = [item["content"] for item in data_outputs]
            return "\n\n".join(sections) if sections else "任务执行完成，但未生成文本输出。"
    
    def _calculate_overall_success(
        self,
        results: List[SubTaskResult],
        missing_subtasks: List[str],
        decomposition: TaskDecomposition,
    ) -> bool:
        """
        计算整体成功状态
        
        如果所有子任务都成功且没有缺失，则整体成功。
        
        Args:
            results: 结果列表
            missing_subtasks: 缺失的子任务ID列表
            decomposition: 任务分解
            
        Returns:
            整体是否成功
        """
        # 如果有缺失的子任务，整体失败
        if missing_subtasks:
            return False
        
        # 如果没有结果，整体失败
        if not results:
            return False
        
        # 检查所有结果是否成功
        return all(r.success for r in results)
