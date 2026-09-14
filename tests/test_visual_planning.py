from fanglei.providers.visual import DeterministicVisualPlanningProvider, VisualPlanningRequest


def _script():
    rows = [
        ("sentence_001", "hook", "interpretation", "同一个GDP，两个数字，到底谁错了？", []),
        ("sentence_002", "phenomenon", "verified_fact", "BEA公布的2024年美国实际GDP增长率是2.8%。", ["claim_007"]),
        ("sentence_003", "phenomenon", "verified_fact", "世界银行API里保留的数值约是2.7932%。", ["claim_007"]),
        ("sentence_004", "phenomenon", "interpretation", "看起来不一样，对吧？", []),
        ("sentence_005", "mechanism", "verified_fact", "2.7932%四舍五入到一位小数就是2.8%。", ["claim_007"]),
        ("sentence_006", "mechanism", "interpretation", "差别在数字写到哪一位。", []),
        ("sentence_007", "mechanism", "interpretation", "一个简略，一个更细。", []),
        ("sentence_008", "mechanism", "explanation", "下次看到经济数据不一样先别急。", []),
        ("sentence_009", "mechanism", "explanation", "先追到原始来源。", []),
        ("sentence_010", "mechanism", "explanation", "再看指标名称和年份。", []),
        ("sentence_011", "mechanism", "explanation", "再检查保留几位小数。", []),
        ("sentence_012", "mechanism", "interpretation", "只是精度不同就不是真冲突。", []),
        ("sentence_013", "mechanism", "interpretation", "对不上就继续追问。", []),
        ("sentence_014", "core_judgment", "analogy", "不是数据打架，只是小数点藏了一部分。", []),
    ]
    return {"schema_version": "3.0", "script_id": "script_001", "estimated_duration_seconds": 74.75,
            "sentences": [{"sentence_id": i, "section": sec, "sentence_type": typ,
                           "text": text, "claim_ids": claims} for i, sec, typ, text, claims in rows]}


def test_gdp_planner_creates_semantic_multi_sentence_beats() -> None:
    plan = DeterministicVisualPlanningProvider().plan(VisualPlanningRequest(
        run_id="gdp", script=_script(), allowed_claim_ids={"claim_007"}
    ))
    assert 4 <= len(plan.beats) <= 7
    covered = [sid for beat in plan.beats for sid in beat.sentence_ids]
    assert covered == [f"sentence_{index:03d}" for index in range(1, 15)]
    assert len(plan.beats) < len(covered)
    assert any(len(beat.sentence_ids) >= 3 for beat in plan.beats)


def test_gdp_planner_keeps_claims_and_exact_relationship() -> None:
    plan = DeterministicVisualPlanningProvider().plan(VisualPlanningRequest(
        run_id="gdp", script=_script(), allowed_claim_ids={"claim_007"}
    ))
    payload = plan.model_dump(mode="json")
    assert any("2.8%" in beat["core_visual_relationship"] for beat in payload["beats"])
    assert any("2.7932%" in beat["core_visual_relationship"] for beat in payload["beats"])
    assert any("四舍五入" in beat["core_visual_relationship"] for beat in payload["beats"])
    assert {cid for beat in plan.beats for cid in beat.claim_ids} == {"claim_007"}
    assert all("placement" not in beat and "renderer_directives" not in beat for beat in payload["beats"])


def test_planner_rejects_claim_not_allowed_downstream() -> None:
    script = _script()
    script["sentences"][1]["claim_ids"] = ["claim_unverified"]
    try:
        DeterministicVisualPlanningProvider().plan(VisualPlanningRequest(
            run_id="gdp", script=script, allowed_claim_ids={"claim_007"}
        ))
    except ValueError as error:
        assert "VISUAL_CLAIM_NOT_ALLOWED" in str(error)
    else:
        raise AssertionError("disallowed visible claim must fail closed")


def test_planner_does_not_introduce_facts_absent_from_script() -> None:
    script = _script()
    for row in script["sentences"]:
        row["text"] = "这个例子只讨论一个抽象指标。"
        row["claim_ids"] = []
        row["sentence_type"] = "explanation"
    script["sentences"][1].update(text="这个抽象指标是1.2%。", sentence_type="verified_fact",
                                  claim_ids=["claim_generic"])
    payload = DeterministicVisualPlanningProvider().plan(VisualPlanningRequest(
        run_id="generic", script=script, allowed_claim_ids={"claim_generic"}
    )).model_dump_json()
    for forbidden in ("2.8%", "2.7932%", "BEA", "World Bank", "2024"):
        assert forbidden not in payload
