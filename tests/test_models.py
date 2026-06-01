from app.models import RunStatus, SubmitRequest, RunResponse, RunListItem

def test_run_status_values():
    assert set(RunStatus) == {"queued", "running", "completed", "failed", "cancelled"}

def test_submit_request_requires_params():
    req = SubmitRequest(params={"input": "s3://bucket/file.csv", "outdir": "/data/out"})
    assert req.params["input"] == "s3://bucket/file.csv"

def test_run_response_fields():
    r = RunResponse(
        id="abc",
        status=RunStatus.queued,
        params={"input": "x"},
        created_at="2026-01-01T00:00:00Z",
        started_at=None,
        finished_at=None,
        exit_code=None,
    )
    assert r.status == RunStatus.queued
    assert r.exit_code is None
