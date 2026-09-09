"""Render validated V0.3 artifacts."""
from fanglei.content_models import AngleCandidate, ScriptDraft, ScriptLintResult


def render_script_json(draft: ScriptDraft, lint: ScriptLintResult) -> dict:
    if not lint.passed: raise ValueError("script quality gate failed")
    payload = draft.model_dump(mode="json")
    payload.update({
        "speaking_rate_chars_per_second": lint.speaking_rate_chars_per_second,
        "spoken_character_count": lint.spoken_character_count,
        "estimated_duration_seconds": lint.estimated_duration_seconds,
    })
    return payload


def render_script_markdown(draft: ScriptDraft, lint: ScriptLintResult) -> str:
    if not lint.passed: raise ValueError("script quality gate failed")
    return "\n\n".join(sentence.text.strip() for sentence in draft.sentences) + "\n"


def render_angle_markdown(candidate: AngleCandidate) -> str:
    claims = "、".join(f"`{item}`" for item in candidate.supporting_claim_ids)
    return (f"# 最终内容角度\n\nselected_angle_id: `{candidate.angle_id}`\n\n## 标题\n\n{candidate.title}\n\n"
            f"## 为什么值得讲\n\n{candidate.core_question}\n\n## 核心结论\n\n{candidate.core_insight}\n\n"
            f"## Claim 链\n\n{claims}\n\n## 不能说什么\n\n- 不得使用未验证事实或把精度差异包装成机构冲突。\n")
