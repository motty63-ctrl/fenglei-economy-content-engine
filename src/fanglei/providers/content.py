"""Provider boundary, deterministic mock, and opt-in DeepSeek adapter."""
import json
import re
import urllib.request
from typing import Any, Callable, Protocol
from pydantic import BaseModel, Field
from fanglei.authority_safety import compact_authority_attribution
from fanglei.content_models import AngleCandidate, AngleProposal, AngleProposalResult, ScriptDraft, ScriptReadyClaim, ScriptSentence
from fanglei.content_style import FANGLEI_ECONOMY_STYLE_GUIDE
from fanglei.evidence_policy import is_claim_eligible_for_content
from fanglei.errors import ProviderError
from fanglei.security import REDACTED, safe_error_message
from fanglei.script_patch import ScriptPatchResult


class AngleGenerationInput(BaseModel):
    run_id: str
    core_topic: str
    research_questions: list[str]
    research_md: str
    fact_palette: tuple[ScriptReadyClaim, ...]
    research_focus: dict[str, Any] | None = None
    authority_metadata: dict[str, Any] = Field(default_factory=dict)


class ScriptGenerationInput(BaseModel):
    run_id: str
    selected_angle: AngleCandidate
    research_md: str
    fact_palette: tuple[ScriptReadyClaim, ...]
    research_focus: dict[str, Any] | None = None
    authority_metadata: dict[str, Any] = Field(default_factory=dict)


def _supporting_claims(
    selected_angle: AngleCandidate,
    fact_palette: tuple[ScriptReadyClaim, ...],
) -> tuple[ScriptReadyClaim, ...]:
    claim_by_id = {claim.claim_id: claim for claim in fact_palette}
    claim_ids = list(dict.fromkeys(selected_angle.supporting_claim_ids))
    if not claim_ids:
        raise ValueError("SCRIPT_ANGLE_HAS_NO_SUPPORTING_CLAIMS")
    missing = [claim_id for claim_id in claim_ids if claim_id not in claim_by_id]
    if missing:
        raise ValueError("SCRIPT_ANGLE_SUPPORTING_CLAIMS_UNAVAILABLE")
    selected = tuple(claim_by_id[claim_id] for claim_id in claim_ids)
    if any(not is_claim_eligible_for_content(claim) for claim in selected):
        raise ValueError("SCRIPT_ANGLE_SUPPORTING_CLAIM_INELIGIBLE")
    return selected


class RepairIssue(BaseModel):
    code: str
    sentence_id: str | None = None
    current_seconds: float | None = None
    min_seconds: float | None = None
    max_seconds: float | None = None
    target_seconds: float | None = None
    current_type: str | None = None
    expected_constraint: str | None = None
    trigger_category: str | None = None


class ScriptRepairInput(BaseModel):
    run_id: str
    repair_attempt: int
    selected_angle: AngleCandidate
    current_script: ScriptDraft
    editable_sentence_ids: list[str]
    protected_sentence_ids: list[str]
    allow_additions: bool = False
    fact_palette: tuple[ScriptReadyClaim, ...]
    issues: list[RepairIssue]


class ContentPlanningProvider(Protocol):
    name: str
    model: str | None
    angle_prompt_version: str
    script_prompt_version: str
    def generate_angles(self, request: AngleGenerationInput) -> AngleProposalResult: ...
    def generate_script(self, request: ScriptGenerationInput) -> ScriptDraft: ...
    def repair_script(self, request: ScriptRepairInput) -> ScriptPatchResult: ...


class DeepSeekContentPlanningProvider:
    name = "deepseek"
    endpoint = "https://api.deepseek.com/chat/completions"
    angle_prompt_version = "angles-deepseek-v1"
    script_prompt_version = "script-deepseek-v2"

    def __init__(self, api_key: str, *, model: str = "deepseek-v4-pro",
                 transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                 timeout_seconds: int = 60, angle_temperature: float = 0.6,
                 script_temperature: float = 0.2, repair_temperature: float = 0.0):
        if not api_key:
            raise ProviderError("DEEPSEEK_API_KEY is required")
        self._api_key = api_key
        self.model = model
        self._transport = transport or self._post
        self._timeout_seconds = timeout_seconds
        temperatures = (angle_temperature, script_temperature, repair_temperature)
        if any(value < 0 or value > 2 for value in temperatures):
            raise ProviderError("DeepSeek temperatures must be between 0 and 2")
        self.angle_temperature = angle_temperature
        self.script_temperature = script_temperature
        self.repair_temperature = repair_temperature

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("DeepSeek returned a non-object response")
        return result

    def _request_json(self, system_prompt: str, user_prompt: str, *, max_tokens: int,
                      temperature: float) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        try:
            response = self._transport(payload)
            content = response["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("DeepSeek returned empty content")
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("DeepSeek JSON content must be an object")
            return parsed
        except Exception as error:
            status = getattr(error, "code", None)
            error_type = type(error).__name__
            sanitized = safe_error_message(str(error).replace(self._api_key, REDACTED))
            raise ProviderError(
                f"DeepSeek API failed status={status if status is not None else 'unknown'} "
                f"type={error_type}: {sanitized}"
            ) from None

    @staticmethod
    def _fact_payload(palette: tuple[ScriptReadyClaim, ...]) -> list[dict[str, Any]]:
        claims = []
        for claim in palette:
            seen = set()
            evidence = []
            for item in claim.evidence:
                key = (item.get("document_hash"), item.get("json_pointer"), item.get("evidence_text"))
                if key in seen:
                    continue
                seen.add(key)
                evidence.append({name: item.get(name) for name in (
                    "source_id", "evidence_text", "observation", "value", "published_at",
                    "original_url", "document_hash", "json_pointer",
                ) if item.get(name) is not None})
            claims.append({
                "claim_id": claim.claim_id,
                "claim_text": claim.claim_text,
                "source_ids": claim.source_ids,
                "evidence": evidence,
                "verification_basis": claim.verification_basis,
                "authority_attestation": claim.authority_attestation,
            })
        return claims

    def smoke_test(self) -> dict[str, Any]:
        result = self._request_json(
            "Return only a JSON object. This is an authentication smoke test.",
            'Return JSON exactly in this shape: {"authenticated": true}.',
            max_tokens=64,
            temperature=0,
        )
        if result.get("authenticated") is not True:
            raise ProviderError("DeepSeek smoke test returned an unexpected JSON object")
        return result

    def generate_angles(self, request: AngleGenerationInput) -> AngleProposalResult:
        eligible_claims = tuple(
            claim for claim in request.fact_palette
            if is_claim_eligible_for_content(claim)
        )
        if not eligible_claims:
            raise ValueError("NO_ALLOWED_CLAIMS_FOR_ANGLE_PLANNING")
        facts = self._fact_payload(eligible_claims)
        system = (
            "你是风雷经济的内容策划。只允许使用输入 JSON 中的 verified claims，不得创造数字、日期、机构结论或政策事实。"
            "生成 JSON，不要输出 Markdown。候选角度必须真正不同；叙事框架应由输入证据自然决定，不要求固定主题集合。"
            "Hook 不得制造假冲突。"
            "所有评分字段必须使用0到5的整数，5为最高，不得使用10分制。"
            "如claim的verification_basis为authoritative_primary_attestation，必须在角度文案中保留机构/文件归因和attestation中的"
            "指标、期间、统计口径、单位与预测属性；不得把projection写成承诺，也不得添加未被原文直接支持的因果、动机或市场影响。"
        )
        user = json.dumps({
            "task": "生成3到5个中文经济短视频候选角度 JSON",
            "topic": request.core_topic,
            "research_questions": request.research_questions,
            "research_focus": request.research_focus,
            "authority_metadata": request.authority_metadata,
            "verified_claims_only": facts,
            "output_schema": {
                "candidates": [{
                    "angle_id": "angle_001", "title": "", "hook": "", "core_question": "",
                    "core_insight": "", "hook_mechanism": "", "audience_takeaway": "",
                    "narrative_framing": "misconception_correction",
                    "supporting_claim_ids": ["claim_id"], "audience_relevance": 0,
                    "novelty": 0, "hook_strength": 0, "visual_potential": 0,
                    "explainability": 0, "risk_notes": [],
                }]
            },
        }, ensure_ascii=False)
        raw = self._request_json(system, user, max_tokens=2200, temperature=self.angle_temperature)
        score_fields = ("audience_relevance", "novelty", "hook_strength", "visual_potential", "explainability")
        rows = raw.get("candidates", [])
        if isinstance(rows, list) and any(
            isinstance(row, dict) and any(isinstance(row.get(field), (int, float)) and row[field] > 5
                                          for field in score_fields)
            for row in rows
        ):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for field in score_fields:
                    value = row.get(field)
                    if isinstance(value, (int, float)) and 0 <= value <= 10:
                        row[field] = min(5, int(value / 2 + 0.5))
        return AngleProposalResult.model_validate(raw)

    def generate_script(self, request: ScriptGenerationInput) -> ScriptDraft:
        supporting_claims = _supporting_claims(request.selected_angle, request.fact_palette)
        facts = self._fact_payload(supporting_claims)
        system = (
            "你是风雷经济的中文短视频编剧。把 selected_angle 作为叙事切入点，并使用 Research / Research Focus"
            "组织表达。事实 whitelist 是 selected_angle.supporting_claim_ids 对应的 verified_claims_only；"
            "Research 只能用于理解问题与结构，不能作为新增事实来源。不得创造输入没有提供的数字、日期、机构行为、"
            "数据口径、历史事件或因果事实。任何可外部验证的句子都必须绑定直接支持它的 claim_ids；"
            "没有 claim 支持时，只能写非事实性的表达或建议。输出符合 output_contract 的 JSON，不要 Markdown。"
            "每条绑定 claim_ids 的句子只能忠实表达该 claim 与对应 evidence；数字、对象、时间、单位、统计口径、"
            "certainty、attribution 和 authority scope 均不得扩大或省略。对权威文件 attestation 必须保留文件归因；"
            "projection 不得改写为承诺、政策决定或现实结果。不得添加输入未支持的 causality、motive 或 market effect。"
            "只在输入 claim 直接支持时解释机制；否则呈现证据边界，不要编造机制。不要把同时发生的变化写成因果关系。"
            "脚本目标60到90秒，总口播字符控制在240到360个；第一句 hook 最多20个口播字符。"
            "输出12到15句，每句推动当前问题向答案前进；事实句必须绑定支持它的 claim_ids，纯观点或比喻不得绑定 claim。"
            "凡 hook 含有可核验的数字、日期、机构行为或具体事实，也必须绑定相应 claim 并标为 verified_fact。"
            "section 只能使用 hook、phenomenon、mechanism、core_judgment，最后一句必须是 core_judgment。"
            "sentence_type 只能使用 verified_fact、explanation、interpretation、analogy。"
            "凡是包含“打个比方、好比、就像、仿佛、这像”的句子，sentence_type 必须是 analogy。"
            + FANGLEI_ECONOMY_STYLE_GUIDE
            + "机制与因果说明必须有 supporting claim 直接支持；风格要求不能覆盖此事实边界。"
        )
        user = json.dumps({
            "task": "根据本次 run 的 Research、选定角度和 supporting facts 生成中文短视频脚本",
            "run_id": request.run_id,
            "research_summary": request.research_md,
            "research_focus": request.research_focus,
            "authority_metadata": request.authority_metadata,
            "selected_angle": request.selected_angle.model_dump(mode="json"),
            "selected_supporting_claim_ids": request.selected_angle.supporting_claim_ids,
            "verified_claims_only": facts,
            "narrative_guidance": [
                "从 hook 引出 selected_angle 的问题",
                "呈现 supporting claims 直接支持的事实",
                "只解释证据支持的背景；否则清楚保留 scope boundary",
                "以不超出 evidence 的结论收尾",
            ],
            "output_contract": {
                "schema_version": "3.0",
                "target_duration_seconds": 75,
                "minimum_sentence_count": 12,
                "maximum_sentence_count": 15,
                "minimum_spoken_character_count": 240,
                "maximum_spoken_character_count": 360,
                "allowed_sections": ["hook", "phenomenon", "mechanism", "core_judgment"],
                "allowed_sentence_types": ["verified_fact", "explanation", "interpretation", "analogy"],
            },
            "output_schema": {
                "angle_id": request.selected_angle.angle_id,
                "title": request.selected_angle.title,
                "target_duration_seconds": 75,
                "sentences": [{
                    "sentence_id": "sentence_001", "section": "hook",
                    "sentence_type": "interpretation", "text": "", "claim_ids": [],
                }],
            },
        }, ensure_ascii=False)
        raw = self._request_json(system, user, max_tokens=2600, temperature=self.script_temperature)
        return self._normalize_script(raw)

    @staticmethod
    def _normalize_script(raw: dict[str, Any]) -> ScriptDraft:
        for sentence in raw.get("sentences", []):
            if isinstance(sentence, dict) and sentence.get("section") == "core_insight":
                sentence["section"] = "core_judgment"
            if isinstance(sentence, dict) and sentence.get("sentence_type") == "core_judgment":
                sentence["sentence_type"] = "interpretation"
            if isinstance(sentence, dict) and sentence.get("sentence_type") != "verified_fact":
                sentence["claim_ids"] = []
        return ScriptDraft.model_validate(raw)

    def repair_script(self, request: ScriptRepairInput) -> ScriptPatchResult:
        system = (
            "你只生成风雷经济脚本的 sentence-level patches，不得返回、重写或覆盖整篇 script。"
            "本地 lint 和 patch applier 是最终裁判。只能修改 editable_sentence_ids；protected_sentence_ids 禁止修改。"
            "不得修改 claim 状态、claim_ids、已通过的 verified_fact，也不得靠改变 sentence_type 绕过事实检查。"
            "verified_claims_only 仅包含 selected_angle.supporting_claim_ids 对应的事实；不得使用其他记忆或补充事实。"
            "保持选定角度的主题、对象、范围和来源归因，不引入当前输入未提供的案例、机构或指标。"
            "不得新增数字、日期、机构结论、数据口径、历史事件或因果事实。只修 structured_issues 指向的问题，"
            "保持其他内容不变，不重新设计 selected_angle。输出纯 JSON，顶层只能是 patches。"
            "遇到 DURATION_TOO_SHORT 时，必须按缺口一次提交足够数量、文本互不重复的 add_after patches，"
            "使完整脚本至少达到240个口播字符；不得靠重复句凑时长。"
            "replace patch 使用 sentence_id、operation=replace、new_text；只有 SENTENCE_TYPE_MISMATCH 或"
            " ANALOGY_OVERUSE 明确授权时"
            "才可附 new_sentence_type。add_after 仅在 allow_additions=true 时使用，并必须附 new_sentence_id、"
            "new_sentence_type=explanation或interpretation、new_section=mechanism。不得在 patch 中发送 claim_ids。"
            + FANGLEI_ECONOMY_STYLE_GUIDE
        )
        issue_rules = {
            "HOOK_INVALID": "hook需为12到18个口播字符，且不含阿拉伯数字、年份、机构名或确定事实。",
            "DURATION_OUT_OF_RANGE": "只对授权句提交局部patch，使修订后完整脚本回到60到90秒。",
            "DURATION_TOO_SHORT": (
                "必须提交至少一个add_after patch，在授权的explanation或interpretation句后新增一条mechanism句；"
                "新增句只写建议、提问或主观理解，不得出现统计、误差、原始数据、精度、机构、数字或因果结论。"
                "每条新增句必须与 existing_sentence_texts 中所有句子实质不同。"
                "不得修改verified_fact、已通过的hook或结论，不得重复事实或建议凑时长。"
            ),
            "DURATION_TOO_LONG": (
                "只压缩授权的explanation或analogy句；不得删除核心verified_fact，"
                "不得修改已通过的hook或结论，也不得破坏现象、机制、判断结构。"
            ),
            "COMPLEX_LONG_SENTENCE": "每句不超过48个口播字符，逗号、分号和冒号合计不超过3个。",
            "UNSUPPORTED_FACT": "仅保留一条忠实翻译claim_text的verified_fact并绑定对应claim_id，不扩写；其他句子不绑定claim。",
            "UNDECLARED_FACT": "存在未绑定claim的外部事实；删除、改成明确提问/建议/类比/主观判断，或绑定真正支持它的claim。",
            "REPEATED_SENTENCE": (
                "只等长替换授权的重复句；不得删除句子或只改标点，也不要用同一句结论凑长度。"
                "若改写后包含‘打个比方、好比、就像、仿佛、这像’，sentence_type必须同时设为analogy。"
            ),
            "SENTENCE_TYPE_MISMATCH": "含明确比喻标记的句子必须标为analogy；不得靠改类型掩盖事实断言。",
            "CORE_JUDGMENT_MISSING": (
                "最后一句section必须是core_judgment，并用不含新事实的清晰陈述句收束；"
                "回到选定角度的问题，并保留输入证据所限定的结论范围。"
            ),
            "CORE_JUDGMENT_WEAK": (
                "最后一句必须是清晰陈述句，不能是问句；请回到选定角度的问题收束，"
                "不要补入输入没有支持的新事实或结论。"
            ),
            "FORMULAIC_REPETITION": "同一种话语开头最多使用两次；改写成自然口语，避免连续使用‘你可以/你不妨/我的判断是’。",
            "REPORT_STYLE_LANGUAGE": "删掉报告式套话，直接进入问题或答案；不得新增事实。",
            "ANALOGY_OVERUSE": "去掉该句的比喻表达并改为自然 explanation；全篇最多保留1个主要比喻。",
            "STYLE_TEMPLATE_OVERUSE": "去掉‘我的判断是’或‘你不妨想想’等模板前缀，保留句子原本推进作用。",
            "SEMANTIC_FACTUALITY_UNSUPPORTED": (
                "逐句检查所有claim_ids为空的句子并消除五类可核查断言："
                "numeric_or_date（阿拉伯数字或年份）；institution_action（机构显示、公布、发布、宣布、认为、预计或报告）；"
                "data_methodology（数据口径、统计口径、计算口径、季调、修订、基期、样本范围、四舍五入、保留小数、原始值、显示精度）；"
                "causal_fact（导致、造成、源于、归因于、因为所以、使得）；"
                "usual_behavior（通常、往往、一般会、经常、倾向于、习惯于、方便传播或计算）。"
                "把这些句子改成明确提问、第二人称核对建议、以‘打个比方/就像’开头的类比，或以‘我的判断是’开头的观点。"
            ),
        }
        current_rules = []
        safe_methodology_replacements = (
            "先把问题说清楚，再比较对应材料。",
            "比较之前，先确认讨论对象和范围。",
            "先看材料直接记录了什么，再谈理解。",
            "遇到不同说法时，可以先回到各自出处。",
            "先区分原文记录与自己的理解。",
            "先把看到的写法和自己的理解分开。",
            "把问题拆开，再一项一项核对。",
            "可以把这次比较当成一次阅读检查。",
            "别急着解释差别，先确认双方说的是同一件事。",
            "先看记录本身，再说明它能回答什么。",
            "阅读相关材料时，给自己留一个核对步骤。",
            "先判断问题出在内容，还是表达方式。",
            "把比较步骤放慢一点，再说出自己的理解。",
            "先追到出处，再回头理解简短说法。",
            "不要只看结论，也要看它回答了什么问题。",
            "先把现象和解释分开，再决定如何表述。",
            "先确认输入信息是否足以支持这个说法。",
        )
        for issue in request.issues:
            code = issue.code
            locator = issue.sentence_id or ""
            if code in issue_rules:
                rule = issue_rules[code]
                current_rules.append(rule + (f" 请修订 {locator}。" if locator else ""))
            elif code == "CLAIM_BINDING_MISSING":
                signal = issue.trigger_category or "external_fact"
                suffix = f" 本次触发类别仅为：{signal}。"
                if locator:
                    suffix += f" 请修订 {locator}。"
                if signal == "numeric_or_date" and locator.lower() in {"sentence_001", "s1"}:
                    suffix += " 请把hook改为不含数字与机构名的问句，例如：‘新闻里的数字，藏着什么？’"
                elif signal == "numeric_or_date" and locator:
                    suffix += (
                        " 该句只有两种合法修法：若它忠实翻译verified_claims_only中的claim_text，"
                        "则设为verified_fact并绑定对应claim_id；否则删掉全部阿拉伯数字、年份、百分比和机构名，"
                        "改成例如‘你可以先问，眼前的差别会不会只是写法不同？’。"
                    )
                elif signal == "data_methodology" and locator:
                    number = re.search(r"(\d+)$", locator)
                    replacement_index = int(number.group(1)) - 1 if number else sum(map(ord, locator))
                    replacement = safe_methodology_replacements[replacement_index % len(safe_methodology_replacements)]
                    suffix += (
                        " 必须整句替换，不得只改sentence_type，也不得保留数据口径、统计口径、计算口径、季调、修订、"
                        "基期、样本范围、四舍五入、保留小数、原始数据、原始值或显示精度等断言。"
                        f"可直接改为：‘{replacement}’"
                    )
                elif signal == "causal_fact" and locator:
                    suffix += (
                        " 必须删除无claim支持的因果判断。可直接改为不含外部事实的建议："
                        "‘你可以把观察到的内容与可能的解释分开。’"
                    )
                current_rules.append(issue_rules["SEMANTIC_FACTUALITY_UNSUPPORTED"] + suffix)
        current_spoken_character_count = len(re.findall(
            r"[\u4e00-\u9fffA-Za-z0-9]",
            "".join(sentence.text for sentence in request.current_script.sentences),
        ))
        editable = set(request.editable_sentence_ids)
        editable_sentences = [
            sentence.model_dump(mode="json")
            for sentence in request.current_script.sentences
            if sentence.sentence_id in editable
        ]
        user = json.dumps({
            "task": "仅返回 lint 授权范围内的 sentence-level patches",
            "repair_attempt": request.repair_attempt,
            "current_spoken_character_count": current_spoken_character_count,
            "existing_sentence_texts": [sentence.text for sentence in request.current_script.sentences],
            "valid_duration_character_range": {"min": 240, "max": 360, "target": 300},
            "structured_issues": [issue.model_dump(mode="json", exclude_none=True) for issue in request.issues],
            "rules_for_current_issue_codes": current_rules,
            "selected_angle": request.selected_angle.model_dump(mode="json"),
            "editable_sentence_ids": request.editable_sentence_ids,
            "editable_sentences": editable_sentences,
            "protected_sentence_ids": request.protected_sentence_ids,
            "allow_additions": request.allow_additions,
            "verified_claims_only": self._fact_payload(_supporting_claims(
                request.selected_angle, request.fact_palette)),
            "patch_contract": {
                "operations": ["replace", "add_after"],
                "replace_fields": ["sentence_id", "operation", "new_text", "new_sentence_type(optional)"],
                "add_after_fields": ["sentence_id", "operation", "new_sentence_id", "new_text",
                                     "new_sentence_type", "new_section"],
            },
        }, ensure_ascii=False)
        raw = self._request_json(system, user, max_tokens=1800, temperature=self.repair_temperature)
        for patch in raw.get("patches", []):
            if not isinstance(patch, dict):
                continue
            if (patch.get("operation") == "replace"
                    and patch.get("new_sentence_type") in {"hook", "phenomenon", "mechanism", "core_judgment"}):
                patch.pop("new_sentence_type")
            if (patch.get("operation") == "add_after"
                    and patch.get("new_sentence_type") == "mechanism"):
                patch["new_sentence_type"] = "explanation"
                patch.setdefault("new_section", "mechanism")
        return ScriptPatchResult.model_validate(raw)


class MockContentPlanningProvider:
    name = "mock-content"
    model = None
    angle_prompt_version = "offline-generic-angles-v1"
    script_prompt_version = "offline-evidence-script-v3"

    def generate_angles(self, request: AngleGenerationInput) -> AngleProposalResult:
        from fanglei.offline_angle_planner import plan_offline_angles

        return plan_offline_angles(request)

    @staticmethod
    def _spoken_count(text: str) -> int:
        return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))

    @staticmethod
    def _authority_scope_term(value: str) -> str:
        labels = {
            "projection": "预测",
            "assessment": "评估",
            "measurement": "测量",
            "report": "记录",
        }
        return labels.get(value.casefold(), value)

    @staticmethod
    def _legacy_fed_v01_subject_label(subject: str) -> str:
        """Retain compact labels for historical Fed V0.1 fixture comparisons only."""
        labels = {
            "change in real gdp": "实际GDP增速",
            "unemployment rate": "失业率",
            "pce inflation": "PCE通胀",
            "core pce inflation": "核心PCE通胀",
            "federal funds rate": "联邦基金利率",
        }
        return labels.get(subject.casefold(), subject)

    @staticmethod
    def _approved_source_ids(request: ScriptGenerationInput) -> set[str]:
        policy = request.authority_metadata.get("source_policy")
        if not isinstance(policy, dict) or policy.get("name") != "authoritative_primary_set":
            raise ValueError("AUTHORITY_SCRIPT_REQUIRES_APPROVED_SOURCE_POLICY")
        approval = policy.get("approval")
        documents = policy.get("approved_documents")
        if (not isinstance(approval, dict) or approval.get("status") != "approved"
                or request.authority_metadata.get("package_admissibility") != "admissible"
                or not isinstance(documents, list)):
            raise ValueError("AUTHORITY_SCRIPT_REQUIRES_ADMISSIBLE_APPROVED_PACKAGE")
        return {row["source_id"] for row in documents
                if isinstance(row, dict) and isinstance(row.get("source_id"), str)}

    @staticmethod
    def _source_attribution(claim: ScriptReadyClaim) -> str:
        attestation = claim.authority_attestation or {}
        attribution = attestation.get("attribution")
        if not isinstance(attribution, str) or not attribution.strip():
            raise ValueError("AUTHORITY_CLAIM_ATTRIBUTION_MISSING")
        return compact_authority_attribution(attribution)

    @classmethod
    def _comparison_sentence(cls, claim: ScriptReadyClaim) -> str:
        attestation = claim.authority_attestation or {}
        scope = attestation.get("scope")
        if attestation.get("kind") != "deterministic_document_comparison" or not isinstance(scope, dict):
            raise ValueError("AUTHORITY_COMPARISON_SCOPE_MISSING")
        attribution = cls._source_attribution(claim)
        required = ("subject", "period", "unit", "statistic", "certainty")
        if any(not isinstance(scope.get(key), str) or not scope[key].strip() for key in required):
            raise ValueError("AUTHORITY_COMPARISON_SCOPE_INCOMPLETE")
        source_ids = set(attestation.get("source_ids", []))
        if source_ids != set(claim.source_ids) or len(source_ids) != 2:
            raise ValueError("AUTHORITY_COMPARISON_SOURCE_IDENTITY_MISMATCH")
        evidence = [item for item in claim.evidence
                    if item.get("source_id") in source_ids and item.get("evidence_eligible") is True
                    and isinstance(item.get("original_url"), str)
                    and isinstance(item.get("published_at"), str)
                    and isinstance(item.get("evidence_text"), str)]
        if len(evidence) != 2 or {item["source_id"] for item in evidence} != source_ids:
            raise ValueError("AUTHORITY_COMPARISON_EVIDENCE_INCOMPLETE")
        evidence.sort(key=lambda item: (item["published_at"], item["source_id"]))
        months_and_values = []
        for item in evidence:
            date_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", item["published_at"])
            values = re.findall(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?(?![\w.])", item["evidence_text"])
            if not date_match or not values or not 1 <= int(date_match.group(2)) <= 12:
                raise ValueError("AUTHORITY_COMPARISON_DATE_OR_VALUE_MISSING")
            months_and_values.append((int(date_match.group(2)), values[-1].replace(",", "")))
        if months_and_values[0][0] == months_and_values[1][0]:
            raise ValueError("AUTHORITY_COMPARISON_RELEASE_MONTHS_NOT_DISTINCT")
        period = scope["period"]
        if re.fullmatch(r"\d{4}", period):
            period = period + "年"
        statistic = "中位数" if scope["statistic"].casefold() == "median" else scope["statistic"]
        unit = "%" if scope["unit"].casefold() in {"percent", "%"} else scope["unit"]
        subject = cls._legacy_fed_v01_subject_label(str(scope.get("subject", "")).strip())
        scope_terms = list(dict.fromkeys(
            cls._authority_scope_term(scope[key]) for key in ("measure", "certainty")
        ))
        scope_label = "".join(scope_terms)
        months = ("一月", "二月", "三月", "四月", "五月", "六月",
                  "七月", "八月", "九月", "十月", "十一月", "十二月")
        first_month = months[months_and_values[0][0] - 1]
        second_month = months[months_and_values[1][0] - 1]
        text = (
            f"{attribution.strip()}：{period}{subject}{statistic}{scope_label}记录变化，"
            f"从{first_month}{months_and_values[0][1]}{unit}到"
            f"{second_month}{months_and_values[1][1]}{unit}。"
        )
        if cls._spoken_count(text) > 48:
            raise ValueError("AUTHORITY_COMPARISON_EXCEEDS_SCRIPT_SENTENCE_LIMIT")
        return text

    @classmethod
    def _document_attribution(cls, claim: ScriptReadyClaim) -> str:
        attestation = claim.authority_attestation or {}
        if attestation.get("kind") != "document_report":
            raise ValueError("AUTHORITY_DOCUMENT_REPORT_REQUIRED")
        return cls._source_attribution(claim)

    @classmethod
    def _research_document_claim(cls, request: ScriptGenerationInput,
                                 approved_source_ids: set[str]) -> tuple[ScriptReadyClaim, str] | None:
        cited_ids = set(re.findall(r"\bclaim_[A-Za-z0-9_-]+\b", request.research_md))
        candidates = []
        for claim in request.fact_palette:
            attestation = claim.authority_attestation or {}
            if (claim.claim_id not in cited_ids or attestation.get("kind") != "document_report"
                    or set(claim.source_ids) != set(attestation.get("source_ids", []))
                    or not set(claim.source_ids) <= approved_source_ids):
                continue
            evidence = [item for item in claim.evidence
                        if item.get("source_id") in claim.source_ids
                        and item.get("evidence_eligible") is True
                        and isinstance(item.get("original_url"), str)
                        and isinstance(item.get("evidence_text"), str)
                        and item["evidence_text"].strip()
                        and "\n" not in item["evidence_text"].strip()]
            for item in evidence:
                sentence = f"{cls._document_attribution(claim)}: ‘{item['evidence_text'].strip()}’"
                if cls._spoken_count(sentence) <= 48:
                    candidates.append((cls._spoken_count(sentence), claim.claim_id, claim, sentence))
        if not candidates:
            return None
        _, _, claim, sentence = min(candidates, key=lambda item: (item[0], item[1]))
        return claim, sentence

    @classmethod
    def _generate_authority_script(cls, request: ScriptGenerationInput) -> ScriptDraft | None:
        palette = {claim.claim_id: claim for claim in request.fact_palette}
        selected = [palette[claim_id] for claim_id in request.selected_angle.supporting_claim_ids
                    if claim_id in palette]
        comparisons = [claim for claim in selected
                       if (claim.authority_attestation or {}).get("kind")
                       == "deterministic_document_comparison"]
        if not comparisons:
            return None
        approved_source_ids = cls._approved_source_ids(request)
        if any(not set(claim.source_ids) <= approved_source_ids for claim in comparisons):
            raise ValueError("AUTHORITY_COMPARISON_OUTSIDE_APPROVED_PACKAGE")

        hook = request.selected_angle.hook.strip()
        if cls._spoken_count(hook) > 20:
            hook = re.split(r"[，,；;。]", hook, maxsplit=1)[0].strip("？? ") + "？"
        if cls._spoken_count(hook) > 20:
            hook = "这些记录能回答什么？"
        rows: list[tuple[str, str, str, list[str]]] = [
            ("hook", "interpretation", hook, []),
            ("phenomenon", "explanation", "先按各自文件记录的时间和口径逐项比较。", []),
        ]
        for index, claim in enumerate(comparisons):
            section = "phenomenon" if index < 2 else "mechanism"
            rows.append((section, "verified_fact",
                         cls._comparison_sentence(claim), [claim.claim_id]))
        rows.extend([
            ("mechanism", "explanation", "每项比较只描述所引文件中的记录差异。", []),
        ])
        document_claim = cls._research_document_claim(request, approved_source_ids)
        if document_claim:
            claim, text = document_claim
            rows.append(("mechanism", "verified_fact", text, [claim.claim_id]))
        rows.extend([
            ("mechanism", "interpretation", "并列呈现不代表文件之间存在因果关系。", []),
            ("core_judgment", "interpretation", "结论仅限于获批文件及对应证据。", []),
        ])
        sentences = [ScriptSentence(sentence_id=f"sentence_{index:03d}", section=section,
                                    sentence_type=kind, text=text, claim_ids=claim_ids)
                     for index, (section, kind, text, claim_ids) in enumerate(rows, start=1)]
        return ScriptDraft(angle_id=request.selected_angle.angle_id,
                           title=request.selected_angle.title, sentences=sentences)

    def generate_script(self, request: ScriptGenerationInput) -> ScriptDraft:
        supporting_claims = _supporting_claims(request.selected_angle, request.fact_palette)
        authority_draft = self._generate_authority_script(request)
        if authority_draft is not None:
            return authority_draft
        def claim_text(claim: ScriptReadyClaim) -> str:
            text = claim.claim_text.strip()
            attestation = claim.authority_attestation or {}
            attribution = attestation.get("attribution")
            if (claim.verification_basis == "authoritative_primary_attestation"
                    and isinstance(attribution, str) and attribution.strip()
                    and attribution.casefold() not in text.casefold()):
                text = f"{compact_authority_attribution(attribution)}：{text}"
            return text

        rows: list[tuple[str, str, str, list[str]]] = [
            ("hook", "interpretation", request.selected_angle.hook.strip(), []),
        ]
        rows.extend(("phenomenon", "verified_fact", claim_text(claim), [claim.claim_id])
                    for claim in supporting_claims)
        framing = [
            ("phenomenon", "explanation", "本条围绕已选角度提出的问题展开，表达范围也由这一问题限定。"),
            ("phenomenon", "explanation", "事实部分只使用随请求提供的已核验内容，不从其他内容补充数字。"),
            ("mechanism", "explanation", "每个事实句都对应随请求传入的 claim 编号。"),
            ("mechanism", "explanation", "引用事实时保留 claim 已记录的来源归因和适用范围。"),
            ("mechanism", "explanation", "没有证据支持的数字不会补入脚本。"),
            ("mechanism", "interpretation", "材料没有直接说明的原因，不改写为因果结论。"),
            ("mechanism", "interpretation", "同时出现的记录可以并列展示，但不据此推断彼此原因。"),
            ("mechanism", "explanation", "未列入所选角度的事实，不作为本条事实句。"),
            ("mechanism", "explanation", "观众可以根据对应 claim 编号回查证据与来源。"),
            ("mechanism", "interpretation", "表达内容不超出事实及来源直接支持的范围。"),
        ]
        needed = max(0, 12 - len(rows) - 1)
        rows.extend((section, kind, text, []) for section, kind, text in framing[:needed])
        rows.append(("core_judgment", "interpretation",
                     "结论：本条表达范围不超过已核验事实所能支持的内容。", []))
        sentences = [ScriptSentence(sentence_id=f"sentence_{index:03d}", section=section,
                                    sentence_type=kind, text=text, claim_ids=claim_ids)
                     for index, (section, kind, text, claim_ids) in enumerate(rows, start=1)]
        return ScriptDraft(angle_id=request.selected_angle.angle_id, title=request.selected_angle.title, sentences=sentences)

    def repair_script(self, request: ScriptRepairInput) -> ScriptPatchResult:
        return ScriptPatchResult(patches=[])
