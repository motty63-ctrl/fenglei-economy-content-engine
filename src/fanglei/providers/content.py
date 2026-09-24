"""Provider boundary, deterministic mock, and opt-in DeepSeek adapter."""
import json
import re
import urllib.request
from typing import Any, Callable, Protocol
from pydantic import BaseModel
from fanglei.content_models import AngleCandidate, AngleProposal, AngleProposalResult, ScriptDraft, ScriptReadyClaim, ScriptSentence
from fanglei.content_style import FANGLEI_ECONOMY_STYLE_GUIDE
from fanglei.errors import ProviderError
from fanglei.security import REDACTED, safe_error_message
from fanglei.script_patch import ScriptPatchResult


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
    script_prompt_version = "script-deepseek-v1"

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
        facts = self._fact_payload(request.fact_palette)
        system = (
            "你是风雷经济的内容策划。只允许使用输入 JSON 中的 verified claims，不得创造数字、日期、机构结论或政策事实。"
            "生成 JSON，不要输出 Markdown。候选角度必须真正不同，并覆盖 misconception_correction、"
            "economic_data_literacy、media_literacy 三种 narrative_framing。Hook 不得制造假冲突。"
            "所有评分字段必须使用0到5的整数，5为最高，不得使用10分制。"
            "如claim的verification_basis为authoritative_primary_attestation，必须在角度文案中保留机构/文件归因和attestation中的"
            "指标、期间、统计口径、单位与预测属性；不得把projection写成承诺，也不得添加未被原文直接支持的因果、动机或市场影响。"
        )
        user = json.dumps({
            "task": "生成3到5个中文经济短视频候选角度 JSON",
            "topic": request.core_topic,
            "research_questions": request.research_questions,
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
        facts = self._fact_payload(request.fact_palette)
        system = (
            "你是风雷经济的中文短视频编剧。只消费输入 JSON 中的 verified claims。不得创造数字、日期、机构行为、"
            "数据口径、历史事件或因果事实。任何可外部验证的句子都必须绑定支持它的 claim_ids，即使 sentence_type 写成"
            " explanation 或 interpretation。没有 claim 支持时，只能写成明确的个人判断或比喻。输出纯 JSON，不要 Markdown。"
            "脚本目标60到90秒，总口播字符严格控制在260到310个，必须先自行核对字数；第一句 hook 最多20个口播字符。"
            "按现象、机制、核心判断推进，语言口语化。不要把 selected_angle 中未经 verified claims 支持的内容当作事实。"
            "绑定 claim_ids 的句子只能陈述该 claim 及 evidence 明确包含的数字、机构和指标；不要给纯观点或比喻绑定 claim。"
            "对authoritative_primary_attestation，必须保留claim的机构/文件归因、attestation scope和certainty；projection不能改写成承诺或政策决定。"
            "不得添加原文未直接支持的因果、动机或市场影响；document_report必须保留来源归因并逐字保留被引用的attested evidence。"
            "请输出12到15句，每句推动当前问题向答案前进。事实句可有多句，但每句都必须忠实复述对应 claim 或 evidence，"
            "并绑定支持它的 claim_ids。API observation 后不要擅自添加百分号，必须按 evidence 中的原始值表达。"
            "若 hook 包含已验证数字或机构名，hook 本身也必须标为 verified_fact 并绑定 claim。"
            "对 angle_001，叙事只围绕同一 GDP 数值的两种精度写法：先呈现 BEA 的2.8%与 World Bank API 的"
            "2.79318715363841（不加百分号），再写‘2.79318715363841四舍五入到一位小数，就是GDP增长率2.8%’，"
            "最后教观众先核对来源、指标、"
            "年份和精度。四舍五入机制句也必须绑定支持它的 claim_id，并标为 verified_fact。"
            "不要引入政策沟通需求、媒体行为、统计误差或任何 claims 未支持的原因。"
            "section 只能使用 hook、phenomenon、mechanism、core_judgment，最后一句必须是 core_judgment。"
            "sentence_type 只能使用 verified_fact、explanation、interpretation、analogy。"
            "凡是包含“打个比方、好比、就像、仿佛、这像”的句子，sentence_type 必须是 analogy。"
            + FANGLEI_ECONOMY_STYLE_GUIDE
        )
        user = json.dumps({
            "task": "生成约300个中文口播字符的结构化脚本 JSON",
            "selected_angle": request.selected_angle.model_dump(mode="json"),
            "verified_claims_only": facts,
            "minimum_sentence_count": 12,
            "minimum_spoken_character_count": 240,
            "required_narrative_beats": [
                "hook：原样使用‘同一个美国GDP，怎么会有两种答案？’，不含数字与机构名",
                "phenomenon：BEA的2024年美国实际GDP增长率2.8%，绑定claim",
                "phenomenon：World Bank API原始观察值2.79318715363841，不加百分号，绑定claim",
                "mechanism：原样使用‘2.79318715363841四舍五入到一位小数，就是GDP增长率2.8%。’，绑定claim",
                "explanation：直接点明算完这一步，表面反差已经消失",
                "interpretation：不要把小数位差别直接理解成机构争论",
                "explanation：把本题答案收束为同一数值的不同精度展示",
                "advice：以后比较经济数据，第一步先看来源",
                "advice：第二步确认指标名称是否相同",
                "advice：第三步确认年份是否相同",
                "advice：第四步检查数值精度",
                "interpretation：完成核对后再判断差异是否真实",
                "core_judgment：用来源、指标、年份、精度这一可复用方法收尾",
            ],
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
                "最后一句section必须是core_judgment，并用不含新事实的明确主观判断收束。"
                "可直接使用：‘所以，理解数据的精度，比记住一个数字更重要。’"
            ),
            "CORE_JUDGMENT_WEAK": (
                "最后一句必须是明确陈述句，不能是问句。请把该句精确替换为："
                "‘所以，理解数据的精度，比记住一个数字更重要。’"
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
            "读到两种写法，先别急着判断谁对谁错。",
            "比较之前，先把指标名称和年份放在一起。",
            "真正要问的，是两种写法传达的方向是否一致。",
            "看经济新闻时，多追问一句来源在哪里。",
            "先确认讨论的是不是同一个指标，再理解差别。",
            "先把看到的写法和自己的理解分开。",
            "不妨先列出疑问，再一项一项核对。",
            "可以把这次比较当成一次阅读检查。",
            "别急着解释差别，先确认双方说的是同一件事。",
            "先看结论方向，再决定细节是否值得深究。",
            "遇到相近写法时，先问它们能不能直接比较。",
            "把比较步骤放慢一点，再说出自己的理解。",
            "先追到出处，再回头理解新闻里的简短说法。",
            "阅读这类数字时，给自己留一个核对步骤。",
            "先判断问题出在内容，还是出在表达方式。",
            "不要只看末尾差别，也要看它回答了什么问题。",
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
                        "‘你不妨把注意力放在趋势上，不必只盯着末尾几位。’"
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
            "verified_claims_only": self._fact_payload(request.fact_palette),
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
    angle_prompt_version = "angles-v1"
    script_prompt_version = "script-v1"

    @staticmethod
    def _spoken_fact(claim_text: str) -> str:
        match = re.search(
            r"United States real GDP grew\s+(\d+(?:\.\d+)?)%\s+in\s+((?:19|20)\d{2})",
            claim_text,
            re.I,
        )
        if match:
            value, year = match.groups()
            return f"美国{year}年实际GDP增长{value}%。"
        return claim_text

    def generate_angles(self, request: AngleGenerationInput) -> AngleProposalResult:
        claim_id = request.fact_palette[0].claim_id
        rows = [
            ("angle_001", "小数点后，藏着一个假问题", "两个权威数字差一点，问题可能不在经济本身。", "显示精度不同，不等于结论冲突", "number_gap_suspense", "看懂数字不同未必代表结论冲突", "misconception_correction"),
            ("angle_002", "数字越长，就一定越准吗", "更多小数位带来的是信息，还是错觉？", "公开传播和研究计算需要不同精度", "precision_question", "理解统计值的原始精度和展示精度", "economic_data_literacy"),
            ("angle_003", "看GDP，先别急着比小数", "读经济数据，第一步为什么不是比较大小？", "先核对指标、时期和精度，再解释经济含义", "reader_checklist", "学会核对媒体中的指标口径和来源", "media_literacy"),
        ]
        return AngleProposalResult(candidates=[AngleProposal(
            angle_id=i, title=t, hook=h, core_question=h, core_insight=insight,
            hook_mechanism=mechanism, audience_takeaway=takeaway, narrative_framing=framing,
            supporting_claim_ids=[claim_id], audience_relevance=5, novelty=4,
            hook_strength=4, visual_potential=3, explainability=5,
        ) for i, t, h, insight, mechanism, takeaway, framing in rows])

    def generate_script(self, request: ScriptGenerationInput) -> ScriptDraft:
        claim = request.fact_palette[0]
        texts = [
            ("hook", "interpretation", "同一个增长率，为什么会出现两种写法？"),
            ("phenomenon", "verified_fact", self._spoken_fact(claim.claim_text)),
            ("mechanism", "explanation", "先别急着判断谁对谁错，第一步是把指标、年份和计算范围对齐。"),
            ("mechanism", "interpretation", "在这个例子里，可以把差别理解成显示精度不同。"),
            ("mechanism", "analogy", "这就像同一段距离，一个人说大约三公里，另一个人写到具体米数。"),
            ("mechanism", "explanation", "接着把两种写法放在一起，看看它们回答的是不是同一个问题。"),
            ("mechanism", "interpretation", "真正值得追问的不是小数点后多了几位，而是口径有没有变化。"),
            ("mechanism", "explanation", "还要看数据是否来自同一年度，是否经过修订，以及增长率是不是实际口径。"),
            ("mechanism", "interpretation", "末尾写得更细，并不会自动改变前面共同表达的方向。"),
            ("mechanism", "interpretation", "普通人看到两个数字时，最容易把显示差异误读成机构分歧。"),
            ("mechanism", "explanation", "避免误读的方法很简单，先对口径，再看精度，最后才比较结论。"),
            ("core_judgment", "interpretation", "所以核心判断是，小数位不同未必是矛盾，口径不同才需要真正警惕。"),
        ]
        sentences = [ScriptSentence(sentence_id=f"sentence_{n:03d}", section=section,
            sentence_type=kind, text=text, claim_ids=[claim.claim_id] if kind == "verified_fact" else [])
            for n, (section, kind, text) in enumerate(texts, 1)]
        return ScriptDraft(angle_id=request.selected_angle.angle_id, title=request.selected_angle.title, sentences=sentences)

    def repair_script(self, request: ScriptRepairInput) -> ScriptPatchResult:
        return ScriptPatchResult(patches=[])
