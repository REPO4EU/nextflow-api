import os

PIPELINE_PATH = os.environ.get("PIPELINE_PATH", "/app/pipeline/main.nf")
RUN_DIR = os.environ.get("RUN_DIR", "/data/runs")
DB_PATH = os.environ.get("DB_PATH", "/data/runs.db")
PORT = int(os.environ.get("PORT", "8000"))
NEXTFLOW_BIN = os.environ.get("NEXTFLOW_BIN", "nextflow")
JWT_SECRET = os.environ.get("JWT_SECRET")

# Consul configuration
CONSUL_ENABLED = os.environ.get("CONSUL_ENABLED", "false").lower() == "true"
CONSUL_BASE_URL = os.environ.get("CONSUL_BASE_URL", None)
CONSUL_TOKEN = os.environ.get("CONSUL_TOKEN", None)
CONSUL_SERVICE_ID = os.environ.get("CONSUL_SERVICE_ID", "NextflowApi")
CONSUL_SERVICE_NAME = os.environ.get("CONSUL_SERVICE_NAME", "NextflowApi")
CONSUL_SERVICE_API_URL = os.environ.get("CONSUL_SERVICE_API_URL", "localhost")
CONSUL_SERVICE_API_PORT = int(os.environ.get("CONSUL_SERVICE_API_PORT", "8000"))
