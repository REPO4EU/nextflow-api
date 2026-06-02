from app.models import RunStatus, RunResponse, RunListItem

def test_run_status_values():
    assert set(RunStatus) == {"queued", "running", "completed", "failed", "cancelled"}

def test_run_response_fields():
    r = RunResponse(
        id="abc",
        status=RunStatus.queued,
        params={"input": "x"},
        command=None,
        run_dir=None,
        created_at="2026-01-01T00:00:00Z",
        started_at=None,
        finished_at=None,
        exit_code=None,
    )
    assert r.status == RunStatus.queued
    assert r.exit_code is None
