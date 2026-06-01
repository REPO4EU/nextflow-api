import os

PIPELINE_PATH = os.environ.get("PIPELINE_PATH", "/app/pipeline/main.nf")
RUN_DIR = os.environ.get("RUN_DIR", "/data/runs")
DB_PATH = os.environ.get("DB_PATH", "/data/runs.db")
PORT = int(os.environ.get("PORT", "8000"))
NEXTFLOW_BIN = os.environ.get("NEXTFLOW_BIN", "nextflow")
