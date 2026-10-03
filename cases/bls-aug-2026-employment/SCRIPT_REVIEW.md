# BLS August 2026 Employment Situation — Script Review

## Review status

- Case: `bls-aug-2026-employment`
- Run: `2026-09-27-001-bls-august-2026-employment-situation`
- Selected angle: `angle_001`
- Candidate title: **从已核验记录看核心问题的几个部分**
- Authoring method: human-edited candidate submitted through `submit_human_script_recovery(...)`
- Candidate status: **pending human Script review**
- Lint: passed; no blocking issues
- Estimated duration: **65.0 seconds**; the only lint finding is the non-blocking `DURATION_TARGET_MISSED` warning against a 75-second editorial target. The estimate is within the configured 60–90 second hard range.
- Submission timestamp: `2026-09-29T09:36:20+08:00`
- Submitter recorded by the owner: `motty63-ctrl`

Lint success is not approval. This submission does not authorize TTS, audio generation, or downstream video work. The supplied wording below has not been rewritten. The final long sentence is represented by two adjacent script segments for structural validation; concatenating them reproduces the supplied sentence exactly.

## Script candidate

1. **Hook** — interpretation; no claim binding

   > 一份就业报告，别只盯着新增就业一个数字。

2. **Phenomenon** — verified fact; `claim_063`; attribution context `bls-release`

   > 美国劳工统计局报告，8月非农就业总人数增加16.2万。

3. **Phenomenon** — verified fact; `claim_064`; attribution context `bls-release`

   > 失业率持平在4.1%。

4. **Phenomenon** — verified fact; `claim_065`; attribution context `bls-release`

   > 私营非农部门平均时薪上涨10美分，涨幅0.3%，达到37.75美元。

5. **Phenomenon** — verified fact; `claim_066`; attribution context `bls-release`

   > 私营非农部门平均每周工时小幅上升0.1小时，至34.4小时。

6. **Phenomenon** — verified fact; `claim_067`; attribution context `bls-release`

   > 6月非农就业变动被上修1.1万，从增加2万修正为增加3.1万。

7. **Phenomenon** — verified fact; `claim_068`; attribution context `bls-release`

   > 7月变动被上修4.4万，从减少2.3万修正为增加2.1万。

8. **Phenomenon** — verified fact; `claim_069`; attribution context `bls-release`

   > 餐饮服务和饮酒场所就业增加5.9万。

9. **Phenomenon** — verified fact; `claim_070`; attribution context `bls-release`

   > 地方政府教育部门就业岗位数增加4.2万。

10. **Phenomenon** — verified fact; `claim_071`; attribution context `bls-release`

    > 信息业就业减少2.3万。

11a. **Mechanism** — verified fact; `claim_063`, `claim_064`, `claim_065`, `claim_066`; attribution context `bls-release`

     > 美国劳工统计局这份报告里，既有8月当期的非农就业、失业率、平均时薪和平均每周工时，

11b. **Core judgment** — verified fact; `claim_067`, `claim_068`, `claim_069`, `claim_070`, `claim_071`; attribution context `bls-release`

     > 也有6月、7月修订和部分行业变化，这些信息需要分开看。

Concatenated segments 11a and 11b: `美国劳工统计局这份报告里，既有8月当期的非农就业、失业率、平均时薪和平均每周工时，也有6月、7月修订和部分行业变化，这些信息需要分开看。`

## Bound claims

| Claim | Script binding |
|---|---|
| `claim_063` | August nonfarm payroll employment increased by 162,000 |
| `claim_064` | August unemployment rate remained unchanged at 4.1 percent |
| `claim_065` | Private nonfarm average hourly earnings rose by 10 cents / 0.3 percent to $37.75 |
| `claim_066` | Private nonfarm average workweek increased by 0.1 hour to 34.4 hours |
| `claim_067` | June payroll change revised from +20,000 to +31,000, an upward revision of 11,000 |
| `claim_068` | July payroll change revised from -23,000 to +21,000, an upward revision of 44,000 |
| `claim_069` | Food services and drinking places employment increased by 59,000 |
| `claim_070` | Local government education employment increased by 42,000 |
| `claim_071` | Information employment declined by 23,000 |

The candidate has no claimless factual sentence. The hook is classified as interpretation and carries no factual claim binding. All bound fact sentences reference the listed BLS claims and use the `bls-release` attribution context.

## Dependency and audit hashes

| Artifact | SHA-256 |
|---|---|
| Facts | `f7cdd59bcfa962201ae031eba20ea6c6bc46ed25229805877089a9f7bfc65882` |
| Research | `ce8cc78eda8f630386c410c39e170d6f393704534415f4612acaf21da2d99862` |
| Source prompt | `4755784c4eb66e45971a25f5cae5908c8c2dd528a42e33bd1ecca27799bf105a` |
| Angles | `32a80578bbeebc6b5f9c10d740d97d436205374b602a9a1d7b2a266edb2d48d8` |
| Human angle selection | `84d8474eef0bcfd02d78b705dfc50ec8103f974b41ca85cd165780442309cc77` |
| Approved terminology map | `a9ee561650535b58d3c6f5bb36c30a884225f70c202f6f0923e2954f05262d2c` |
| `human_script_edit.json` | `f0c370007feae195d3e8b030710c865c593d83e3278f3c9c1e6e990e92b70387` |
| Canonical submitted draft | `2d27970c364bf2066896973b6e6322d89b4c35c55bbface7cd23dc78ba47aa75` |
| `script.json` | `450c61b2799ef9efb85b7b71fa4d191936b51c14815410477cd69aa949d84305` |

The owner recorded the human edit as `pending_human_review`. No script approval record exists. No TTS/provider call, audio artifact, audio approval, storyboard, timeline, or video was created for this BLS run.
