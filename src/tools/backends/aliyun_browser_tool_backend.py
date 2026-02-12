"""
网页搜索与内容抓取后端实现

提供两大核心能力：
1. 关键词搜索：通过搜索引擎（Bing/百度）搜索关键词，返回结构化搜索结果
2. 网页抓取：直接请求指定 URL 并提取页面文本内容

使用 aiohttp 直接 HTTP 请求，轻量高效，不依赖云端浏览器沙箱。
"""

import asyncio
import logging
import re
import urllib.parse
from typing import Dict, Any, Optional, List
from html.parser import HTMLParser

import aiohttp

logger = logging.getLogger(__name__)


def _strip_unwanted_tags(html: str) -> str:
    """用正则预先移除 script/style/noscript/svg/head 标签及其内容。

    这比 HTMLParser 状态跟踪更可靠，能处理百度等复杂/畸形 HTML。
    """
    for tag in ("script", "style", "noscript", "svg", "head"):
        html = re.sub(
            rf"<{tag}[\s>].*?</{tag}\s*>",
            "",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    # 移除 HTML 注释
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    return html


class _TextExtractor(HTMLParser):
    """从已清理的 HTML 中提取纯文本"""

    def __init__(self):
        super().__init__()
        self._text_parts: list[str] = []
        # 内联不可见标签（双重保险）
        self._skip_tags = {"script", "style", "noscript", "svg", "head"}
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._text_parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._text_parts)


def _extract_text_from_html(html: str) -> str:
    """从 HTML 提取纯文本：先正则剥离不可见标签，再用 HTMLParser 提取文本"""
    cleaned = _strip_unwanted_tags(html)
    parser = _TextExtractor()
    try:
        parser.feed(cleaned)
    except Exception:
        pass
    return parser.get_text()


def _extract_title_from_html(html: str) -> str:
    """从 HTML 提取 title"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


class AliyunBrowserToolBackend:
    """
    网页内容抓取后端

    使用 aiohttp 直接请求网页并提取内容。
    轻量高效，不依赖云端浏览器沙箱。

    Attributes:
        account_id: 阿里云主账号 ID（保留，用于未来沙箱模式）
        region_id: 地域 ID
    """

    # 模拟浏览器的 User-Agent
    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        account_id: str = "",
        region_id: str = "cn-hangzhou",
        sandbox_idle_timeout: int = 3600,
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None,
    ):
        self.account_id = account_id
        self.region_id = region_id
        self._session: Optional[aiohttp.ClientSession] = None

        # 保留沙箱相关属性以兼容上层接口
        self.sandbox_id: Optional[str] = None

        logger.info(
            f"AliyunBrowserToolBackend initialized (HTTP mode): "
            f"account_id={account_id or '(未配置)'}"
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话，带完整浏览器请求头以规避反爬"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": self._USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                    "Cache-Control": "max-age=0",
                    "Connection": "keep-alive",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def navigate_and_extract(
        self,
        url: str,
        extract_content: bool = True,
        screenshot: bool = False,
        wait_seconds: float = 0,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        请求指定 URL 并提取页面内容，带自动重试

        Args:
            url: 目标 URL
            extract_content: 是否提取页面文本内容
            screenshot: 是否截图（HTTP 模式不支持，忽略）
            wait_seconds: 忽略（HTTP 模式无需等待 JS 渲染）
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数（连接错误/超时时重试）

        Returns:
            包含页面内容、标题等信息的字典
        """
        last_result: Dict[str, Any] = {}

        for attempt in range(1 + max_retries):
            result: Dict[str, Any] = {
                "success": False,
                "url": url,
                "title": "",
                "content": "",
                "screenshot_base64": "",
                "error": "",
            }

            try:
                async with asyncio.timeout(timeout):
                    session = await self._get_session()

                    async with session.get(
                        url,
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=timeout - 1),
                    ) as response:
                        result["url"] = str(response.url)

                        if response.status != 200:
                            result["error"] = f"HTTP {response.status}"
                            if response.status < 500:
                                try:
                                    html = await response.text(errors="replace")
                                    result["title"] = _extract_title_from_html(html)
                                    if extract_content:
                                        result["content"] = _extract_text_from_html(html)
                                except Exception:
                                    pass
                            # 4xx 不重试，5xx 重试
                            if response.status < 500:
                                return result
                            last_result = result
                            if attempt < max_retries:
                                await asyncio.sleep(1.0 * (attempt + 1))
                                continue
                            return result

                        content_type = response.headers.get("Content-Type", "")

                        if "text/html" in content_type or "application/xhtml" in content_type:
                            html = await response.text(errors="replace")
                            result["title"] = _extract_title_from_html(html)
                            if extract_content:
                                text = _extract_text_from_html(html)
                                max_chars = 15000
                                if len(text) > max_chars:
                                    text = (
                                        text[:max_chars]
                                        + f"\n\n[内容已截断，共 {len(text)} 字符，显示前 {max_chars} 字符]"
                                    )
                                result["content"] = text
                        elif "application/json" in content_type:
                            text = await response.text(errors="replace")
                            result["title"] = "JSON Response"
                            if extract_content:
                                max_chars = 15000
                                if len(text) > max_chars:
                                    text = text[:max_chars] + "\n\n[JSON 已截断]"
                                result["content"] = text
                        elif "text/" in content_type:
                            text = await response.text(errors="replace")
                            result["title"] = "Text Response"
                            if extract_content:
                                max_chars = 15000
                                if len(text) > max_chars:
                                    text = text[:max_chars] + "\n\n[内容已截断]"
                                result["content"] = text
                        else:
                            result["title"] = f"Binary: {content_type}"
                            result["content"] = f"[非文本内容: {content_type}]"

                        result["success"] = True
                        return result

            except (asyncio.TimeoutError, TimeoutError):
                result["error"] = f"请求超时（{timeout}s）"
                last_result = result
                if attempt < max_retries:
                    logger.info(f"请求超时，重试 {attempt + 1}/{max_retries}: {url}")
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
            except aiohttp.ClientError as e:
                result["error"] = f"网络错误: {type(e).__name__}: {e}"
                last_result = result
                if attempt < max_retries:
                    logger.info(f"网络错误，重试 {attempt + 1}/{max_retries}: {url}")
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"
                logger.error(f"Browser operation failed: {e}")
                return result  # 未知错误不重试

        return last_result or result

    async def search(
        self,
        query: str,
        num_results: int = 8,
        timeout: float = 20.0,
    ) -> Dict[str, Any]:
        """
        通过搜索引擎搜索关键词，返回结构化结果

        优先使用夸克（中国大陆可用、结果质量高），Bing 作为备选。

        Args:
            query: 搜索关键词
            num_results: 期望返回的结果数量
            timeout: 请求超时时间（秒）

        Returns:
            {"success": bool, "query": str, "results": [...], "error": str}
        """
        result: Dict[str, Any] = {
            "success": False,
            "query": query,
            "results": [],
            "error": "",
        }

        engines = [
            ("quark", self._search_quark),
            ("bing", self._search_bing),
        ]

        for engine_name, engine_fn in engines:
            try:
                engine_timeout = min(timeout, 10.0)
                items = await engine_fn(query, num_results, engine_timeout)
                if items:
                    result["success"] = True
                    result["results"] = items
                    logger.info(f"搜索成功 ({engine_name}): '{query}' → {len(items)} 条结果")
                    return result
            except Exception as e:
                logger.warning(f"搜索引擎 {engine_name} 失败: {e}")
                continue

        result["error"] = "所有搜索引擎均失败"
        return result

    async def _search_quark(
        self, query: str, num_results: int, timeout: float
    ) -> List[Dict[str, str]]:
        """通过夸克搜索（中国大陆首选，结果质量高）

        夸克 CDN 节点较多，部分节点可能不通，因此内置重试。
        """
        encoded_q = urllib.parse.quote_plus(query)
        url = f"https://quark.sm.cn/s?q={encoded_q}&from=smor&safe=1"

        session = await self._get_session()
        last_err = None
        for attempt in range(3):
            try:
                async with asyncio.timeout(timeout):
                    async with session.get(
                        url,
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=timeout - 1),
                    ) as response:
                        if response.status != 200:
                            return []
                        html = await response.text(errors="replace")
                return self._parse_quark_results(html, num_results)
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                last_err = e
                if attempt < 2:
                    # 关闭旧 session 强制重新建连（可能换 CDN 节点）
                    await self.close()
                    self._session = None
                    session = await self._get_session()
                    await asyncio.sleep(0.5)
        raise last_err or RuntimeError("quark search failed")

    async def _search_bing(
        self, query: str, num_results: int, timeout: float
    ) -> List[Dict[str, str]]:
        """通过 Bing 搜索（备选）"""
        encoded_q = urllib.parse.quote_plus(query)
        url = f"https://www.bing.com/search?q={encoded_q}&count={num_results}&ensearch=1"

        session = await self._get_session()
        async with asyncio.timeout(timeout):
            async with session.get(
                url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=timeout - 1),
            ) as response:
                if response.status != 200:
                    return []
                html = await response.text(errors="replace")

        return self._parse_bing_results(html, num_results)

    @staticmethod
    def _parse_quark_results(html: str, max_results: int) -> List[Dict[str, str]]:
        """解析夸克搜索结果页 HTML

        夸克搜索结果通过两种方式嵌入数据：
        1. data-reco JSON 属性：包含 article_title, norm_url, host_name
        2. href 直接链接：外部网站的真实 URL
        """
        import html as html_module
        import json as json_module

        results: List[Dict[str, str]] = []
        seen_urls: set = set()

        def _decode_url(u: str) -> str:
            """解码 URL（处理双重编码的情况）"""
            decoded = urllib.parse.unquote(u)
            # 如果解码后仍含 %，再解一次
            if "%" in decoded:
                decoded = urllib.parse.unquote(decoded)
            return decoded

        def _decode_title(t: str) -> str:
            """解码标题（处理 URL 编码的中文标题）"""
            if "%" in t:
                try:
                    return urllib.parse.unquote(t)
                except Exception:
                    pass
            return t

        # 方法 1: 从 data-reco JSON 属性提取（最可靠，含标题和来源）
        reco_blocks = re.findall(r'data-reco="([^"]+)"', html)
        for reco_raw in reco_blocks:
            try:
                reco_str = html_module.unescape(reco_raw)
                reco = json_module.loads(reco_str)
                title = _decode_title(reco.get("article_title", "").strip())
                url = _decode_url(reco.get("norm_url", "").strip())
                source = reco.get("host_name", "").strip()
                if "%" in source:
                    source = urllib.parse.unquote(source)
                # 过滤无效结果
                if not url or not title or title == "undefined":
                    continue
                if not url.startswith("http"):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": f"来源: {source}" if source else "",
                })
            except (json_module.JSONDecodeError, TypeError):
                continue

        # 方法 2: 从外部 <a href> 提取（兜底，补充方法 1 遗漏的结果）
        link_pattern = re.compile(
            r'<a[^>]*href="(https?://(?!.*(?:quark|sm\.cn|ucweb|uc\.cn|page\.sm))[^"]+)"[^>]*>',
            re.IGNORECASE,
        )
        for m in link_pattern.finditer(html):
            url = _decode_url(m.group(1))
            if url in seen_urls or url.endswith((".js", ".css", ".png", ".jpg", ".gif")):
                continue
            seen_urls.add(url)
            pos = m.end()
            nearby = html[pos : pos + 500]
            title_m = re.search(r">([^<]{5,80})<", nearby)
            title = title_m.group(1).strip() if title_m else ""
            title = re.sub(r"</?em>", "", _decode_title(title))
            if title and title != "undefined":
                results.append({"title": title, "url": url, "snippet": ""})

        return results[:max_results]

    @staticmethod
    def _parse_bing_results(html: str, max_results: int) -> List[Dict[str, str]]:
        """解析 Bing 搜索结果页 HTML

        支持两种模式：
        - cn.bing.com 标准结果（b_algo 块）
        - ensearch=1 国际结果（b_algo 块或 cite 标签中的真实 URL）
        """
        results = []

        # 标准 b_algo 块解析
        blocks = re.findall(
            r'<li\s+class="b_algo"[^>]*>(.*?)</li>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        for block in blocks[:max_results]:
            link_match = re.search(
                r'<h2[^>]*>\s*<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if not link_match:
                continue
            raw_url = link_match.group(1).strip()
            title = re.sub(r"<[^>]+>", "", link_match.group(2)).strip()

            # 尝试从 cite 标签提取真实 URL（Bing 跳转链接的情况）
            url = raw_url
            if "bing.com/ck/" in raw_url:
                cite_match = re.search(r"<cite[^>]*>(.*?)</cite>", block, re.DOTALL)
                if cite_match:
                    cite_text = re.sub(r"<[^>]+>", "", cite_match.group(1)).strip()
                    # cite 中通常是 "domain.com › path" 格式
                    cite_text = cite_text.replace(" › ", "/").replace("›", "/")
                    if not cite_text.startswith("http"):
                        cite_text = "https://" + cite_text
                    url = cite_text

            snippet = ""
            snippet_match = re.search(
                r'<p[^>]*>(.*?)</p>',
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if snippet_match:
                snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()

            if url and title:
                results.append({"title": title, "url": url, "snippet": snippet})

        return results

    async def stop_sandbox(self) -> bool:
        """停止沙箱（HTTP 模式无沙箱，直接返回）"""
        self.sandbox_id = None
        return True

    async def close(self):
        """关闭后端，清理 HTTP 会话"""
        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"关闭 HTTP 会话失败: {e}")
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


__all__ = ["AliyunBrowserToolBackend"]
