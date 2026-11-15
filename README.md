# Runspindle for Bloomberg

A static marketing and source-library site for the **Runspindle for the Bloomberg Terminal** product concept. The source material describes proposed workflows and synthetic examples. It does not claim a deployed integration, live trading, measured savings, or Bloomberg endorsement.

## Explore

- [Product concept](assets/runspindle_bloomberg_product.pdf): 16-page overview and workflow summaries.
- [Workflow catalog](assets/runspindle_bloomberg_workflows.csv): 40 complete scenarios and source URLs.
- [Ranked catalog](assets/runspindle_bloomberg_ranked.csv): the same 40 scenarios, ranked by the supplied scoring fields.
- [Asset guide](ASSETS.md): annotations and relationships for every original asset.
- [Gallery index](assets/Runspindle_Gallery_Index.html): 37-page map with citations for the eight additional business cases.
- [Synthetic replay corpus and case 10 harness](evaluation/README.md): 40 source-linked cases and one executable replay with negative cases; finance rules and live outcomes remain unverified.
- [Full-cost model](economics/README.md): an input template and calculator for comparing four alternatives without inventing costs or savings.
- [Case 10 draft contract](pilot/case-10-contract-v0.1.md) and [Console prototype](src/prototype.html): a synthetic paper-flow study for issue #4, without live access or accepted outcomes.
- [Synthetic run coordinator](pilot/runtime-README.md): a local durable state machine and demo traces for issue #5, with no live adapter or accepted outcome.
- [Synthetic adapter contracts](pilot/adapters-README.md): source and paper destination interfaces for issue #6, with an explicit live-access blocker.
- [Security and operations review pack](operations/security-review-v0.1.md): draft threat model, failure evidence, runbook, and pilot blockers for issue #8.

## Build locally

Requires Python 3.12+ and Pillow (`python -m pip install Pillow==11.3.0`). Run `python scripts/build.py`, then serve `dist/` with `python -m http.server 8000 --directory dist`. The build creates an asset catalog, workflow data, gallery thumbnails, and a complete static site. Source assets stay in `assets/`; generated files stay in ignored `dist/`.

## Publishing

Every push to `main` builds and publishes `dist/` through [the GitHub Pages action](.github/workflows/pages.yml). GitHub Pages must be configured to use **GitHub Actions** as its source.

## Evidence boundary

The eight cross-system business workflows and 32 Terminal-only paper workflows use fictional businesses or synthetic numbers. The research paper calls the integrated Runspindle system unimplemented and frames its claims as hypotheses. Bloomberg Terminal access, data rights, and any separate product access must be arranged by the operator. The site preserves those boundaries and links to the underlying records.

This is an independent concept presentation; Bloomberg is a trademark of Bloomberg Finance L.P. or its affiliates. No affiliation or endorsement is implied.
