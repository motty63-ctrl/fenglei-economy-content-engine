# Provider Interface

`SearchProvider.search(SearchRequest) -> SearchResponse` 只返回候选 URL、标题、日期提示、排序分数和 discovery snippet；所有结果固定 `evidence_eligible=false`。

`DocumentFetcher.fetch(source_id, url, title) -> FetchedDocument` 必须直接请求候选 URL，限制超时和正文大小，并记录抓取时间。

`RuleBasedEvidenceExtractor.extract(documents, questions)` 只处理已保存的原始正文，输出 evidence text、段落 locator、发布日期和抓取时间。后续模型 extractor 可实现相同边界，不改变业务层。

首个 provider 为 `TavilySearchProvider`；业务层只依赖协议，可后续增加 Brave、OpenAI Web Search 和官方数据 API。
