<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

-->

# Migration: project home moved to `rh-ai-quickstart/rh-research`

On **2026-04-20**, active development of this Red Hat-flavored fork of the NVIDIA AI-Q Blueprint moved from a private personal fork (`RobbieJ/aiq`) to the Red Hat AI Quickstarts organization at [`rh-ai-quickstart/rh-research`](https://github.com/rh-ai-quickstart/rh-research).

This file explains the relationship between the three repositories involved, how git history is laid out, and how to set up your local clone.

## Repository layout

| Role | Repository | Purpose |
|---|---|---|
| **Canonical home** | [`rh-ai-quickstart/rh-research`](https://github.com/rh-ai-quickstart/rh-research) | Where current development, releases, issues, and pull requests live. Clone this. |
| **Upstream** | [`NVIDIA-AI-Blueprints/aiq`](https://github.com/NVIDIA-AI-Blueprints/aiq) | The original NVIDIA AI-Q Blueprint. Used as a source of periodic merges for new NVIDIA features and fixes. |
| **Personal mirror** | `RobbieJ/aiq` (private) | Preserved as-is for historical reference. No new work lands here. |

## Branch layout on `rh-research`

During the initial migration window, `rh-research` has two active long-lived branches:

- **`develop`** — tracks NVIDIA upstream exactly. Identical to `NVIDIA-AI-Blueprints/aiq:develop` at fork time (2026-04-20) and brought forward from there. This is the target for periodic upstream merges.
- **`red-hat-v2.1.0`** — the Red Hat-flavored work. Branched off an older NVIDIA base with ~30 commits of customization on top (see below). Tagged `v2.1.0-redhat` at its tip.

The two branches will converge once the NVIDIA upstream commits between the Red Hat fork point and current `develop` (23 commits as of 2026-04-20, including security patches for Pillow / authlib / cryptography, the data source registry refactor in `#90`, the auth-middleware API surface in `#173`, and the prompt restructure in `#177`) are merged into `red-hat-v2.1.0`. That integration is deliberately tracked as its own piece of work because it touches the data source registry / paper-search / news-search code, the auth middleware, and agent prompts, and deserves isolated testing. See the `upstream-merge` issue on `rh-research` for status.

Once the upstream merge lands, `red-hat-v2.1.0` will be merged into `develop` and `rh-research` will go back to a single-branch project.

## History

`rh-ai-quickstart/rh-research` was initialized as a GitHub fork of `NVIDIA-AI-Blueprints/aiq`, so its commit history is a strict superset of NVIDIA's. On top of the NVIDIA base (at the fork point of the Red Hat work), the `red-hat-v2.1.0` branch adds approximately 30 commits of Red Hat-flavored customizations across three broad areas:

- **vLLM / open-model support** — `configs/config_web_vllm.yml`, intent-LLM base URL override, config validation that skips API-key checks for local and private endpoints, vLLM e2e test coverage, and model-aware thinking prefixes so Nemotron retains `/think` directives while other models get clean prompts
- **Additional data sources** — `paper_search` (Google Scholar via Serper) and `news_search` (Serper news) registered across the clarifier, shallow agent, and `/v1/data_sources` API
- **Frontend rebrand** — logo (fedora SVG), Red Hat palette (#EE0000), Red Hat Display/Text fonts, app name "Red Hat Research", favicon; KUI design-system palette tokens overridden via `globals.css`

See `CHANGELOG.md` for the full feature list.

The migration itself landed as a direct push of the Red Hat branch from the personal mirror to `rh-research:red-hat-v2.1.0`, tagged `v2.1.0-redhat`. No history was rewritten; every commit in the personal-fork history remains intact.

## Setting up a clone

To work on the Red Hat-flavored project, track `red-hat-v2.1.0`:

```bash
git clone -b red-hat-v2.1.0 https://github.com/rh-ai-quickstart/rh-research.git
cd rh-research

# Add NVIDIA upstream for periodic syncs
git remote add upstream https://github.com/NVIDIA-AI-Blueprints/aiq.git
git fetch upstream
```

To track NVIDIA upstream as-is:

```bash
git clone https://github.com/rh-ai-quickstart/rh-research.git
cd rh-research
# develop is checked out by default and tracks NVIDIA
```

### Syncing NVIDIA upstream into the Red Hat branch

```bash
git checkout red-hat-v2.1.0
git fetch upstream
git merge upstream/develop         # expect conflicts — see open issue for guidance
git push origin red-hat-v2.1.0
```

Upstream merge windows are batched rather than continuous. See the open issue on `rh-research` tagged `upstream-merge` for status and the specific files that require care (data source registry, auth middleware, agent prompts).

## Attribution

This project remains Apache-2.0 licensed. All copyright headers continue to read `Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.` — that attribution is a requirement of the upstream license, not a statement of current maintainership.

Red Hat contributions are layered on top of the NVIDIA base and are similarly Apache-2.0 licensed. See `LICENSE` and `LICENSE-THIRD-PARTY` for the full legal text and third-party dependencies.

## Deferred work

The 23 NVIDIA upstream commits between the Red Hat fork point (`7fec684`) and current NVIDIA `develop` (`2397af6`) are tracked as a separate `upstream-merge` issue on `rh-research`. Highlights:

- **Security patches** — Pillow 12.2.0 (CVE-2026-40192), authlib ≥1.6.11, cryptography / pygments / pyopenssl / pytest CVE bumps
- **Architectural changes** — Data source registry refactor (`#90`), AI-Q exposed as API with auth middleware (`#173`), prompt restructure for KV-cache prefix reuse (`#177`), `register_token_fetcher` plugin hook (`#169`)
- **Fixes** — checkpoint pool size, WebSocket auth propagation (with subsequent revert), Dask auth-token propagation, idempotent DB init, SSE stream reliability, file-upload bug

The merge is deferred rather than bundled with the migration because the overlap with Red Hat's `paper_search` / `news_search` data sources, our vLLM / config-validation changes, and the frontend data-sources panel requires isolated testing. This is not a paper exercise — it is a real piece of engineering work.

## Where to find old pull requests and issues

Pull requests and issues filed on `RobbieJ/aiq` are preserved at the personal mirror. Their discussion threads do not migrate automatically with `git push`; each PR closed during migration has a comment pointing to its landing commit on `rh-research`.
