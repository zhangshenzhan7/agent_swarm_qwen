"""
测试 coder 角色在非 Qwen 原生模型下使用沙箱代码解释器的能力。

验证要点：
1. coder 使用 deepseek-v3.2 时，code_interpreter 被识别为需要沙箱回退
2. sandbox_code_interpreter 出现在 tools schema 中（而非 DashScope 内置）
3. system prompt 中不再声明"代码解释器"为内置能力，而是列为可调用工具
4. _build_request_config 中 enable_code_interpreter=False（第三方模型不支持）
5. call_tool 允许调用 sandbox_code_interpreter
6. 对比：Qwen 原生模型仍走 DashScope 内置 code_interpreter
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.models.agent import AgentRole, PREDEFINED_ROLES, ROLE_MODEL_CONFIG
from src.models.tool import ToolDefinition
from src.qwen.models import QwenConfig, QwenModel, QwenResponse
from src.sub_agent import SubAgentImpl, SANDBOX_CODE_INTERPRETER_TOOL
from src.tool_registry import ToolRegistry
from src.models.task import SubTask
from src.models.context import ExecutionContext
from src.models.enums import TaskStatus


# ── fixtures ──────────────────────────────────────────────

@pytest.fixture
def coder_role() -> AgentRole:
    """获取预定义的 coder 角色"""
    return PREDEFINED_ROLES["coder"]


@pytest.fixture
def sandbox_tool_def() -> ToolDefinition:
    """创建一个模拟的 sandbox_code_interpreter 工具定义"""
    async def mock_handler(code: str, language: str = "python"):
        return {
            "success": True,
            "stdout": f"executed: {code[:30]}",
            "stderr": "",
            "return_code": 0,
            "execution_time": 0.5,
        }

    return ToolDefinition(
        name="sandbox_code_interpreter",
        description="在云端安全沙箱中执行代码并返回结果。",
        parameters_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的代码"},
                "language": {
                    "type": "string",
                    "enum": ["python", "javascript"],
                    "default": "python",
                },
            },
            "required": ["code"],
        },
        handler=mock_handler,
        timeout=35.0,
    )


@pytest.fixture
def code_execution_tool_def() -> ToolDefinition:
    """创建一个模拟的 code_execution 工具定义"""
    async def mock_handler(code: str, language: str = "python"):
        return {"success": True, "stdout": "ok", "stderr": "", "return_code": 0, "execution_time": 0.1}

    return ToolDefinition(
        name="code_execution",
        description="本地执行代码。",
        parameters_schema={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        handler=mock_handler,
    )


@pytest.fixture
def code_review_tool_def() -> ToolDefinition:
    async def mock_handler(code: str, focus: str = "general"):
        return {"issues": []}

    return ToolDefinition(
        name="code_review",
        description="代码审查。",
        parameters_schema={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        handler=mock_handler,
    )


@pytest.fixture
def file_operations_tool_def() -> ToolDefinition:
    async def mock_handler(operation: str, path: str, content: str = ""):
        return {"success": True}

    return ToolDefinition(
        name="file_operations",
        description="文件操作。",
        parameters_schema={"type": "object", "properties": {"operation": {"type": "string"}, "path": {"type": "string"}}, "required": ["operation", "path"]},
        handler=mock_handler,
    )


@pytest.fixture
def tool_registry(sandbox_tool_def, code_execution_tool_def, code_review_tool_def, file_operations_tool_def) -> ToolRegistry:
    """创建包含所有 coder 需要的工具的注册表"""
    registry = ToolRegistry()
    registry.register_tool(sandbox_tool_def)
    registry.register_tool(code_execution_tool_def)
    registry.register_tool(code_review_tool_def)
    registry.register_tool(file_operations_tool_def)
    return registry


@pytest.fixture
def mock_qwen_client():
    """创建模拟的 Qwen 客户端"""
    client = AsyncMock()
    client.chat = AsyncMock(return_value=QwenResponse(
        content="```python\nprint('hello')\n```",
        tool_calls=None,
        finish_reason="stop",
        usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    ))
    return client


@pytest.fixture
def subtask() -> SubTask:
    return SubTask(
        id="test-subtask-001",
        parent_task_id="test-task-001",
        content="用 Python 写一个快速排序算法并测试",
        dependencies=set(),
        priority=1,
        role_hint="coder",
    )


@pytest.fixture
def execution_context() -> ExecutionContext:
    return ExecutionContext(
        task_id="test-task-001",
        start_time=0,
        status=TaskStatus.EXECUTING,
    )


def _make_coder_agent(
    coder_role: AgentRole,
    mock_qwen_client,
    tool_registry: ToolRegistry,
    model: QwenModel,
) -> SubAgentImpl:
    """创建指定模型的 coder SubAgentImpl"""
    config = QwenConfig(model=model, temperature=0.1)
    return SubAgentImpl(
        agent_id="test-coder-001",
        role=coder_role,
        qwen_client=mock_qwen_client,
        tool_registry=tool_registry,
        config=config,
    )


# ── 测试：非 Qwen 模型的沙箱回退 ──────────────────────────

class TestCoderSandboxFallback:
    """测试 coder 角色在 deepseek-v3.2 下的沙箱回退行为"""

    def test_coder_role_has_code_interpreter(self, coder_role):
        """coder 角色的 available_tools 包含 code_interpreter"""
        assert "code_interpreter" in coder_role.available_tools

    def test_coder_uses_non_qwen_model(self):
        """coder 默认使用非 Qwen 原生模型"""
        config = ROLE_MODEL_CONFIG["coder"]
        model_name = config["model"]
        # 找到对应的 QwenModel 枚举
        model_enum = None
        for m in QwenModel:
            if m.value == model_name:
                model_enum = m
                break
        assert model_enum is not None, f"模型 {model_name} 未在 QwenModel 枚举中定义"
        assert not model_enum.is_qwen_native(), f"coder 模型 {model_name} 应为非 Qwen 原生模型"

    def test_uses_sandbox_code_interpreter_true(self, coder_role, mock_qwen_client, tool_registry):
        """deepseek-v3.2 模型应该使用沙箱代码解释器"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        assert agent._uses_sandbox_code_interpreter() is True

    def test_uses_sandbox_code_interpreter_false_for_qwen(self, coder_role, mock_qwen_client, tool_registry):
        """Qwen 原生模型不需要沙箱回退"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.QWEN3_MAX)
        assert agent._uses_sandbox_code_interpreter() is False

    def test_effective_builtins_empty_for_non_qwen(self, coder_role, mock_qwen_client, tool_registry):
        """非 Qwen 模型没有 DashScope 内置工具"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        assert agent._get_effective_builtin_tools() == set()

    def test_effective_builtins_full_for_qwen(self, coder_role, mock_qwen_client, tool_registry):
        """Qwen 原生模型有完整的 DashScope 内置工具"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.QWEN3_MAX)
        builtins = agent._get_effective_builtin_tools()
        assert "code_interpreter" in builtins
        assert "web_search" in builtins

    def test_tools_schema_includes_sandbox_for_non_qwen(self, coder_role, mock_qwen_client, tool_registry):
        """非 Qwen 模型的 tools schema 应包含 sandbox_code_interpreter"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        schema = agent._build_tools_schema()
        tool_names = [t["function"]["name"] for t in schema]
        assert "sandbox_code_interpreter" in tool_names
        # code_interpreter 不应出现在 schema 中（它不是注册的工具名）
        assert "code_interpreter" not in tool_names

    def test_tools_schema_excludes_sandbox_for_qwen(self, coder_role, mock_qwen_client, tool_registry):
        """Qwen 原生模型的 tools schema 不应包含 sandbox_code_interpreter（走内置）"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.QWEN3_MAX)
        schema = agent._build_tools_schema()
        tool_names = [t["function"]["name"] for t in schema]
        assert "sandbox_code_interpreter" not in tool_names
        # code_interpreter 也不应出现（它是 DashScope 内置，不在 schema 中）
        assert "code_interpreter" not in tool_names

    def test_request_config_no_code_interpreter_for_non_qwen(self, coder_role, mock_qwen_client, tool_registry):
        """非 Qwen 模型的 request config 中 enable_code_interpreter=False"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        config = agent._build_request_config()
        assert config.enable_code_interpreter is False
        assert config.enable_search is False

    def test_request_config_has_code_interpreter_for_qwen(self, coder_role, mock_qwen_client, tool_registry):
        """Qwen 原生模型的 request config 中 enable_code_interpreter=True"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.QWEN3_MAX)
        config = agent._build_request_config()
        assert config.enable_code_interpreter is True

    def test_system_prompt_no_builtin_code_interpreter_for_non_qwen(self, coder_role, mock_qwen_client, tool_registry, subtask):
        """非 Qwen 模型的 system prompt 不应声明代码解释器为内置能力"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        prompt = agent._build_system_prompt(subtask)
        # 不应出现"内置能力"下的代码解释器
        assert "内置能力" not in prompt or "代码解释器" not in prompt.split("内置能力")[1].split("##")[0] if "内置能力" in prompt else True
        # 应该在"可调用工具"中出现 sandbox_code_interpreter
        assert "sandbox_code_interpreter" in prompt

    def test_system_prompt_has_builtin_code_interpreter_for_qwen(self, coder_role, mock_qwen_client, tool_registry, subtask):
        """Qwen 原生模型的 system prompt 应声明代码解释器为内置能力"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.QWEN3_MAX)
        prompt = agent._build_system_prompt(subtask)
        assert "代码解释器" in prompt
        # sandbox_code_interpreter 不应出现
        assert "sandbox_code_interpreter" not in prompt


class TestCoderSandboxToolCall:
    """测试 coder 通过 sandbox_code_interpreter 调用工具"""

    async def test_call_sandbox_tool_allowed(self, coder_role, mock_qwen_client, tool_registry):
        """非 Qwen 模型的 coder 可以调用 sandbox_code_interpreter"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        result = await agent.call_tool("sandbox_code_interpreter", {"code": "print(1+1)", "language": "python"})
        assert result["success"] is True
        assert "executed" in result["stdout"]

    async def test_call_sandbox_tool_blocked_for_qwen(self, coder_role, mock_qwen_client, tool_registry):
        """Qwen 原生模型的 coder 不应通过 function calling 调用 sandbox_code_interpreter"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.QWEN3_MAX)
        # sandbox_code_interpreter 不在 coder 的 available_tools 中，
        # 且 Qwen 模型不触发沙箱回退，所以应该被拒绝
        with pytest.raises(Exception, match="not available"):
            await agent.call_tool("sandbox_code_interpreter", {"code": "print(1)"})

    async def test_call_regular_tools_still_works(self, coder_role, mock_qwen_client, tool_registry):
        """非 Qwen 模型的 coder 仍然可以调用其他常规工具"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        result = await agent.call_tool("code_execution", {"code": "print('hi')"})
        assert result["success"] is True


class TestCoderEndToEnd:
    """端到端测试：coder 使用沙箱完成任务"""

    async def test_coder_executes_with_sandbox_tool_call(
        self, coder_role, mock_qwen_client, tool_registry, subtask, execution_context
    ):
        """
        模拟 coder 执行流程：
        1. 模型第一次返回 tool_call 调用 sandbox_code_interpreter
        2. 工具执行成功，结果返回给模型
        3. 模型第二次返回最终答案
        """
        # 第一次调用：模型请求调用沙箱工具
        tool_call_response = QwenResponse(
            content="",
            tool_calls=[{
                "id": "call_001",
                "function": {
                    "name": "sandbox_code_interpreter",
                    "arguments": '{"code": "def quicksort(arr):\\n    if len(arr) <= 1: return arr\\n    pivot = arr[0]\\n    return quicksort([x for x in arr[1:] if x < pivot]) + [pivot] + quicksort([x for x in arr[1:] if x >= pivot])\\nprint(quicksort([3,1,4,1,5,9,2,6]))", "language": "python"}'
                }
            }],
            finish_reason="tool_calls",
            usage={"input_tokens": 200, "output_tokens": 80, "total_tokens": 280},
        )
        # 第二次调用：模型返回最终答案
        final_response = QwenResponse(
            content="快速排序实现完成，测试通过。排序结果：[1, 1, 2, 3, 4, 5, 6, 9]",
            tool_calls=None,
            finish_reason="stop",
            usage={"input_tokens": 300, "output_tokens": 100, "total_tokens": 400},
        )
        mock_qwen_client.chat = AsyncMock(side_effect=[tool_call_response, final_response])

        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        result = await agent.execute(subtask, execution_context)

        assert result.success is True
        assert "快速排序" in result.output
        # 验证工具被调用了
        assert len(agent.tool_calls) == 1
        assert agent.tool_calls[0].tool_name == "sandbox_code_interpreter"
        assert agent.tool_calls[0].success is True

    async def test_coder_tools_schema_count(self, coder_role, mock_qwen_client, tool_registry):
        """验证非 Qwen coder 的 tools schema 数量正确"""
        agent = _make_coder_agent(coder_role, mock_qwen_client, tool_registry, QwenModel.DEEPSEEK_V3_2)
        schema = agent._build_tools_schema()
        tool_names = sorted([t["function"]["name"] for t in schema])
        # coder available_tools: ["code_interpreter", "code_execution", "code_review", "file_operations"]
        # code_interpreter → sandbox_code_interpreter (function calling)
        # code_execution, code_review, file_operations → 直接注册的工具
        assert tool_names == sorted(["sandbox_code_interpreter", "code_execution", "code_review", "file_operations"])
