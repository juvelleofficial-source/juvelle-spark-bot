import os
import sys
import logging
from typing import List, Dict
from ingestion.spark_session import get_spark_session
from ingestion.document_processor import process_documents_distributed, load_documents_from_docx
from ingestion.batch_embedder import generate_embeddings_distributed
from ingestion.vector_indexer import sync_to_local_vector_cache, export_for_vertex_vector_search
from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SparkIngestionJob")

def get_knowledge_documents() -> List[Dict[str, str]]:
    """
    Loads knowledge documents from the editable Microsoft Word (.docx) file if available,
    falling back to built-in brand chunks.
    """
    docx_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "Juvelle_Knowledge_Base.docx")
    if os.path.exists(docx_path):
        docx_docs = load_documents_from_docx(docx_path)
        if docx_docs:
            logger.info(f"Loaded {len(docx_docs)} document sections directly from {docx_path}")
            return docx_docs

    # Fallback to default in-memory chunks
    return [
        {
            "doc_id": "JUV_001",
            "doc_title": "Juvelle Brand Identity & Apparel Catalog",
            "source_uri": "juvelle://catalog/products_and_pricing.md",
            "raw_text": (
                "Juvelle is an exclusive women's clothing boutique based in Kerala. "
                "USP: Premium quality fabric at the most affordable price. "
                "Products: Exclusively Churidar tops made with breathable cotton and premium rayon blends "
                "suitable for daily wear, office wear, and college wear. "
                "Standard price range is ₹399 - ₹899. "
                "Juvelle does NOT sell kids wear, men wear, western clothing, sarees, frocks, jeans, or t-shirts."
            )
        },
        {
            "doc_id": "JUV_002",
            "doc_title": "Juvelle Shipping, Logistics & Delivery Coverage",
            "source_uri": "juvelle://logistics/delivery_policy.md",
            "raw_text": (
                "Delivery Location: KERALA ONLY. Juvelle currently delivers exclusively to addresses within Kerala. "
                "Orders to other states or abroad (Tamil Nadu, Bangalore, Mumbai, Dubai, etc.) are politely declined. "
                "Courier Partner: Delhivery courier service. "
                "Dispatch Timeline: Next working day after payment confirmation. "
                "Delivery Time: Usually 2-3 business days anywhere in Kerala."
            )
        },
        {
            "doc_id": "JUV_003",
            "doc_title": "Juvelle Ordering Process & Payment Methods",
            "source_uri": "juvelle://sales/ordering_and_payment.md",
            "raw_text": (
                "Website: Juvelle does NOT have an official website yet. "
                "How to Order: Customers place orders directly in chat by sending a screenshot of the desired Churidar top "
                "along with their required size (S, M, L, XL, XXL). "
                "Payment Method: Online payment only (UPI, Google Pay, PhonePe, Paytm, direct Bank Transfer). "
                "Cash on Delivery (COD) is NOT available to ensure rapid next-day dispatch."
            )
        },
        {
            "doc_id": "JUV_004",
            "doc_title": "Juvelle Quality, Fabric Care & Customer Support",
            "source_uri": "juvelle://support/fabric_and_contact.md",
            "raw_text": (
                "Fabric Quality: 100% breathable pure cotton and premium soft rayon blends tested for daily comfort. "
                "Customer Support: Support is handled right here via Instagram Direct Message and WhatsApp chat. "
                "Return & Exchanges: Damaged items are replaced upon providing an opening video; size assistance is provided prior to dispatch."
            )
        }
    ]

def run_ingestion_pipeline(sample_docs: List[Dict[str, str]] = None, export_gcs: bool = False):
    """
    Executes the full Spark ETL Ingestion Pipeline:
    1. Read Raw Documents from DOCX / In-memory
    2. Distributed Token Chunking
    3. Distributed Batch Embedding Generation
    4. Indexing into Vertex Vector Search / Local Vector Store
    """
    logger.info("==================================================")
    logger.info("Starting Apache Spark Enterprise Ingestion Pipeline")
    logger.info("==================================================")

    spark = get_spark_session("GeminiSparkIngestionPipeline")
    
    docs = sample_docs or get_knowledge_documents()
    logger.info(f"Loaded {len(docs)} input documents for distributed processing.")

    # 1. Create PySpark DataFrame from input documents
    df_raw = spark.createDataFrame(docs)
    logger.info("Raw documents DataFrame created. Partitions: " + str(df_raw.rdd.getNumPartitions()))

    # 2. Distributed Chunking
    logger.info("Executing distributed token chunking...")
    df_chunks = process_documents_distributed(
        df_raw,
        chunk_size=settings.CHUNK_SIZE_TOKENS,
        chunk_overlap=settings.CHUNK_OVERLAP_TOKENS
    )
    chunk_count = df_chunks.count()
    logger.info(f"Generated {chunk_count} semantic text chunks.")

    # 3. Distributed Embeddings
    logger.info("Generating distributed vector embeddings via Spark mapPartitions...")
    df_embedded = generate_embeddings_distributed(df_chunks)
    
    # 4. Vector Store Sync
    logger.info("Syncing embeddings to vector index...")
    synced_count = sync_to_local_vector_cache(df_embedded)
    logger.info(f"Successfully indexed {synced_count} vector records.")

    # 5. Export to GCS for Vertex AI Vector Search if requested
    if export_gcs and settings.GCS_BUCKET_NAME:
        gcs_target = f"gs://{settings.GCS_BUCKET_NAME}/vector_indexes/latest"
        export_for_vertex_vector_search(df_embedded, gcs_target)

    logger.info("==================================================")
    logger.info("Spark Ingestion Pipeline Completed Successfully!")
    logger.info("==================================================")
    return synced_count

if __name__ == "__main__":
    run_ingestion_pipeline()
