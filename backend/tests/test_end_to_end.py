from fastapi.testclient import TestClient

from app.main import create_app


def test_coursemind_read_only_consultation_flow_end_to_end():
    api = TestClient(create_app("sqlite://"))
    frontend = api.get("/app/")
    assert frontend.status_code == 200
    assert "CourseMind" in frontend.text
    assert api.post("/admin/courses", json={
        "code": "DSC5001", "title": "Applied Data Science", "credits": 3,
        "subject": "DSC", "catalogue_year": "2026/27",
        "official_url": "https://cityu.example/DSC5001",
    }).status_code == 201
    assert api.post("/admin/source-documents", json={
        "document_type": "course", "title": "DSC5001 official facts",
        "content": "DSC5001 Applied Data Science official course facts.",
        "source_url": "https://cityu.example/DSC5001",
        "catalogue_year": "2026/27", "course_code": "DSC5001",
    }).status_code == 201
    assert api.post("/admin/offerings", json={
        "course_code": "DSC5001", "term_id": "2026-A", "section": "C01",
        "slots": [{"weekday": 2, "start_minute": 540, "end_minute": 650}],
        "source_status": "published", "source_url": "aims://2026-A",
        "credit_units": 3,
    }).status_code == 201
    assert api.put("/profiles/e2e-user", json={
        "programme": "DSC", "major_track": "DSC", "catalogue_year": "2026/27",
        "completed_courses": [{"course_code": "DSC5001", "status": "passed"}],
    }).status_code == 200
    context = api.post("/consultation/context", json={
        "user_id": "e2e-user", "message": "DSC5001 的课程内容和上课时间", "term_id": "2026-A",
    })
    assert context.status_code == 200
    assert context.json()["read_only"] is True
    assert api.get("/courses/DSC5001/details?term_id=2026-A").status_code == 200
    comparison = api.get("/courses/compare?codes=SDSC5001,DSC5001")
    assert comparison.status_code == 200
    assert [item["course_code"] for item in comparison.json()["courses"]] == ["DSC5001"]
    metrics = api.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["metrics"]["requests_total"] >= 8
