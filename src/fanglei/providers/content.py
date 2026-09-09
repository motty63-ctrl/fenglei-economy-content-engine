"""Provider boundary and deterministic V0.3 mock."""
from typing import Protocol
from pydantic import BaseModel
from fanglei.content_models import AngleCandidate, AngleProposal, AngleProposalResult, ScriptDraft, ScriptReadyClaim, ScriptSentence


class AngleGenerationInput(BaseModel):
    run_id: str
    core_topic: str
    research_questions: list[str]
    research_md: str
    fact_palette: tuple[ScriptReadyClaim, ...]


class ScriptGenerationInput(BaseModel):
    run_id: str
    selected_angle: AngleCandidate
    research_md: str
    fact_palette: tuple[ScriptReadyClaim, ...]


class ContentPlanningProvider(Protocol):
    name: str
    model: str | None
    angle_prompt_version: str
    script_prompt_version: str
    def generate_angles(self, request: AngleGenerationInput) -> AngleProposalResult: ...
    def generate_script(self, request: ScriptGenerationInput) -> ScriptDraft: ...


class MockContentPlanningProvider:
    name = "mock-content"
    model = None
    angle_prompt_version = "angles-v1"
    script_prompt_version = "script-v1"

    def generate_angles(self, request: AngleGenerationInput) -> AngleProposalResult:
        claim_id = request.fact_palette[0].claim_id
        rows = [
            ("angle_001", "小数点后，藏着一个假问题", "两个权威数字差一点，问题可能不在经济本身。", "显示精度不同，不等于结论冲突"),
            ("angle_002", "数字越长，就一定越准吗", "更多小数位带来的是信息，还是错觉？", "公开传播和研究计算需要不同精度"),
            ("angle_003", "看GDP，先别急着比小数", "读经济数据，第一步为什么不是比较大小？", "先核对指标、时期和精度，再解释经济含义"),
        ]
        return AngleProposalResult(candidates=[AngleProposal(
            angle_id=i, title=t, hook=h, core_question=h, core_insight=insight,
            supporting_claim_ids=[claim_id], audience_relevance=5, novelty=4,
            hook_strength=4, visual_potential=3, explainability=5,
        ) for i, t, h, insight in rows])

    def generate_script(self, request: ScriptGenerationInput) -> ScriptDraft:
        claim = request.fact_palette[0]
        texts = [
            ("hook", "interpretation", "同一个增长率，为什么会出现两种写法？"),
            ("phenomenon", "verified_fact", claim.claim_text),
            ("mechanism", "explanation", "先别急着判断谁对谁错，第一步是把指标、年份和计算范围对齐。"),
            ("mechanism", "explanation", "如果这些条件相同，差别往往只是结果展示时保留了几位小数。"),
            ("mechanism", "analogy", "这就像同一段距离，一个人说大约三公里，另一个人写到具体米数。"),
            ("mechanism", "explanation", "短数字方便新闻传播，长数字方便研究者复算，它们服务的场景并不相同。"),
            ("mechanism", "interpretation", "真正值得追问的不是小数点后多了几位，而是口径有没有变化。"),
            ("mechanism", "explanation", "还要看数据是否来自同一年度，是否经过修订，以及增长率是不是实际口径。"),
            ("mechanism", "analogy", "刻度更细不代表方向相反，它只是让同一个位置被描述得更具体。"),
            ("mechanism", "interpretation", "普通人看到两个数字时，最容易把显示差异误读成机构分歧。"),
            ("mechanism", "explanation", "避免误读的方法很简单，先对口径，再看精度，最后才比较结论。"),
            ("core_judgment", "interpretation", "所以核心判断是，小数位不同未必是矛盾，口径不同才需要真正警惕。"),
        ]
        sentences = [ScriptSentence(sentence_id=f"sentence_{n:03d}", section=section,
            sentence_type=kind, text=text, claim_ids=[claim.claim_id] if kind == "verified_fact" else [])
            for n, (section, kind, text) in enumerate(texts, 1)]
        return ScriptDraft(angle_id=request.selected_angle.angle_id, title=request.selected_angle.title, sentences=sentences)
