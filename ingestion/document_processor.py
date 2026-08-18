import re
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def load_documents_from_docx(file_path: str) -> List[Dict[str, str]]:
    """
    Parses a Microsoft Word (.docx) file into structured documents grouped by sections.
    """
    if not os.path.exists(file_path):
        logger.warning(f"DOCX file not found at {file_path}")
        return []

    try:
        from docx import Document
        doc = Document(file_path)
        
        sections = []
        current_title = "Juvelle Knowledge Base"
        current_paragraphs = []
        doc_counter = 1

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            # Check if this paragraph is a section heading
            if p.style.name.startswith("Heading") or (len(text) < 60 and text[0].isdigit() and "." in text[:3]):
                if current_paragraphs:
                    sections.append({
                        "doc_id": f"DOCX_SEC_{doc_counter}",
                        "doc_title": current_title,
                        "source_uri": f"docx://{os.path.basename(file_path)}#{doc_counter}",
                        "raw_text": " ".join(current_paragraphs)
                    })
                    doc_counter += 1
                    current_paragraphs = []
                current_title = text
            else:
                current_paragraphs.append(text)

        if current_paragraphs:
            sections.append({
                "doc_id": f"DOCX_SEC_{doc_counter}",
                "doc_title": current_title,
                "source_uri": f"docx://{os.path.basename(file_path)}#{doc_counter}",
                "raw_text": " ".join(current_paragraphs)
            })

        logger.info(f"Loaded {len(sections)} sections from DOCX file: {file_path}")
        return sections

    except Exception as e:
        logger.error(f"Error reading DOCX file {file_path}: {e}")
        return []

def chunk_text_content(
    text: str,
    doc_id: str,
    doc_title: str,
    source_uri: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> List[Dict[str, Any]]:
    """
    Splits text into semantic, token-aware chunks with overlapping context window.
    """
    if not text or not text.strip():
        return []

    cleaned_text = re.sub(r'\s+', ' ', text).strip()
    words = cleaned_text.split(' ')
    total_words = len(words)
    chunks = []
    
    start_idx = 0
    chunk_seq = 0

    while start_idx < total_words:
        end_idx = min(start_idx + chunk_size, total_words)
        chunk_words = words[start_idx:end_idx]
        chunk_str = " ".join(chunk_words)

        chunks.append({
            "chunk_id": f"{doc_id}_chk_{chunk_seq}",
            "doc_id": doc_id,
            "doc_title": doc_title,
            "source_uri": source_uri,
            "chunk_index": chunk_seq,
            "content": chunk_str,
            "token_count": len(chunk_words)
        })

        chunk_seq += 1
        start_idx += (chunk_size - chunk_overlap)
        if start_idx >= total_words:
            break

    return chunks

def process_documents_distributed(
    df_raw: Any,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> Any:
    """
    Applies distributed chunking across all partitions of the raw documents DataFrame.
    Supports both PySpark DataFrame and LocalSpark DataFrame.
    """
    try:
        from pyspark.sql.functions import udf, explode, col
        from pyspark.sql.types import ArrayType, StructType, StructField, StringType, IntegerType

        chunk_struct_schema = StructType([
            StructField("chunk_id", StringType(), False),
            StructField("doc_id", StringType(), False),
            StructField("doc_title", StringType(), True),
            StructField("source_uri", StringType(), True),
            StructField("chunk_index", IntegerType(), False),
            StructField("content", StringType(), False),
            StructField("token_count", IntegerType(), False)
        ])

        chunk_udf = udf(
            lambda text, d_id, title, uri: chunk_text_content(text, d_id, title, uri, chunk_size, chunk_overlap),
            ArrayType(chunk_struct_schema)
        )

        df_chunked = df_raw.withColumn(
            "chunks",
            chunk_udf(col("raw_text"), col("doc_id"), col("doc_title"), col("source_uri"))
        )
        return df_chunked.select(explode(col("chunks")).alias("chunk")).select("chunk.*")

    except Exception:
        # Local Spark Engine fallback
        all_chunks = []
        for row in df_raw.collect():
            raw_text = row.get("raw_text") if isinstance(row, dict) else row.raw_text
            d_id = row.get("doc_id") if isinstance(row, dict) else row.doc_id
            title = row.get("doc_title") if isinstance(row, dict) else row.doc_title
            uri = row.get("source_uri") if isinstance(row, dict) else row.source_uri

            chunks = chunk_text_content(raw_text, d_id, title, uri, chunk_size, chunk_overlap)
            all_chunks.extend(chunks)

        return df_raw.sparkSession.createDataFrame(all_chunks)
