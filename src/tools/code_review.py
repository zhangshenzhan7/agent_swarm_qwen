"""Code review tool implementation.

提供代码审查能力，包括：
- 语法检查
- 代码风格分析
- 常见问题检测（未使用变量、复杂度过高等）
- 安全漏洞扫描

基于 AST 分析和规则匹配实现，不依赖外部 lint 工具。
"""

import ast
import re
import textwrap
from typing import Dict, Any, List, Optional

from ..models.tool import ToolDefinition


class CodeReviewTool:
    """代码审查工具"""

    # 支持审查的语言
    SUPPORTED_LANGUAGES = {"python", "javascript", "shell"}

    def __init__(self, max_code_size: int = 50000):
        self._max_code_size = max_code_size

    async def review(
        self,
        code: str,
        language: str = "python",
        focus: str = "all",
    ) -> Dict[str, Any]:
        """
        审查代码

        Args:
            code: 要审查的代码
            language: 编程语言
            focus: 审查重点 (all, syntax, style, security, complexity)

        Returns:
            审查结果
        """
        if not code or not code.strip():
            return {"success": False, "error": "代码内容为空"}

        if len(code) > self._max_code_size:
            return {"success": False, "error": f"代码过长，最大 {self._max_code_size} 字符"}

        if language not in self.SUPPORTED_LANGUAGES:
            return {
                "success": False,
                "error": f"不支持的语言: {language}，支持: {list(self.SUPPORTED_LANGUAGES)}",
            }

        issues: List[Dict[str, Any]] = []

        if language == "python":
            issues = self._review_python(code, focus)
        elif language == "javascript":
            issues = self._review_javascript(code, focus)
        elif language == "shell":
            issues = self._review_shell(code, focus)

        # 按严重程度排序
        severity_order = {"error": 0, "warning": 1, "info": 2}
        issues.sort(key=lambda x: severity_order.get(x.get("severity", "info"), 3))

        summary = {
            "errors": sum(1 for i in issues if i.get("severity") == "error"),
            "warnings": sum(1 for i in issues if i.get("severity") == "warning"),
            "info": sum(1 for i in issues if i.get("severity") == "info"),
        }

        return {
            "success": True,
            "language": language,
            "total_issues": len(issues),
            "summary": summary,
            "issues": issues[:30],  # 最多返回 30 条
        }

    def _review_python(self, code: str, focus: str) -> List[Dict[str, Any]]:
        """审查 Python 代码"""
        issues: List[Dict[str, Any]] = []

        # 1. 语法检查
        if focus in ("all", "syntax"):
            issues.extend(self._check_python_syntax(code))

        # 语法错误时跳过后续 AST 分析
        has_syntax_error = any(i.get("category") == "syntax" for i in issues)

        # 2. 代码风格
        if focus in ("all", "style"):
            issues.extend(self._check_python_style(code))

        # 3. 安全检查
        if focus in ("all", "security"):
            issues.extend(self._check_python_security(code))

        # 4. 复杂度与质量（需要有效 AST）
        if focus in ("all", "complexity") and not has_syntax_error:
            issues.extend(self._check_python_complexity(code))

        return issues

    def _check_python_syntax(self, code: str) -> List[Dict[str, Any]]:
        """Python 语法检查"""
        issues = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            issues.append({
                "severity": "error",
                "category": "syntax",
                "line": e.lineno,
                "message": f"语法错误: {e.msg}",
            })
        return issues

    def _check_python_style(self, code: str) -> List[Dict[str, Any]]:
        """Python 代码风格检查"""
        issues = []
        lines = code.split("\n")

        for i, line in enumerate(lines, 1):
            # 行长度
            if len(line) > 120:
                issues.append({
                    "severity": "warning",
                    "category": "style",
                    "line": i,
                    "message": f"行长度 {len(line)} 超过 120 字符",
                })

            # 尾部空白
            if line != line.rstrip() and line.strip():
                issues.append({
                    "severity": "info",
                    "category": "style",
                    "line": i,
                    "message": "行尾有多余空白字符",
                })

            # 混用 tab 和空格缩进
            if line and line[0] in (" ", "\t"):
                indent = ""
                for ch in line:
                    if ch in (" ", "\t"):
                        indent += ch
                    else:
                        break
                if "\t" in indent and " " in indent:
                    issues.append({
                        "severity": "warning",
                        "category": "style",
                        "line": i,
                        "message": "混用 Tab 和空格缩进",
                    })

        # 函数/类命名检查（通过 AST）
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not re.match(r'^[a-z_][a-z0-9_]*$', node.name) and not node.name.startswith('__'):
                        issues.append({
                            "severity": "warning",
                            "category": "style",
                            "line": node.lineno,
                            "message": f"函数名 '{node.name}' 不符合 snake_case 规范",
                        })
                elif isinstance(node, ast.ClassDef):
                    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', node.name):
                        issues.append({
                            "severity": "warning",
                            "category": "style",
                            "line": node.lineno,
                            "message": f"类名 '{node.name}' 不符合 PascalCase 规范",
                        })
        except SyntaxError:
            pass

        return issues

    def _check_python_security(self, code: str) -> List[Dict[str, Any]]:
        """Python 安全检查"""
        issues = []
        lines = code.split("\n")

        security_patterns = [
            (r'\beval\s*\(', "使用 eval() 存在代码注入风险"),
            (r'\bexec\s*\(', "使用 exec() 存在代码注入风险"),
            (r'__import__\s*\(', "使用 __import__() 可能被利用进行动态导入攻击"),
            (r'\bpickle\.loads?\s*\(', "pickle 反序列化不可信数据存在安全风险"),
            (r'\byaml\.load\s*\((?!.*Loader)', "yaml.load() 应使用 safe_load() 或指定 Loader"),
            (r'subprocess\.\w+\(.*shell\s*=\s*True', "subprocess 使用 shell=True 存在命令注入风险"),
            (r'os\.system\s*\(', "os.system() 存在命令注入风险，建议使用 subprocess"),
            (r'password\s*=\s*["\'][^"\']+["\']', "代码中硬编码密码"),
            (r'(api_key|secret|token)\s*=\s*["\'][^"\']+["\']', "代码中硬编码敏感凭证"),
        ]

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, message in security_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        "severity": "error",
                        "category": "security",
                        "line": i,
                        "message": message,
                    })

        return issues

    def _check_python_complexity(self, code: str) -> List[Dict[str, Any]]:
        """Python 复杂度检查"""
        issues = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return issues

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 函数体行数
                if node.end_lineno and node.lineno:
                    func_lines = node.end_lineno - node.lineno + 1
                    if func_lines > 50:
                        issues.append({
                            "severity": "warning",
                            "category": "complexity",
                            "line": node.lineno,
                            "message": f"函数 '{node.name}' 过长（{func_lines} 行），建议拆分",
                        })

                # 参数数量
                args = node.args
                total_args = len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs)
                # 减去 self/cls
                if total_args > 0 and args.args and args.args[0].arg in ("self", "cls"):
                    total_args -= 1
                if total_args > 7:
                    issues.append({
                        "severity": "warning",
                        "category": "complexity",
                        "line": node.lineno,
                        "message": f"函数 '{node.name}' 参数过多（{total_args} 个），建议使用参数对象",
                    })

                # 嵌套深度
                max_depth = self._calc_nesting_depth(node)
                if max_depth > 4:
                    issues.append({
                        "severity": "warning",
                        "category": "complexity",
                        "line": node.lineno,
                        "message": f"函数 '{node.name}' 嵌套层级过深（{max_depth} 层），建议重构",
                    })

        return issues

    def _calc_nesting_depth(self, node: ast.AST, depth: int = 0) -> int:
        """计算 AST 节点的最大嵌套深度"""
        nesting_types = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)
        max_depth = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, nesting_types):
                child_depth = self._calc_nesting_depth(child, depth + 1)
            else:
                child_depth = self._calc_nesting_depth(child, depth)
            max_depth = max(max_depth, child_depth)
        return max_depth

    def _review_javascript(self, code: str, focus: str) -> List[Dict[str, Any]]:
        """审查 JavaScript 代码（基于规则匹配）"""
        issues: List[Dict[str, Any]] = []
        lines = code.split("\n")

        if focus in ("all", "style"):
            for i, line in enumerate(lines, 1):
                if len(line) > 120:
                    issues.append({
                        "severity": "warning",
                        "category": "style",
                        "line": i,
                        "message": f"行长度 {len(line)} 超过 120 字符",
                    })

        if focus in ("all", "security"):
            security_patterns = [
                (r'\beval\s*\(', "使用 eval() 存在代码注入风险"),
                (r'innerHTML\s*=', "直接设置 innerHTML 存在 XSS 风险"),
                (r'document\.write\s*\(', "document.write() 存在 XSS 风险"),
                (r'(password|secret|api_key|token)\s*[:=]\s*["\'][^"\']+["\']', "硬编码敏感凭证"),
            ]
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                for pattern, message in security_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append({
                            "severity": "error",
                            "category": "security",
                            "line": i,
                            "message": message,
                        })

        if focus in ("all", "style"):
            # var 使用检查
            for i, line in enumerate(lines, 1):
                if re.search(r'\bvar\s+', line):
                    issues.append({
                        "severity": "info",
                        "category": "style",
                        "line": i,
                        "message": "建议使用 let/const 替代 var",
                    })
                if re.search(r'==(?!=)', line) and not re.search(r'===', line):
                    issues.append({
                        "severity": "info",
                        "category": "style",
                        "line": i,
                        "message": "建议使用 === 替代 ==（严格相等）",
                    })

        return issues

    def _review_shell(self, code: str, focus: str) -> List[Dict[str, Any]]:
        """审查 Shell 代码（基于规则匹配）"""
        issues: List[Dict[str, Any]] = []
        lines = code.split("\n")

        if focus in ("all", "security"):
            security_patterns = [
                (r'\brm\s+-rf\s+/', "rm -rf 针对根路径，极其危险"),
                (r'\bchmod\s+777\b', "chmod 777 权限过于宽松"),
                (r'\bcurl\s+.*\|\s*(ba)?sh', "从网络下载并直接执行脚本存在安全风险"),
                (r'\bsudo\b', "使用 sudo 提权操作，需确认必要性"),
            ]
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pattern, message in security_patterns:
                    if re.search(pattern, line):
                        issues.append({
                            "severity": "error",
                            "category": "security",
                            "line": i,
                            "message": message,
                        })

        if focus in ("all", "style"):
            # 变量未加引号
            for i, line in enumerate(lines, 1):
                if re.search(r'\$\w+(?!\})', line) and not re.search(r'"\$', line):
                    if not line.strip().startswith("#"):
                        issues.append({
                            "severity": "info",
                            "category": "style",
                            "line": i,
                            "message": "变量引用建议使用双引号包裹，如 \"$var\"",
                        })

        return issues

    def get_tool_definition(self) -> ToolDefinition:
        """获取工具定义"""
        return ToolDefinition(
            name="code_review",
            description="审查代码质量，检查语法错误、代码风格、安全漏洞和复杂度。支持 Python、JavaScript、Shell。",
            parameters_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要审查的代码",
                    },
                    "language": {
                        "type": "string",
                        "description": "编程语言",
                        "enum": list(self.SUPPORTED_LANGUAGES),
                        "default": "python",
                    },
                    "focus": {
                        "type": "string",
                        "description": "审查重点",
                        "enum": ["all", "syntax", "style", "security", "complexity"],
                        "default": "all",
                    },
                },
                "required": ["code"],
            },
            handler=self._handle_review,
            timeout=30.0,
        )

    async def _handle_review(
        self,
        code: str,
        language: str = "python",
        focus: str = "all",
    ) -> Dict[str, Any]:
        """工具调用处理函数"""
        return await self.review(code, language, focus)


def create_code_review_tool(max_code_size: int = 50000) -> ToolDefinition:
    """
    创建代码审查工具定义

    Args:
        max_code_size: 最大代码长度

    Returns:
        工具定义
    """
    tool = CodeReviewTool(max_code_size=max_code_size)
    return tool.get_tool_definition()
