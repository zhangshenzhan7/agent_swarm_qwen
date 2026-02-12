"""文件解析服务 - 提取PDF/文档内容"""

import os
import fitz  # PyMuPDF
from typing import Optional, Dict, Any


def extract_pdf_text(file_path: str, max_pages: int = 50, max_chars: int = 100000) -> Dict[str, Any]:
    """
    提取PDF文本内容
    
    Args:
        file_path: PDF文件路径
        max_pages: 最大提取页数
        max_chars: 最大字符数
        
    Returns:
        包含文本内容和元数据的字典
    """
    try:
        doc = fitz.open(file_path)
        
        metadata = {
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "subject": doc.metadata.get("subject", ""),
            "total_pages": len(doc),
            "extracted_pages": 0,
        }
        
        text_parts = []
        total_chars = 0
        
        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            page_text = page.get_text()
            
            if total_chars + len(page_text) > max_chars:
                # 截断到最大字符数
                remaining = max_chars - total_chars
                if remaining > 0:
                    text_parts.append(f"\n--- 第{page_num+1}页 ---\n{page_text[:remaining]}")
                    text_parts.append("\n\n[文档内容过长，已截断...]")
                break
            
            text_parts.append(f"\n--- 第{page_num+1}页 ---\n{page_text}")
            total_chars += len(page_text)
            metadata["extracted_pages"] = page_num + 1
        
        doc.close()
        
        full_text = "".join(text_parts)
        
        return {
            "success": True,
            "text": full_text,
            "char_count": len(full_text),
            "metadata": metadata,
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "text": "",
            "metadata": {},
        }


def extract_text_file(file_path: str, max_chars: int = 100000) -> Dict[str, Any]:
    """提取文本文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(max_chars)
        
        return {
            "success": True,
            "text": content,
            "char_count": len(content),
            "metadata": {"file_size": os.path.getsize(file_path)},
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "text": "",
            "metadata": {},
        }


def extract_file_content(file_path: str, file_type: str = None) -> Dict[str, Any]:
    """
    根据文件类型提取内容
    
    Args:
        file_path: 文件路径
        file_type: MIME类型（可选）
        
    Returns:
        提取结果
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}", "text": ""}
    
    # 根据扩展名或MIME类型判断
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf' or file_type == 'application/pdf':
        return extract_pdf_text(file_path)
    elif ext in ['.txt', '.md', '.py', '.js', '.ts', '.json', '.xml', '.html', '.css']:
        return extract_text_file(file_path)
    else:
        # 尝试作为文本文件读取
        try:
            return extract_text_file(file_path)
        except:
            return {"success": False, "error": f"不支持的文件类型: {ext}", "text": ""}


if __name__ == "__main__":
    # 测试
    result = extract_file_content("Engram_paper.pdf")
    print(f"成功: {result['success']}")
    print(f"字符数: {result.get('char_count', 0)}")
    print(f"元数据: {result.get('metadata', {})}")
    if result['success']:
        print(f"\n前1000字符:\n{result['text'][:1000]}")
