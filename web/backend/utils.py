"""工具函数"""

import re
import mimetypes
from typing import Dict, List, Any


def clean_thinking_tags(text: str) -> str:
    """清理文本中的 thinking 标签，只保留正常内容"""
    if not text:
        return ""
    
    result = text
    
    # 1. 移除完整的 [THINKING]...[/THINKING] 标签对及其内容（包括嵌套）
    max_iterations = 10
    for _ in range(max_iterations):
        new_result = re.sub(r'\[THINKING\].*?\[/THINKING\]', '', result, flags=re.DOTALL | re.IGNORECASE)
        if new_result == result:
            break
        result = new_result
    
    # 2. 移除单独的 [THINKING] 标签（未闭合的）
    result = re.sub(r'\[THINKING\]', '', result, flags=re.IGNORECASE)
    
    # 3. 移除单独的 [/THINKING] 标签
    result = re.sub(r'\[/THINKING\]', '', result, flags=re.IGNORECASE)
    
    # 4. 移除 [NEW_PHASE] 标签
    result = re.sub(r'\[NEW_PHASE\]', '', result, flags=re.IGNORECASE)
    
    # 5. 清理多余的空白行
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    # 6. 清理行首行尾空白
    result = result.strip()
    
    return result


# 文件类型到角色的映射
FILE_TYPE_TO_ROLE: Dict[str, List[str]] = {
    # 图片类型
    "image/jpeg": ["image_analyst", "researcher"],
    "image/png": ["image_analyst", "researcher"],
    "image/gif": ["image_analyst"],
    "image/webp": ["image_analyst", "researcher"],
    "image/bmp": ["image_analyst"],
    # 文档类型
    "application/pdf": ["researcher", "summarizer", "analyst"],
    "application/msword": ["researcher", "summarizer", "writer"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ["researcher", "summarizer", "writer"],
    "application/vnd.ms-excel": ["analyst", "researcher"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ["analyst", "researcher"],
    "application/vnd.ms-powerpoint": ["researcher", "image_analyst", "summarizer"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ["researcher", "image_analyst", "summarizer"],
    "text/plain": ["researcher", "summarizer", "translator"],
    "text/markdown": ["researcher", "summarizer", "writer"],
    "text/csv": ["analyst", "researcher"],
    # 代码类型
    "text/javascript": ["coder", "analyst"],
    "text/python": ["coder", "analyst"],
    "application/json": ["coder", "analyst"],
    "text/html": ["coder", "analyst"],
    "text/css": ["coder"],
    # 视频类型
    "video/mp4": ["image_analyst", "researcher"],
    "video/webm": ["image_analyst", "researcher"],
    "video/quicktime": ["image_analyst", "researcher"],
    # 音频类型
    "audio/mpeg": ["researcher"],
    "audio/wav": ["researcher"],
}


def detect_file_type(filename: str, mime_type: str = None) -> str:
    """检测文件类型"""
    if mime_type:
        return mime_type
    guessed_type, _ = mimetypes.guess_type(filename)
    return guessed_type or "application/octet-stream"


def get_recommended_roles_for_files(files: List[Dict[str, Any]]) -> List[str]:
    """根据文件类型推荐合适的角色"""
    recommended = set()
    for file_info in files:
        file_type = file_info.get("type", "")
        filename = file_info.get("name", "")
        
        if not file_type:
            file_type = detect_file_type(filename)
        
        roles = FILE_TYPE_TO_ROLE.get(file_type, [])
        if not roles:
            ext = filename.lower().split(".")[-1] if "." in filename else ""
            if ext in ["jpg", "jpeg", "png", "gif", "webp", "bmp"]:
                roles = ["image_analyst", "researcher"]
            elif ext in ["pdf"]:
                roles = ["researcher", "summarizer"]
            elif ext in ["doc", "docx"]:
                roles = ["researcher", "summarizer"]
            elif ext in ["xls", "xlsx", "csv"]:
                roles = ["analyst", "researcher"]
            elif ext in ["py", "js", "ts", "java", "go", "rs"]:
                roles = ["coder", "analyst"]
            elif ext in ["mp4", "webm", "mov", "avi"]:
                roles = ["image_analyst", "researcher"]
            else:
                roles = ["researcher", "analyst"]
        
        recommended.update(roles)
    
    return list(recommended)
