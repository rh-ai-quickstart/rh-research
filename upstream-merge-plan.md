# Upstream catch-up plan — `red-hat-v2.1.0` ← `upstream/develop`

> Status: **DRAFT for review** (untracked working doc, generated 2026-06-22). No merging has started.
> Scope: bring `red-hat-v2.1.0` current with NVIDIA `upstream/develop` (`da1071b`, 2026-06-16),
> preserving Red Hat branding, vLLM / multi-model support, and carefully reconciling data sources
> toward the NVIDIA implementations.

## 0. Decisions locked (2026-06-22)

| Decision | Choice |
|---|---|
| News data source | **Drop** RH `serper_news_search`; **adopt** upstream `duckduckgo_news_search` |
| Paper search | **Drop** RH Serper-backed `google_scholar_paper_search` mods; **adopt** upstream `google_scholar_paper_search` |
| Serper overall | RH `serper_news_search` removed. **NOTE:** upstream's `paper_search` is itself Serper-backed (`SERPER_API_KEY`, serper.dev) — that is NVIDIA's backend, so Serper *stays* for paper search. "Adopt NVIDIA" wins over "remove Serper" here. |
| Data-source architecture | **Adopt** upstream `data_source_registry.py` + `data_sources.py` wholesale |
| End state | Land result **on `red-hat-v2.1.0` in place**. `develop` stays a pristine upstream mirror. |
| Merge vs rebase | **Merge** (branch is public + tagged `v2.1.0-redhat`; never rebase shared history) |

Data-source resolution: take NVIDIA implementations across the board. `serper_news_search` dropped → `duckduckgo_news_search`.
`google_scholar_paper_search` reset to pure upstream (which uses Serper as its backend). `SERPER_API_KEY` env wiring is therefore
RETAINED for paper_search; only the RH news-search Serper usage is removed.

## 1. Baseline facts (verified)

- RH fork base: `62101c8` (v2.0, 2026-03-18). RH tip `84d6bf6` (90 commits).
- Upstream tip `da1071b` (2026-06-16) — **106 commits** ahead of the RH base.
- **Conflict surface: 137 files** touched by both sides since the base:
  `frontends/ui` 33 · `src/aiq_agent` 27 · `frontends/aiq_api` 21 · `docs/source` 12 ·
  `tests/aiq_agent` 9 · `frontends/benchmarks` 6 · `tests/tokenomics` 5 · others.
- `nvidia-nat`: RH `1.6.0` → upstream `1.7.0`.

## 2. Must-preserve inventory (Red Hat value)

### 2a. Branding (`frontends/ui`)
Logo (fedora SVG), `#EE0000` palette, Red Hat Display/Text fonts, app name "Red Hat Research", favicon,
KUI design-system token overrides in `globals.css`.
**Branding files that ALSO changed upstream (hard-merge set):**
- `frontends/ui/src/app/globals.css`  (palette / KUI tokens)
- `frontends/ui/src/adapters/ui/icons.tsx`  (logo)
- `frontends/ui/src/features/layout/components/AppBar.tsx` (+ `AppBar.spec.tsx`)  (app name / logo placement)
- `frontends/ui/src/features/layout/components/ChatArea.tsx` (+ `ChatArea.spec.tsx`)
- `frontends/ui/src/features/layout/components/ResearchPanel.tsx`

### 2b. vLLM + multi-model (beyond Nemotron)
- `configs/config_web_vllm.yml`, `configs/config_frontier_models.yml` (`openai` `_type`, e.g. `gpt-5.2`)
- `src/aiq_agent/common/config_validation.py` — optional API-key for local/private endpoints
- `src/aiq_agent/common/prompt_utils.py` — `get_thinking_prefix()` / `is_nemotron()`
  (Nemotron keeps `/think`; other models get clean prompts) + exports in `common/__init__.py`
- Agent callers: `chat_researcher/nodes/intent_classifier.py`, `clarifier/agent.py`,
  `clarifier/prompts/plan_generation.j2`
- `tests/.../test_vllm_e2e.py`

### 2c. Data sources (the careful zone)
- Base: `google_scholar_paper_search`, `knowledge_layer`, `tavily_web_search`
- RH added/modified Serper backing for news + paper → **DROP entirely**, adopt upstream sources
- Upstream added: `duckduckgo_news_search`, `exa_web_search`, `polymarket_prediction_market`,
  plus new module `src/aiq_agent/common/data_source_registry.py` + `agents/deep_researcher/tools/source_registry.py`
- Shared `src/aiq_agent/common/data_sources.py`: upstream rewrote (+55/−24), RH small add (+18/−2) — take upstream, re-wire.

## 3. Execution strategy — staged merge on an integration branch

**Branch:** `chore/upstream-merge-v2.1.0-2026-06` off `origin/red-hat-v2.1.0`.
Never merge directly onto `red-hat-v2.1.0` or `develop`. Final PR targets `red-hat-v2.1.0`.

Approach: a single `git merge upstream/develop` will surface all 137 conflicts at once. To keep each domain
testable, resolve in the staged order below within that one merge (or sequence upstream sub-ranges if cleaner),
committing checkpoints and running the matching tests before moving on.

### Stage A — mechanical / low-risk
- `pyproject.toml`, `uv.lock` (regenerate via `uv lock`), `nvidia-nat 1.6.0→1.7.0`
- `.pre-commit-config.yaml`, `.secrets.baseline`, CI configs, `CHANGELOG.md`, `LICENSE-THIRD-PARTY`
- Reconcile issue-#5 security bumps already on RH (don't duplicate/regress)
- **Gate:** `uv lock --check`; `uv sync`; import smoke (`python -c "import aiq_agent"`)

### Stage B — data sources (highest care; prefer NVIDIA)
1. Adopt upstream `data_sources.py`, `data_source_registry.py`, `tools/source_registry.py`, `source_registry.j2` as base.
2. **Remove** `sources/serper_news_search/` entirely + every reference (≈45 files: configs, docs, deploy, notebooks, scripts, `frontends/ui/src/features/layout/data-sources.ts`, `frontends/aiq_api/.../registry.py`).
3. **Adopt upstream `google_scholar_paper_search`** — discard RH's Serper-backed modifications to it; take upstream's version wholesale (resolves the former open item).
4. **Add** upstream `duckduckgo_news_search` to the registry + UI data-source toggles + configs where serper-news was wired.
5. Also inherit `exa_web_search`, `polymarket_prediction_market` (decide whether to expose in UI/configs or leave dormant).
6. **Verify news-search Serper residue is gone:** `git grep -i serper` should return ONLY upstream's `paper_search`/google_scholar references (Serper is its backend) — no `serper_news_search` / RH news-search references.
7. Reconcile `frontends/aiq_api/src/aiq_api/registry.py` + `test_data_sources*` / `test_data_source_registry`.
- **Gate:** `pytest tests/aiq_agent/common/test_data_source*` + source-package tests; `/v1/data_sources` endpoint test.

### Stage C — agents / LLM / prompts (preserve vLLM + thinking logic)
- Merge upstream agent + prompt changes while **keeping** `get_thinking_prefix()`/`is_nemotron()` and
  `config_validation.py` openai handling. Watch `auth`/provider-lifecycle-hook changes from upstream (#195).
- Verify `config_web_vllm.yml` + `config_frontier_models.yml` still resolve against new NAT 1.7.0 LLM plumbing.
- **Gate:** `pytest tests/aiq_agent` (agents/common); config-load smoke for vLLM + frontier configs.

### Stage D — auth middleware (#173)
- Reconcile `frontends/ui/src/adapters/auth/config.ts` (+ `.spec.ts`), `AppConfigContext.tsx`, API auth surface.
- **Gate:** auth unit tests; UI auth adapter tests.

### Stage E — frontend rebrand
- Merge upstream UI (33 files) while re-asserting the 2a hard-merge set (palette, logo, app name, fonts).
- **Gate:** `npm test` (UI), visual check of AppBar/branding; `AppBar.spec` / `ChatArea.spec` pass.

### Stage F — full validation
- Upstream `aiq-release-qa` skill across touched surfaces (py / frontend / docs / eval).
- `test_vllm_e2e.py` end-to-end; one real query through `config_web_vllm.yml`.

## 4. PR & landing
- PR `chore/upstream-merge-v2.1.0-2026-06` → `red-hat-v2.1.0` via fork-aware API:
  `gh api repos/rh-ai-quickstart/rh-research/pulls -X POST -f base=red-hat-v2.1.0 -f head=...`
- Merge method: **merge commit** (preserve upstream SHAs for future syncs).
- Re-tag (e.g. `v2.1.1-redhat`) after merge if desired.

## 5. Risks / watch-items
- **137-file merge is large** — staged gates above are the mitigation; consider splitting C/E into sub-PRs if conflicts are deep.
- **`data_sources.py` rewrite** — RH registration semantics may differ from upstream's new registry; re-wire, don't patch.
- **Serper news-search removal breadth** — RH `serper_news_search` references span ~45 files (configs, docs, notebooks, deploy). Remove news-search wiring only; KEEP `SERPER_API_KEY` + paper_search Serper usage (upstream's backend). Distinguish the two when grepping.
- **NAT 1.6.0→1.7.0** — possible API changes in `builder.get_llm()` / LLM client creation affecting vLLM `openai` path.
- **Branding regressions** — upstream UI refactors may move the components that carry logo/app-name; re-assert tokens after merge.

## 6. Rollback
- All work isolated on `chore/upstream-merge-v2.1.0-2026-06`; `red-hat-v2.1.0` untouched until PR merge.
- `develop` unaffected (pristine mirror; PR #16 separate).
