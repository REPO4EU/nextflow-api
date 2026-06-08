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
JWT_SECRET=your-jwt-secret
AUTH_ENABLED=true
```

Notes:
- `DATA_DIR` is mounted into the container and holds run data and the SQLite database.
- `PIPELINE_DIR` must point at the cloned `nf-core/diseasemodulediscovery` repository.
- `JWT_SECRET` is used to validate incoming bearer tokens when `AUTH_ENABLED=true`.
- Set `AUTH_ENABLED=false` to disable authentication for all protected endpoints.

### 4. Configure `nextflow.config` (optional)

A `nextflow.config` file in the repository root is automatically passed to every pipeline run via the `-c` flag. Use it to set Nextflow options that apply to all runs, for example:

```groovy
cleanup = true
```

### 5. Build and launch the container

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

## Submitting Input Files

`POST /runs` accepts multipart form data with three fields:

| Field | Type | Description |
|---|---|---|
| `params` | JSON string | Pipeline parameters passed as `--key value` flags |
| `profile` | string | Nextflow profile(s), e.g. `docker` or `docker,test` (default: `docker`) |
| `files` | file(s) | Input files to upload (optional, repeatable) |

Uploaded files are saved to the run's `input/` directory before the pipeline starts. The pipeline is then executed with the run directory as its working directory, so uploaded files can be referenced in `params` using the relative prefix `input/<filename>` — no absolute paths needed.

Example with two input files:

```bash
curl -X POST http://localhost:8000/runs \
  -F 'params={"seeds":"input/seeds.csv","network":"input/ppi.csv"}' \
  -F 'profile=docker' \
  -F 'files=@seeds.csv' \
  -F 'files=@ppi.csv'
```

## Curl Example Run

Here is a simple end-to-end flow using `curl` after the container is up.

Submit a run and store the id:

```bash
run_id=$(curl -s -X POST http://localhost:8000/runs \
  -F 'params={"seeds":"input/entrez_seeds_1.csv", "network": "input/entrez_ppi.csv"}' \
  -F 'profile=docker,test' \
  -F 'files=@test_data/entrez_seeds_1.csv' \
  -F 'files=@test_data/entrez_ppi.csv' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
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

## Run tests
```bash
docker compose run --build --rm nextflow-api python3.11 -m pytest tests/
```

## Run interactive session
```bash
docker compose run --build --rm nextflow-api bash
```