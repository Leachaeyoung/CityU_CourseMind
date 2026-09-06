from fastapi.testclient import TestClient

from app.main import create_app


def client():
    return TestClient(create_app("sqlite://"))


def test_profile_normalizes_historical_programme_name_and_keeps_course_records():
    api = client()
    response = api.put(
        "/profiles/student-1",
        json={
            "programme": "SDSC",
            "catalogue_year": "2024-25",
            "completed_courses": [{"course_code": "DSC1001", "status": "passed"}],
            "current_courses": [{"course_code": "CS1001", "status": "in_progress"}],
            "max_credits": 12,
            "unavailable_slots": [{"weekday": 2, "start_minute": 540, "end_minute": 600}],
            "interests": ["NLP"],
            "workload_preference": "medium",
        },
    )
    assert response.status_code == 200
    assert response.json()["programme"] == "DSC"
    assert response.json()["completed_courses"][0]["course_code"] == "DSC1001"


def test_my_profile_normalizes_historical_sdsc_course_records():
    api = client()
    response = api.put(
        "/profiles/legacy-student",
        json={
            "programme": "SDSC",
            "major_track": "DSC",
            "catalogue_year": "2026/27",
            "completed_courses": [{"course_code": "SDSC2001", "status": "passed"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["completed_courses"][0]["course_code"] == "DSC2001"


def test_metrics_expose_request_and_evidence_observability_without_user_content():
    api = client()
    assert api.get("/health").status_code == 200
    metrics = api.get("/metrics")
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["metrics"]["requests_total"] >= 2
    assert "average_latency_ms" in payload["metrics"]
    assert "student" not in str(payload).lower()


def test_any_student_can_publish_course_reviews():
    api = client()
    assert api.post(
        "/admin/courses",
        json={
            "code": "DSC4000",
            "title": "Example course",
            "credits": 3,
            "subject": "DSC",
            "catalogue_year": "2024-25",
            "official_url": "https://example.invalid/DSC4000",
        },
    ).status_code == 201
    assert api.put(
        "/profiles/student-1",
        json={
            "programme": "DSC",
            "catalogue_year": "2024-25",
            "completed_courses": [{"course_code": "DSC4000", "status": "passed"}],
        },
    ).status_code == 200

    review = {
        "author_id": "student-1",
        "term_id": "2025-A",
        "overall_rating": 4,
        "workload": "high",
        "difficulty": "medium",
        "assessment_pressure": "high",
        "content": "This is a sufficiently detailed course review for a realistic community entry.",
    }
    assert api.post("/courses/DSC4000/reviews", json=review).status_code == 201

    summary = api.get("/courses/DSC4000/reviews")
    assert summary.status_code == 200
    assert summary.json()["review_count"] == 1
    assert summary.json()["total_review_count"] == 1
    assert summary.json()["returned_count"] == 1
    assert summary.json()["average_rating"] == 4.0

    review["author_id"] = "student-without-course"
    assert api.put(
        "/profiles/student-without-course",
        json={"programme": "DSC", "catalogue_year": "2024-25"},
    ).status_code == 200
    assert api.post("/courses/DSC4000/reviews", json=review).status_code == 201


def test_chat_route_requires_official_evidence_before_course_answer_generation():
    api = client()
    assert api.post(
        "/admin/source-documents",
        json={
            "document_type": "course",
            "title": "DSC4070 Large Language Models",
            "content": "DSC4070 official course description and prerequisite information.",
            "source_url": "https://www.cityu.edu.hk/catalogue/ug/current/course/DSC4070.htm",
            "catalogue_year": "2024-25",
            "course_code": "DSC4070",
        },
    ).status_code == 201
    routed = api.post(
        "/chat/route",
        json={"message": "DSC4070 的课程内容和先修课是什么？"},
    )
    assert routed.status_code == 200
    payload = routed.json()
    assert payload["routing"]["evidence_requirement"] == "official_course"
    assert payload["answer_generation_allowed"] is True
    assert payload["official_evidence"][0]["source_url"].endswith("DSC4070.htm")


def test_evidence_retrieval_normalizes_legacy_sdsc_course_code():
    api = client()
    assert api.post(
        "/admin/source-documents",
        json={
            "document_type": "course",
            "title": "DSC3006 official course page",
            "content": "DSC3006 Fundamentals of Machine Learning I; prerequisite MA2506 or MA2510.",
            "source_url": "https://www.cityu.edu.hk/catalogue/ug/current/course/DSC3006.htm",
            "catalogue_year": "2026/27",
            "course_code": "DSC3006",
        },
    ).status_code == 201
    routed = api.post("/chat/route", json={"message": "SDSC3006 的先修课是什么？"})
    assert routed.status_code == 200
    assert routed.json()["official_evidence"][0]["title"].startswith("DSC3006")


def test_chat_route_blocks_verified_schedule_conclusion_without_published_term_data():
    api = client()
    routed = api.post(
        "/chat/route",
        json={"message": "帮我排下学期不冲突的课表"},
    )
    payload = routed.json()
    assert payload["routing"]["evidence_requirement"] == "official_schedule"
    assert payload["answer_generation_allowed"] is False
    assert any("目标学期" in blocker for blocker in payload["blockers"])


def test_consultation_context_is_read_only_and_reuses_saved_profile():
    api = client()
    assert api.put("/profiles/consult-user", json={
        "programme": "DSC", "major_track": "DSC", "catalogue_year": "2026/27",
        "interests": ["machine learning"],
    }).status_code == 200
    response = api.post("/consultation/context", json={
        "user_id": "consult-user", "message": "推荐下学期课程", "term_id": "2026-A",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_found"] is True
    assert payload["profile"]["interests"] == ["machine learning"]
    assert payload["read_only"] is True
    assert "注册" in payload["notice"]


def test_course_details_keeps_catalogue_and_aims_layers_separate():
    api = client()
    assert api.post("/admin/courses", json={
        "code": "DSC9999", "title": "Example", "credits": 3, "subject": "DSC",
        "catalogue_year": "2026/27", "official_url": "https://example.invalid/course",
    }).status_code == 201
    assert api.post("/admin/offerings", json={
        "course_code": "DSC9999", "term_id": "2026-A", "section": "C01",
        "slots": [{"weekday": 1, "start_minute": 540, "end_minute": 650}],
        "source_status": "published", "source_url": "aims://snapshot",
    }).status_code == 201
    response = api.get("/courses/DSC9999/details?term_id=2026-A")
    assert response.status_code == 200
    payload = response.json()
    assert payload["aims_is_authoritative_for_term"] is True
    assert payload["aims_offerings"][0]["source_url"] == "aims://snapshot"
    assert payload["course"]["official_url"].endswith("course")
    assert payload["community"]["review_count"] == 0
    assert "available_seats" not in payload["aims_offerings"][0]
    assert "capacity" not in payload["aims_offerings"][0]
    assert "waitlist_available" not in payload["aims_offerings"][0]


def test_planning_candidates_filters_by_profile_and_aims_section_restriction():
    api = client()
    assert api.post("/admin/courses", json={
        "code": "DSC9998", "title": "Candidate", "credits": 3, "subject": "DSC",
        "catalogue_year": "2026/27", "official_url": "https://example.invalid/candidate",
    }).status_code == 201
    assert api.put("/profiles/u1", json={
        "programme": "DSC", "major_track": "DSC", "catalogue_year": "2026/27",
    }).status_code == 200
    assert api.post("/admin/programme-course-scopes", json={
        "programme": "DSC", "catalogue_year": "2026/27", "course_code": "DSC9998",
        "scope": "elective", "source_url": "https://example.invalid/scope",
    }).status_code == 201
    assert api.post("/admin/offerings", json={
        "course_code": "DSC9998", "term_id": "2026-A", "section": "C01",
        "slots": [{"weekday": 1, "start_minute": 540, "end_minute": 650}],
        "source_status": "published", "source_url": "aims://snapshot",
        "allowed_majors": ["DSE"],
    }).status_code == 201
    result = api.get("/planning/candidates?user_id=u1&term_id=2026-A")
    assert result.status_code == 200
    assert result.json()["candidates"] == []
    assert result.json()["excluded"][0]["reason"] == "AIMS section restriction"


def test_compare_courses_separates_official_facts_from_community_signals():
    api = client()
    for code in ("DSC9001", "DSC9002"):
        assert api.post("/admin/courses", json={"code": code, "title": code, "credits": 3, "subject": "DSC", "catalogue_year": "2026/27", "official_url": "https://example.invalid/" + code}).status_code == 201
    response = api.get("/courses/compare?codes=DSC9001,DSC9002")
    assert response.status_code == 200
    assert len(response.json()["courses"]) == 2
    assert "community" in response.json()["courses"][0]
    assert "official_url" in response.json()["courses"][0]
    assert response.json()["not_found"] == []
    assert "average_difficulty" in response.json()["dimensions"]


def test_plan_preflight_checks_official_sections_prerequisites_and_conflicts():
    api = client()
    for code, prerequisite in (("DSC1001", []), ("CS2001", ["DSC1001"]), ("DSC2002", [])):
        assert api.post(
            "/admin/courses",
            json={
                "code": code,
                "title": f"Course {code}",
                "credits": 3,
                "subject": "CS" if code.startswith("CS") else "DSC",
                "catalogue_year": "2024-25",
                "official_url": f"https://example.invalid/{code}",
                "required_all": prerequisite,
            },
        ).status_code == 201
    assert api.put(
        "/profiles/student-1",
        json={
            "programme": "DSC",
            "catalogue_year": "2024-25",
            "completed_courses": [{"course_code": "DSC1001", "status": "passed"}],
            "max_credits": 6,
        },
    ).status_code == 200
    for code in ("CS2001", "DSC2002"):
        assert api.post(
            "/admin/programme-course-scopes",
            json={
                "programme": "DSC",
                "catalogue_year": "2024-25",
                "course_code": code,
                "scope": "elective",
                "source_url": "https://example.invalid/dsc-scheme",
            },
        ).status_code == 201
    for course_code, section, start, end in (("CS2001", "A", 540, 630), ("DSC2002", "B", 600, 660)):
        assert api.post(
            "/admin/offerings",
            json={
                "course_code": course_code,
                "term_id": "2026-A",
                "section": section,
                "slots": [{"weekday": 1, "start_minute": start, "end_minute": end}],
                "source_status": "published",
                "source_url": "https://example.invalid/master-schedule",
            },
        ).status_code == 201
    preflight = api.post(
        "/planning/preflight",
        json={
            "user_id": "student-1",
            "term_id": "2026-A",
            "selections": [
                {"course_code": "CS2001", "section": "A"},
                {"course_code": "DSC2002", "section": "B"},
            ],
        },
    )
    assert preflight.status_code == 200
    payload = preflight.json()
    assert payload["prerequisite_checks"]["CS2001"]["eligible"] is True
    assert len(payload["schedule_conflicts"]) == 1
    assert payload["hard_constraints_passed"] is False
