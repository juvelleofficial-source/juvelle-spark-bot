import os
import sys
import logging
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Entrypoint")

if __name__ == "__main__":
    port_env = os.environ.get("PORT", "8000")
    try:
        port = int(port_env)
    except ValueError:
        port = 8000
        
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"Starting Juvelle Spark Bot MCP & RAG Server on {host}:{port}...")
    uvicorn.run("api.main:app", host=host, port=port, log_level="info")
