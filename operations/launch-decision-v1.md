# Launch decision and research release plan

**Recommendation recorded November 20, 2026:** keep the public site at research
preview scope. Production launch and partner intake are on hold. The current
checkout provides a static catalog, synthetic paper Console, local runtime and
evaluation artifacts. This memo is a proposed decision for the accountable
owners. Sign-offs, a launch date and production availability are pending.

## Decision gates

| Gate | Current evidence | Accountable role for review |
| --- | --- | --- |
| Buyer and recurring job | Candidate workflow and fictional examples. Observed buyer demand and willingness to pay are pending. | Product and commercial |
| Terminal access and data rights | Permissioned integration and allowed observation, retention, redistribution and derived use remain unresolved. | Legal/compliance and product |
| Economics | Full-cost model available. Eligible episode counts, active time, costs and competing alternatives require matched measurement. | Commercial and evaluation |
| Workflow contract and runtime | Case 10 synthetic Console, local durable effects, and separate readback evidence. Approved scope and integrated provider acceptance remain pending. | Engineering |
| Adapters | Synthetic source and destination only. Exact entitlements and authorized destination setup need qualification. | Engineering and legal/compliance |
| Evaluation | Synthetic fixture evidence available. Domain review, matched permissioned alternatives and accepted live results are pending. | Evaluation |
| Security, privacy and support | Draft threat model and failure controls available. Named on-call and recovery owners, production data handling and service terms are pending. | Security and operations |
| Pilot | Rehearsal register available. Signed plan, participant consent, live episodes and independent review are pending. | Pilot lead and evaluation |

Sources are tracked in [issues #1–#9](https://github.com/newdarwindev/runspindle_for_bloomberg/issues?q=sort%3Acreated-asc),
the [pilot pack](../pilot/design-partner-pilot-pack.md), the
[cost model](../economics/README.md) and the
[security review](security-review-v0.1.md). Legal/compliance, security,
engineering, product and commercial owners must record their named sign-offs
and dates before the status can advance.

## Positioning and claims review

Public wording for this PR is “Research preview.” Visitors can explore 40
documented workflows and a fictional case 10 paper demo. Product language about
market checks, operator decisions and verified records describes the proposed
workflow. A synthetic pass, illustrated recovery, editorial ranking or example
payout cannot support a production acceptance, ROI, availability or savings claim.

| Surface | Reviewed evidence | Public handling |
| --- | --- | --- |
| Home page | The existing hero labels a product concept and the catalog labels ranking editorial. The new research section makes scope, access and intake visible next to the hero. | Publish research status and synthetic demo link after review. |
| Product brief | Pages 4–6 identify conceptual or synthetic UI. Page 7 labels the integrated product unimplemented and live acceptance and deployment pending. Page 10 uses fictional value examples. | Keep the PDF as a concept brief. Link it alongside the scope notice. |
| Revised gallery | Page 20 labels the comparison worksheet as having no measured results. Pages 30–37 label additional workflows conceptual or synthetic. | Keep it in the visual archive. No customer case study or measured comparison is approved. |

Product PDF SHA-256
`a8fdb0f143b958ce93084f2322163152de54bb4664aa4226a2ee2d41abe19571`.
Gallery PDF SHA-256
`242a15a653bb387f66c498a846de68d8a02dd879c4f98bdad1145e1bf4c7a369`.
Both PDFs remain original source materials. For any future claim, record its
exact wording, source artifact, scope, owner approval, date and expiry.
Remove the claim when its evidence or access scope expires.

## Offer, onboarding and pricing research

The initial research hypothesis is a narrow analyst-led workflow in an already
licensed environment. Evaluate the recurring dividend false-breakdown paper
check first. A permissioned pilot would require an approved account/session,
exact observation scope, and a destination independently accepted under the
signed plan. Start a buyer discussion with a recent instance of the recurring
job and how it was completed. Validate frequency, approval path, error and
review burden, existing alternatives, and the person who can fund a tool.
No participant, access scope, or buyer demand has been confirmed.

Test the proposed offer against a fixed team fee and a usage-based research
hypothesis only after permissioned measurement. Compare with native, expert,
and deterministic alternatives on the same scope. Tie the minimum viable
price to full cost, including setup, licensing, review, recovery and support.
Ask qualified buyers to compare real operating tradeoffs using the same
bounded proposal. Price, sales motion, terms and support capacity stay
uncommitted until commercial validation and owner approval. Do not collect
personal contact or workflow inputs through the research page.

## Research release and rollback

1. Run the static build, Python and Node tests, and local case 10 replay.
2. Open the built site on desktop and mobile. Verify visible research status,
   keyboard focus, legible FAQ, and the working synthetic Console link.
3. Reconcile source PDFs and examples against the claims review. Confirm the
   site keeps intake, pricing, production support and live effects gated.
4. Submit the exact commit and site QA result for review. Use the repository's
   established Pages workflow after the authorized merge.
5. If the preview ships misleading claims, altered source assets, broken
   navigation, or unexpected data collection, revert the offending release to
   the last verified research commit and verify the published result. No live
   workflow or new intake is part of the rollback.

For a later launch, the named owner must predeclare stop and rollback triggers
for rights changes, incorrect or unknown effects, quality regression, and
unmanageable support or recovery burden. Track consecutive eligible episodes,
accepted outcomes, correct refusals, unresolved effects, latency, human-active
time, quality and full cost. Compare the same episodes and rights across
alternatives. Keep preview analytics disabled until privacy review and an owner
define consent, retention and the measurement purpose.
