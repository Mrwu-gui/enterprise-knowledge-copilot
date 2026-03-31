from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

from backend.langchain_components import (
    Document,
    load_documents_with_langchain,
    split_markdown_with_langchain,
)

try:
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

try:
    import pytesseract
    from PIL import Image
except Exception:  # pragma: no cover
    pytesseract = None
    Image = None

SUPPORTED_EXTENSIONS = {
    ".md",
    ".txt",
    ".html",
    ".htm",
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".png",
    ".jpg",
    ".jpeg",
}
TEXTLIKE_EXTENSIONS = {".md", ".txt", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PAGE_MERGE_MIN_CHARS = 280
PAGE_MERGE_MAX_CHARS = 2200
SEMANTIC_CHUNK_MIN_CHARS = 220
SEMANTIC_CHUNK_TARGET_CHARS = 720
SEMANTIC_CHUNK_MAX_CHARS = 1080

TIER_ALIAS = {
    "L1": "permanent",
    "L2": "seasonal",
    "L3": "hotfix",
    "permanent": "permanent",
    "seasonal": "seasonal",
    "hotfix": "hotfix",
}


@dataclass
class ParsedKnowledgeFile:
    filename: str
    canonical_tier: str
    original_suffix: str
    markdown_text: str
    source_type: str
    document_count: int
    chunk_count: int


class UnsupportedDocumentError(ValueError):
    pass


def normalize_tier(value: str) -> str:
    tier = str(value or "").strip()
    return TIER_ALIAS.get(tier, tier)


def ensure_supported_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError(f"暂不支持 {suffix or '无后缀'} 文件，请上传 Markdown / TXT / HTML / PDF / DOCX / PPTX")
    return suffix


def _read_utf8(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _html_to_markdown_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines: list[str] = []
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    if title:
        lines.append(f"# {title}")
        lines.append("")
    for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr"]):
        text = " ".join(node.get_text(" ", strip=True).split())
        if not text:
            continue
        name = node.name.lower()
        if name.startswith("h") and len(name) == 2 and name[1].isdigit():
            level = min(max(int(name[1]), 1), 6)
            lines.append(f"{'#' * level} {text}")
        elif name == "li":
            lines.append(f"- {text}")
        elif name == "tr":
            lines.append(f"| {text} |")
        else:
            lines.append(text)
        lines.append("")
    content = "\n".join(lines).strip()
    return html.unescape(content)


def _fallback_documents(path: Path, suffix: str) -> list[Document]:
    if suffix in {".md", ".txt"}:
        return [Document(page_content=_read_utf8(path), metadata={"source": str(path)})]
    if suffix in {".html", ".htm"}:
        return [Document(page_content=_html_to_markdown_text(_read_utf8(path)), metadata={"source": str(path)})]
    if suffix in IMAGE_EXTENSIONS:
        return _load_image_with_ocr(path)
    raise UnsupportedDocumentError(f"当前环境未安装 {suffix} 文档解析依赖，无法处理该文件")


def _load_image_with_ocr(path: Path) -> list[Document]:
    """图片文件走 OCR，方便企业上传扫描件和截图。"""
    if pytesseract is None or Image is None:
        raise UnsupportedDocumentError("当前环境未安装 OCR 依赖，暂不支持图片识别，请先上传文字版或安装 Tesseract / Pillow")
    text = pytesseract.image_to_string(Image.open(path), lang="chi_sim+eng")
    cleaned = _clean_text(text)
    return [Document(page_content=cleaned or "图片未识别出可用文字", metadata={"source": str(path), "ocr": True})]


def _ocr_pdf_with_pdfplumber(path: Path) -> list[Document]:
    """针对扫描版 PDF 做兜底 OCR，优先保证有字可检索。"""
    if pdfplumber is None or pytesseract is None:
        return []
    documents: list[Document] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                page_text = _clean_text(page.extract_text() or "")
                if page_text:
                    documents.append(
                        Document(
                            page_content=page_text,
                            metadata={"source": str(path), "page": page_index - 1, "ocr": False},
                        )
                    )
                    continue
                try:
                    rendered = page.to_image(resolution=220)
                    image = rendered.original
                except Exception:
                    continue
                ocr_text = _clean_text(pytesseract.image_to_string(image, lang="chi_sim+eng"))
                if not ocr_text:
                    continue
                documents.append(
                    Document(
                        page_content=ocr_text,
                        metadata={"source": str(path), "page": page_index - 1, "ocr": True},
                    )
                )
    except Exception:
        return []
    return documents


def _extract_pdf_tables(path: Path) -> list[str]:
    """提取 PDF 表格，尽量把企业制度、报价单、排班表这类结构化内容保留下来。"""
    if pdfplumber is None:
        return []
    table_blocks: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                for table_index, table in enumerate(page.extract_tables() or [], start=1):
                    rows = []
                    for row in table or []:
                        cleaned = [re.sub(r"\s+", " ", str(cell or "").strip()) for cell in row]
                        if any(cleaned):
                            rows.append(cleaned)
                    if not rows:
                        continue
                    header = rows[0]
                    body = rows[1:] if len(rows) > 1 else []
                    lines = [f"## 第 {page_index} 页表格 {table_index}", ""]
                    lines.append("| " + " | ".join(header) + " |")
                    lines.append("| " + " | ".join(["---"] * len(header)) + " |")
                    for row in body:
                        padded = row + [""] * (len(header) - len(row))
                        lines.append("| " + " | ".join(padded[: len(header)]) + " |")
                    table_blocks.append("\n".join(lines).strip())
    except Exception:
        return []
    return table_blocks


def _merge_cross_page_documents(docs: list[Document]) -> list[Document]:
    """
    合并跨页断开的短文本，减少企业 PDF / Word / PPT 在分页处被切碎的情况。
    规则尽量保守：只合并短页，避免把整章文档揉成一块。
    """
    if len(docs) <= 1:
        return docs
    merged: list[Document] = []
    buffer_doc: Document | None = None
    for doc in docs:
        content = _clean_text(doc.page_content)
        if not content:
            continue
        metadata = dict(doc.metadata or {})
        current = Document(page_content=content, metadata=metadata)
        if buffer_doc is None:
            buffer_doc = current
            continue
        buffer_text = _clean_text(buffer_doc.page_content)
        same_source = buffer_doc.metadata.get("source") == current.metadata.get("source")
        page_a = buffer_doc.metadata.get("page")
        page_b = current.metadata.get("page")
        consecutive_pages = isinstance(page_a, int) and isinstance(page_b, int) and page_b == page_a + 1
        should_merge = (
            same_source
            and consecutive_pages
            and len(buffer_text) < PAGE_MERGE_MIN_CHARS
            and len(buffer_text) + len(content) <= PAGE_MERGE_MAX_CHARS
        )
        if should_merge:
            buffer_doc = Document(
                page_content=f"{buffer_text}\n\n{content}",
                metadata={**buffer_doc.metadata, "page_end": page_b, "merged_pages": True},
            )
            continue
        merged.append(buffer_doc)
        buffer_doc = current
    if buffer_doc is not None:
        merged.append(buffer_doc)
    return merged


def _load_pdf_documents(path: Path) -> list[Document]:
    """PDF 优先走文本解析，文本过少时再用结构化解析或 OCR 兜底。"""
    candidates = load_documents_with_langchain(path)
    total_chars = sum(len(_clean_text(doc.page_content)) for doc in candidates)
    if total_chars >= 180:
        return _merge_cross_page_documents(candidates)
    ocr_docs = _ocr_pdf_with_pdfplumber(path)
    if ocr_docs:
        return _merge_cross_page_documents(ocr_docs)
    return _merge_cross_page_documents(candidates)


def _load_word_documents(path: Path) -> list[Document]:
    """Word 文档优先保结构，解析失败再回退到简单文本提取。"""
    docs = load_documents_with_langchain(path)
    if docs:
        return [Document(page_content=_clean_text(doc.page_content), metadata=dict(doc.metadata or {})) for doc in docs if _clean_text(doc.page_content)]
    return _fallback_documents(path, path.suffix.lower())


def _load_html_documents(path: Path) -> list[Document]:
    docs = load_documents_with_langchain(path)
    if docs:
        return [Document(page_content=_clean_text(doc.page_content), metadata=dict(doc.metadata or {})) for doc in docs if _clean_text(doc.page_content)]
    return _fallback_documents(path, path.suffix.lower())


def load_documents(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf_documents(path)
    if suffix == ".docx":
        return _load_word_documents(path)
    if suffix in {".pptx", ".xlsx", ".xls", ".md", ".txt"}:
        docs = load_documents_with_langchain(path)
        if docs:
            return [Document(page_content=_clean_text(doc.page_content), metadata=dict(doc.metadata or {})) for doc in docs if _clean_text(doc.page_content)]
    if suffix in {".html", ".htm"}:
        return _load_html_documents(path)
    return _fallback_documents(path, suffix)


def _clean_text(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"([^\n])-\n([^\n])", r"\1\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_markdown_structure(markdown_text: str) -> str:
    """
    统一标题和正文之间的空行，方便后续做标题分块和章节分块。
    """
    lines = markdown_text.replace("\r", "").splitlines()
    normalized: list[str] = []
    previous_blank = False
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("#"):
            if normalized and normalized[-1] != "":
                normalized.append("")
            normalized.append(stripped)
            previous_blank = False
            continue
        if not stripped:
            if not previous_blank:
                normalized.append("")
            previous_blank = True
            continue
        normalized.append(line)
        previous_blank = False
    text = "\n".join(normalized).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def _documents_to_markdown(docs: Iterable[Document], filename: str, suffix: str) -> str:
    docs = list(docs)
    if suffix == ".md":
        merged = "\n\n".join(_clean_text(doc.page_content) for doc in docs if _clean_text(doc.page_content))
        return merged

    title = Path(filename).stem
    lines = [f"# {title}", "", f"来源文件：{filename}", ""]
    for index, doc in enumerate(docs, start=1):
        content = _clean_text(doc.page_content)
        if not content:
            continue
        page_num = doc.metadata.get("page") if isinstance(doc.metadata, dict) else None
        if page_num is not None:
            lines.append(f"## 第 {int(page_num) + 1} 页")
        elif len(docs) > 1:
            lines.append(f"## 第 {index} 段")
        lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()


def _append_structured_extras(markdown_text: str, *, path: Path, suffix: str) -> str:
    """把 OCR / 表格等结构化附加内容并到 Markdown，保证后续切块时能一起参与检索。"""
    blocks = [markdown_text.strip()]
    if suffix == ".pdf":
        table_blocks = _extract_pdf_tables(path)
        if table_blocks:
            blocks.append("## 附加结构化表格")
            blocks.append("")
            blocks.extend(table_blocks)
    return "\n\n".join(block for block in blocks if block).strip()


def _protect_tables(markdown_text: str, metadata: dict | None = None) -> list[Document]:
    """优先把 Markdown 表格视为独立知识块，避免后续递归切分把表格切碎。"""
    segments: list[Document] = []
    current_lines: list[str] = []
    current_is_table = False
    base_metadata = dict(metadata or {})

    def flush() -> None:
        nonlocal current_lines, current_is_table
        content = "\n".join(current_lines).strip()
        if not content:
            current_lines = []
            current_is_table = False
            return
        doc_metadata = dict(base_metadata)
        if current_is_table:
            doc_metadata["structured"] = "table"
        segments.append(Document(page_content=content, metadata=doc_metadata))
        current_lines = []
        current_is_table = False

    for line in markdown_text.splitlines():
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")
        if current_lines and is_table_line != current_is_table:
            flush()
        current_is_table = is_table_line
        current_lines.append(line)
    flush()
    return [doc for doc in segments if doc.page_content.strip()]


def _split_markdown_sections(markdown_text: str) -> list[Document]:
    """
    先按标题和章节切大块，并保留标题路径，方便后续语义分块时保住上下文。
    """
    normalized = _normalize_markdown_structure(markdown_text)
    sections: list[Document] = []
    heading_stack: list[str] = []
    current_heading = ""
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_heading
        content = "\n".join(current_lines).strip()
        if not content:
            current_lines = []
            return
        heading_path = " > ".join(part for part in heading_stack if part)
        metadata = {
            "heading": current_heading,
            "heading_path": heading_path,
        }
        sections.extend(_protect_tables(content, metadata))
        current_lines = []

    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if match:
                flush()
                level = len(match.group(1))
                heading_text = match.group(2).strip()
                while len(heading_stack) >= level:
                    heading_stack.pop()
                heading_stack.append(heading_text)
                current_heading = heading_text
                current_lines = [stripped]
                continue
        current_lines.append(line)
    flush()
    return sections or [Document(page_content=normalized, metadata={})]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s+|\n{2,}", text)
    sentences = [part.strip() for part in parts if part and part.strip()]
    if sentences:
        return sentences
    return [text.strip()] if text.strip() else []


def _tokenize_for_similarity(text: str) -> set[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{1,4}|[A-Za-z0-9_]{2,}", text.lower())
    return set(tokens)


def _semantic_split_document(doc: Document) -> list[Document]:
    """
    用轻量语义策略把章节块再切小：
    - 优先按句子聚合
    - 结合关键词重叠度判断是否继续并块
    - 避免切得过碎
    """
    content = _clean_text(doc.page_content)
    if len(content) <= SEMANTIC_CHUNK_MAX_CHARS:
        return [Document(page_content=content, metadata=dict(doc.metadata or {}))]

    sentences = _split_sentences(content)
    if not sentences:
        return []

    chunks: list[Document] = []
    current_sentences: list[str] = []
    current_tokens: set[str] = set()
    current_len = 0

    def flush() -> None:
        nonlocal current_sentences, current_tokens, current_len
        chunk_text = "\n".join(current_sentences).strip()
        if chunk_text:
            chunks.append(Document(page_content=chunk_text, metadata=dict(doc.metadata or {})))
        current_sentences = []
        current_tokens = set()
        current_len = 0

    for sentence in sentences:
        sentence_tokens = _tokenize_for_similarity(sentence)
        sentence_len = len(sentence)
        overlap = len(current_tokens & sentence_tokens) if current_tokens else 0
        should_start_new = False

        if current_sentences:
            if current_len >= SEMANTIC_CHUNK_MAX_CHARS:
                should_start_new = True
            elif current_len >= SEMANTIC_CHUNK_TARGET_CHARS and overlap == 0:
                should_start_new = True
            elif current_len >= SEMANTIC_CHUNK_MIN_CHARS and sentence.startswith("#"):
                should_start_new = True

        if should_start_new:
            flush()

        current_sentences.append(sentence)
        current_tokens |= sentence_tokens
        current_len += sentence_len

    flush()
    return chunks


def _apply_semantic_chunking(docs: list[Document]) -> list[Document]:
    final_docs: list[Document] = []
    for doc in docs:
        if doc.metadata.get("structured") == "table":
            final_docs.append(doc)
            continue
        final_docs.extend(_semantic_split_document(doc))
    return final_docs


def split_documents_for_stats(markdown_text: str) -> list[Document]:
    """企业文档友好的分块策略：标题分块 -> 章节分块 -> 表格保护 -> 语义分块。"""
    normalized = _normalize_markdown_structure(markdown_text)
    docs = split_markdown_with_langchain(normalized)
    docs = [
        Document(
            page_content=_clean_text(doc.page_content),
            metadata={key: value for key, value in dict(doc.metadata or {}).items() if value},
        )
        for doc in docs
        if _clean_text(doc.page_content)
    ] or _split_markdown_sections(normalized)

    section_docs: list[Document] = []
    for doc in docs:
        if doc.metadata.get("structured") == "table":
            section_docs.append(doc)
            continue
        section_docs.extend(_split_markdown_sections(doc.page_content))
    docs = section_docs or docs

    semantic_docs = _apply_semantic_chunking(docs)
    return semantic_docs or docs


def parse_uploaded_knowledge_file(*, filename: str, raw_bytes: bytes, tier: str, temp_dir: Path) -> ParsedKnowledgeFile:
    suffix = ensure_supported_extension(filename)
    canonical_tier = normalize_tier(tier)
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / filename
    temp_path.write_bytes(raw_bytes)
    documents = load_documents(temp_path)
    markdown_text = _documents_to_markdown(documents, filename=filename, suffix=suffix)
    markdown_text = _append_structured_extras(markdown_text, path=temp_path, suffix=suffix)
    chunk_docs = split_documents_for_stats(markdown_text)
    output_name = f"{Path(filename).stem}.md"
    return ParsedKnowledgeFile(
        filename=output_name,
        canonical_tier=canonical_tier,
        original_suffix=suffix,
        markdown_text=markdown_text,
        source_type=suffix.lstrip("."),
        document_count=len(documents),
        chunk_count=len(chunk_docs),
    )
