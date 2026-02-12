"""
阿里云函数计算 Code Interpreter 后端实现

基于阿里云 AgentRun Sandbox Code Interpreter 服务实现安全的代码执行。
支持 Python、JavaScript 等语言的云端沙箱执行。

参考文档：
https://help.aliyun.com/zh/functioncompute/fc/sandbox-sandbox-code-interepreter

功能特性：
- 云端代码执行（Python、JavaScript）
- 完整的文件系统操作（上传、下载、管理文件）
- 自动资源管理（创建、停止、删除沙箱实例）
- 内置安全隔离和超时控制
"""

import asyncio
import hashlib
import hmac
import logging
import os
import time
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from urllib.parse import urlparse
import aiohttp

from ..code_execution import ExecutionResult, Language

logger = logging.getLogger(__name__)


class AliyunFCCodeInterpreterBackend:
    """
    阿里云函数计算 Code Interpreter 后端
    
    使用阿里云 AgentRun Sandbox 提供的云端代码执行服务。
    相比本地执行，提供更强的安全隔离和资源控制能力。
    
    主要优势：
    - Serverless 架构，按需计费
    - 完全隔离的沙箱环境
    - 支持文件系统操作
    - 自动伸缩和资源管理
    
    Attributes:
        account_id: 阿里云主账号 ID
        region_id: 地域 ID（如 cn-hangzhou）
        template_name: 沙箱模板名称
        sandbox_id: 当前沙箱实例 ID
        timeout: 默认执行超时时间
    """
    
    def __init__(
        self,
        account_id: str,
        region_id: str = "cn-hangzhou",
        template_name: str = "python-sandbox",
        timeout: float = 30.0,
        sandbox_idle_timeout: int = 3600,
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None,
    ):
        """
        初始化阿里云 FC Code Interpreter 后端
        
        Args:
            account_id: 阿里云主账号 ID
            region_id: 地域 ID，默认 cn-hangzhou
            template_name: 沙箱模板名称，默认 python-sandbox
            timeout: 代码执行超时时间（秒），默认 30
            sandbox_idle_timeout: 沙箱闲置超时时间（秒），默认 3600（1小时）
            access_key_id: 阿里云 AccessKey ID（控制面 API 需要，用于自动创建模板）
            access_key_secret: 阿里云 AccessKey Secret
        """
        self.account_id = account_id
        self.region_id = region_id
        self.template_name = template_name
        self.timeout = timeout
        self.sandbox_idle_timeout = sandbox_idle_timeout
        self.access_key_id = access_key_id or os.environ.get("ALIYUN_ACCESS_KEY_ID", "")
        self.access_key_secret = access_key_secret or os.environ.get("ALIYUN_ACCESS_KEY_SECRET", "")
        
        # 数据面 API Base URL
        self.base_url = f"https://{account_id}.agentrun-data.{region_id}.aliyuncs.com"
        
        # 控制面 API Base URL
        self.control_url = f"https://agentrun.{region_id}.aliyuncs.com"
        
        # 当前沙箱和上下文信息
        self.sandbox_id: Optional[str] = None
        self.context_id: Optional[str] = None
        
        # 模板是否已确认存在
        self._template_verified = False
        
        # HTTP 会话
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info(
            f"AliyunFCCodeInterpreterBackend initialized: "
            f"account_id={account_id}, region={region_id}, template={template_name}, "
            f"ak={'***' if self.access_key_id else '(未配置)'}"
        )
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "X-Acs-Parent-Id": self.account_id,
                    "Content-Type": "application/json",
                }
            )
        return self._session
    
    def _sign_v3(self, method: str, url: str, headers: Dict[str, str], body: str) -> str:
        """阿里云 V3 签名（控制面 API 需要）"""
        signed_headers = sorted([
            k.lower() for k in headers.keys()
            if k.lower().startswith("x-acs-") or k.lower() in ("host", "content-type")
        ])
        signed_headers_str = ";".join(signed_headers)

        canonical_headers = ""
        for h in signed_headers:
            val = headers[[k for k in headers if k.lower() == h][0]]
            canonical_headers += f"{h}:{val}\n"

        body_bytes = body.encode("utf-8") if body else b""
        hashed_payload = hashlib.sha256(body_bytes).hexdigest()

        parsed = urlparse(url)
        canonical_uri = parsed.path or "/"
        canonical_querystring = parsed.query or ""

        canonical_request = (
            f"{method}\n{canonical_uri}\n{canonical_querystring}\n"
            f"{canonical_headers}\n{signed_headers_str}\n{hashed_payload}"
        )

        hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"ACS3-HMAC-SHA256\n{hashed_request}"

        signature = hmac.new(
            self.access_key_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return (
            f"ACS3-HMAC-SHA256 Credential={self.access_key_id},"
            f"SignedHeaders={signed_headers_str},Signature={signature}"
        )

    async def _ensure_template(self) -> None:
        """确保沙箱模板存在，不存在则通过控制面 API 自动创建
        
        需要 AK/SK 配置。如果未配置 AK/SK，跳过自动创建（依赖用户手动在控制台创建）。
        """
        if self._template_verified:
            return
        
        if not self.access_key_id or not self.access_key_secret:
            logger.debug("AK/SK 未配置，跳过模板自动创建检查")
            return
        
        url = f"{self.control_url}/2025-09-10/templates"
        body = json.dumps({
            "templateName": self.template_name,
            "templateType": "CodeInterpreter",
            "description": "Auto-created by qwen-agent-swarm",
            "cpu": 2,
            "memory": 4096,
        })

        nonce = uuid.uuid4().hex
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        host = f"agentrun.{self.region_id}.aliyuncs.com"

        headers = {
            "Host": host,
            "Content-Type": "application/json",
            "x-acs-action": "CreateTemplate",
            "x-acs-version": "2025-09-10",
            "x-acs-date": timestamp,
            "x-acs-signature-nonce": nonce,
            "x-acs-parent-id": self.account_id,
        }
        headers["Authorization"] = self._sign_v3("POST", url, headers, body)

        session = await self._get_session()
        try:
            async with session.post(url, data=body, headers=headers) as response:
                resp_text = await response.text()
                if response.status in (200, 201):
                    logger.info(f"模板 '{self.template_name}' 创建成功")
                    self._template_verified = True
                elif response.status == 409 or "already" in resp_text.lower():
                    # 模板已存在
                    logger.info(f"模板 '{self.template_name}' 已存在")
                    self._template_verified = True
                else:
                    logger.warning(
                        f"模板创建返回 {response.status}: {resp_text[:300]}"
                    )
        except Exception as e:
            logger.warning(f"模板自动创建失败（非致命）: {e}")
    
    async def _ensure_sandbox(self) -> str:
        """
        确保沙箱实例存在
        
        如果沙箱不存在，自动创建一个新的沙箱实例。
        如果模板不存在，先通过控制面 API 自动创建模板（需要 AK/SK）。
        
        Returns:
            沙箱实例 ID
        """
        if self.sandbox_id:
            # 检查沙箱是否仍然有效
            try:
                await self._check_sandbox_health()
                return self.sandbox_id
            except Exception as e:
                logger.warning(f"Existing sandbox is invalid: {e}, creating new one")
                self.sandbox_id = None
                self.context_id = None
        
        # 创建新的沙箱实例
        session = await self._get_session()
        url = f"{self.base_url}/sandboxes"
        
        payload = {
            "templateName": self.template_name,
        }
        
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 404:
                    error_text = await response.text()
                    if "template not found" in error_text.lower():
                        # 模板不存在，尝试自动创建
                        logger.info(f"模板 '{self.template_name}' 不存在，尝试自动创建...")
                        await self._ensure_template()
                        if not self._template_verified:
                            raise RuntimeError(
                                f"模板 '{self.template_name}' 不存在且自动创建失败。"
                                f"请在 AgentRun 控制台手动创建，或配置 AK/SK 以启用自动创建。"
                            )
                        # 等待模板就绪
                        await asyncio.sleep(2)
                        # 重试创建沙箱
                        async with session.post(url, json=payload) as retry_resp:
                            if retry_resp.status not in (200, 201):
                                retry_text = await retry_resp.text()
                                raise RuntimeError(
                                    f"模板创建后沙箱创建仍失败: {retry_resp.status}, {retry_text}"
                                )
                            data = await retry_resp.json()
                            if "data" in data and isinstance(data["data"], dict):
                                self.sandbox_id = data["data"]["sandboxId"]
                            else:
                                self.sandbox_id = data["sandboxId"]
                            logger.info(f"Created sandbox: {self.sandbox_id}")
                            return self.sandbox_id
                    else:
                        raise RuntimeError(
                            f"Failed to create sandbox: {response.status}, {error_text}"
                        )
                
                if response.status not in (200, 201):
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Failed to create sandbox: {response.status}, {error_text}"
                    )
                
                data = await response.json()
                # API 返回格式: {"code": "SUCCESS", "data": {"sandboxId": "..."}}
                # 或直接: {"sandboxId": "..."}
                if "data" in data and isinstance(data["data"], dict):
                    self.sandbox_id = data["data"]["sandboxId"]
                else:
                    self.sandbox_id = data["sandboxId"]
                
                self._template_verified = True  # 沙箱创建成功说明模板存在
                logger.info(f"Created sandbox: {self.sandbox_id}")
                return self.sandbox_id
                
        except Exception as e:
            logger.error(f"Error creating sandbox: {e}")
            raise
    
    async def _check_sandbox_health(self) -> bool:
        """
        检查沙箱健康状态
        
        Returns:
            True 如果沙箱健康
        """
        if not self.sandbox_id:
            return False
        
        session = await self._get_session()
        url = f"{self.base_url}/sandboxes/{self.sandbox_id}/health"
        
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "ok"
                return False
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    async def _ensure_context(self, language: str) -> str:
        """
        确保执行上下文存在
        
        Args:
            language: 编程语言（python 或 javascript）
            
        Returns:
            上下文 ID
        """
        # 确保沙箱存在
        await self._ensure_sandbox()
        
        # 如果已有上下文，直接返回
        if self.context_id:
            return self.context_id
        
        # 创建新的执行上下文
        session = await self._get_session()
        url = f"{self.base_url}/sandboxes/{self.sandbox_id}/contexts"
        
        payload = {
            "language": language,
        }
        
        try:
            async with session.post(url, json=payload) as response:
                if response.status not in (200, 201):
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Failed to create context: {response.status}, {error_text}"
                    )
                
                data = await response.json()
                self.context_id = data["id"]
                
                logger.info(f"Created context: {self.context_id} for {language}")
                return self.context_id
                
        except Exception as e:
            logger.error(f"Error creating context: {e}")
            raise
    
    async def execute(
        self,
        code: str,
        language: str,
        timeout: float
    ) -> ExecutionResult:
        """
        执行代码
        
        在阿里云 FC 沙箱中执行代码。
        
        Args:
            code: 要执行的代码字符串
            language: 编程语言（python 或 javascript）
            timeout: 执行超时时间（秒）
            
        Returns:
            ExecutionResult: 包含执行结果的数据类实例
        """
        start_time = time.time()
        
        # 验证语言
        language_lower = language.lower()
        if language_lower not in ["python", "javascript"]:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Unsupported language: {language}. "
                       f"Supported: python, javascript",
                return_code=-1,
                execution_time=0.0,
                error_type="EXEC_UNSUPPORTED_LANGUAGE"
            )
        
        # 验证代码不为空
        if not code or not code.strip():
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Code cannot be empty",
                return_code=-1,
                execution_time=0.0,
                error_type="EXEC_SYNTAX_ERROR"
            )
        
        try:
            # 确保上下文存在
            context_id = await self._ensure_context(language_lower)
            
            # 执行代码
            session = await self._get_session()
            url = f"{self.base_url}/sandboxes/{self.sandbox_id}/contexts/execute"
            
            payload = {
                "contextId": context_id,
                "code": code,
            }
            
            # 使用 asyncio.wait_for 实现超时控制
            async with asyncio.timeout(timeout):
                async with session.post(url, json=payload) as response:
                    execution_time = time.time() - start_time
                    
                    if response.status not in (200, 201):
                        error_text = await response.text()
                        return ExecutionResult(
                            success=False,
                            stdout="",
                            stderr=f"Execution failed: {error_text}",
                            return_code=-1,
                            execution_time=execution_time,
                            error_type="EXEC_RUNTIME_ERROR"
                        )
                    
                    data = await response.json()
                    
                    # 解析执行结果
                    # AgentRun Sandbox 返回格式：
                    # { "results": [{"type": "stdout", "text": "..."}, 
                    #               {"type": "result", "text": "..."},
                    #               {"type": "endOfExecution", "status": "ok|error"}],
                    #   "contextId": "..." }
                    
                    results = data.get("results", [])
                    stdout_parts = []
                    stderr_parts = []
                    exec_status = "ok"
                    
                    for item in results:
                        item_type = item.get("type", "")
                        item_text = item.get("text", "")
                        if item_type == "stdout":
                            stdout_parts.append(item_text)
                        elif item_type == "stderr":
                            stderr_parts.append(item_text)
                        elif item_type == "error":
                            stderr_parts.append(item_text)
                        elif item_type == "result":
                            # 表达式求值结果 — 支持两种格式:
                            # 格式1: {"type": "result", "text": "..."}
                            # 格式2: {"type": "result", "data": {"text/plain": "..."}}
                            result_text = item_text
                            if not result_text and "data" in item:
                                result_data = item["data"]
                                if isinstance(result_data, dict):
                                    result_text = result_data.get("text/plain", "")
                            if result_text and result_text != "None" and result_text != "Code executed successfully":
                                stdout_parts.append(result_text)
                        elif item_type == "endOfExecution":
                            exec_status = item.get("status", "ok")
                    
                    stdout = "\n".join(stdout_parts)
                    stderr = "\n".join(stderr_parts)
                    # 如果没有 endOfExecution，根据是否有 stderr 判断
                    success = (exec_status == "ok") and not stderr
                    
                    # 兼容旧格式（非 results 数组）
                    if not results:
                        stdout = str(data.get("output", data.get("result", "")))
                        stderr = str(data.get("error", ""))
                        success = data.get("success", True) and not stderr
                    
                    return ExecutionResult(
                        success=success,
                        stdout=stdout,
                        stderr=stderr,
                        return_code=0 if success else -1,
                        execution_time=execution_time,
                    )
        
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            logger.warning(f"Code execution timed out after {timeout}s")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution timed out after {timeout} seconds",
                return_code=-1,
                execution_time=execution_time,
                error_type="EXEC_TIMEOUT"
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error executing code: {e}")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution error: {type(e).__name__}: {e}",
                return_code=-1,
                execution_time=execution_time,
                error_type="EXEC_RUNTIME_ERROR"
            )
    
    async def read_file(self, path: str) -> Dict[str, Any]:
        """
        读取沙箱中的文件
        
        Args:
            path: 文件路径
            
        Returns:
            文件内容和元信息
        """
        await self._ensure_sandbox()
        
        session = await self._get_session()
        url = f"{self.base_url}/sandboxes/{self.sandbox_id}/files"
        
        try:
            async with session.get(url, params={"path": path}) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Failed to read file: {error_text}",
                    }
                
                data = await response.json()
                return {
                    "success": True,
                    "content": data.get("content", ""),
                    "size": data.get("size", 0),
                    "path": data.get("path", path),
                    "encoding": data.get("encoding", "utf-8"),
                }
        
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    async def write_file(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        写入文件到沙箱
        
        Args:
            path: 文件路径
            content: 文件内容
            encoding: 编码方式，默认 utf-8
            
        Returns:
            操作结果
        """
        await self._ensure_sandbox()
        
        session = await self._get_session()
        url = f"{self.base_url}/sandboxes/{self.sandbox_id}/files"
        
        payload = {
            "path": path,
            "content": content,
            "encoding": encoding,
        }
        
        try:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Failed to write file: {error_text}",
                    }
                
                data = await response.json()
                return {
                    "success": True,
                    "path": data.get("path", path),
                    "size": data.get("size", len(content)),
                }
        
        except Exception as e:
            logger.error(f"Error writing file: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    async def list_directory(self, path: str = "/home/user") -> Dict[str, Any]:
        """
        列出目录内容
        
        Args:
            path: 目录路径，默认 /home/user
            
        Returns:
            目录内容列表
        """
        await self._ensure_sandbox()
        
        session = await self._get_session()
        url = f"{self.base_url}/sandboxes/{self.sandbox_id}/filesystem"
        
        try:
            async with session.get(url, params={"path": path}) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Failed to list directory: {error_text}",
                    }
                
                data = await response.json()
                return {
                    "success": True,
                    "path": data.get("path", path),
                    "entries": data.get("entries", []),
                    "total": len(data.get("entries", [])),
                }
        
        except Exception as e:
            logger.error(f"Error listing directory: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    async def stop_sandbox(self) -> bool:
        """
        停止沙箱实例
        
        Returns:
            True 如果成功停止
        """
        if not self.sandbox_id:
            return True
        
        sandbox_id = self.sandbox_id
        session = await self._get_session()
        url = f"{self.base_url}/sandboxes/{sandbox_id}/stop"
        
        try:
            async with session.post(url) as response:
                success = response.status in (200, 204)
                if success:
                    logger.info(f"Stopped sandbox: {sandbox_id}")
                else:
                    body = await response.text()
                    logger.warning(f"Stop sandbox {sandbox_id} returned {response.status}: {body}")
                # 无论成功与否都清除引用，避免重复尝试停止已失效的沙箱
                self.sandbox_id = None
                self.context_id = None
                return success
        
        except Exception as e:
            logger.error(f"Error stopping sandbox {sandbox_id}: {e}")
            # 清除引用，下次使用时会创建新沙箱
            self.sandbox_id = None
            self.context_id = None
            return False
    
    async def delete_sandbox(self) -> bool:
        """
        删除沙箱实例
        
        Returns:
            True 如果成功删除
        """
        if not self.sandbox_id:
            return True
        
        session = await self._get_session()
        url = f"{self.base_url}/sandboxes/{self.sandbox_id}"
        
        try:
            async with session.delete(url) as response:
                success = response.status == 200
                if success:
                    logger.info(f"Deleted sandbox: {self.sandbox_id}")
                    self.sandbox_id = None
                    self.context_id = None
                return success
        
        except Exception as e:
            logger.error(f"Error deleting sandbox: {e}")
            return False
    
    async def close(self):
        """关闭后端，清理资源"""
        # 停止沙箱（忽略失败，沙箱会通过 idle timeout 自动回收）
        try:
            await self.stop_sandbox()
        except Exception as e:
            logger.warning(f"close() 中停止沙箱失败: {e}")
        
        # 关闭 HTTP 会话
        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"close() 中关闭 HTTP 会话失败: {e}")
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()


__all__ = [
    "AliyunFCCodeInterpreterBackend",
]
