import os

PIPELINE_PATH = os.environ.get("PIPELINE_PATH", "/app/pipeline/main.nf")
WORK_DIR = os.environ.get("WORK_DIR", "/data/work")
DB_PATH = os.environ.get("DB_PATH", "/data/runs.db")
PORT = int(os.environ.get("PORT", "8000"))
NEXTFLOW_BIN = os.environ.get("NEXTFLOW_BIN", "nextflow")
