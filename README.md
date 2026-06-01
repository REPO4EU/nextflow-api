# Nextflow API

This service exposes a small FastAPI wrapper around the `nf-core/diseasemodulediscovery` Nextflow pipeline. It runs the pipeline in a container and stores each run under `${DATA_DIR}/runs/<run_id>/`.

## Setup

### 1. Clone this repository

```bash
git clone https://github.com/REPO4EU/nextflow-api.git
cd nextflow-api
```

### 2. Clone the Disease Module Discovery pipeline

The API expects the `nf-core/diseasemodulediscovery` pipeline to be available locally and referenced by `PIPELINE_DIR` in `.env`.

```bash
git clone https://github.com/nf-core/diseasemodulediscovery.git diseasemodulediscovery
```

If you place the pipeline somewhere else, update `PIPELINE_DIR` accordingly.

### 3. Configure `.env`

Create or edit `.env` in the repository root. A minimal configuration looks like this:

```env
DATA_DIR=/absolute/path/to/data/dir/
PIPELINE_DIR=/absolute/path/to/pipeline/dir/
```

Notes:
- `DATA_DIR` is mounted into the container and holds run data and the SQLite database.
- `PIPELINE_DIR` must point at the cloned `nf-core/diseasemodulediscovery` repository.

### 4. Build and launch the container

```bash
docker compose up --build
```


## API Access

Once the container is running, the API is available at:

```text
http://localhost:8000
```

Docs and interactive queries:
```text
http://localhost:8000/docs
```

Useful endpoints:

- `POST /runs` - submit a new pipeline run
- `GET /runs` - list runs
- `GET /runs/{run_id}` - inspect a run
- `GET /runs/{run_id}/logs` - read the Nextflow log for a run
- `DELETE /runs/{run_id}` - cancel a running job

Example submit request:

```bash
curl -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"params":{"input":"/path/to/input.json"}}'
```

You can also add `"profile": "docker,test"` to run the pipeline with the test profile.

## Result Structure

Each submission gets its own run directory under `data/runs/<run_id>/`.

```text
${DATA_DIR}/runs/<run_id>/
├── nextflow.log
├── results/
└── work/
```

- `nextflow.log` contains the Nextflow execution log.
- `work/` contains Nextflow intermediate work files.
- `results/` contains the pipeline outputs produced by the run.

The API also stores run metadata in `data/runs.db`, including status, timestamps, and exit code.

## Curl Example Run

Here is a simple end-to-end flow using `curl` after the container is up.

Submit a run and store the id:

```bash
run_id=$(curl -s -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"params":{},"profile":"docker,test"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
```

```bash
echo $run_id
```

Check the run status:

```bash
curl -s http://localhost:8000/runs/$run_id
```

Read the Nextflow log:

```bash
curl -s http://localhost:8000/runs/$run_id/logs
```

List all runs:

```bash
curl -s http://localhost:8000/runs
```

If you omit `profile`, the API uses `docker` by default.
