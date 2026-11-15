# Full-cost comparison template

This is the reproducible calculation slice of issue #3. Copy
`model.template.json` to an evidence-backed input file, fill in a common
period, currency, task boundary, permission rule, and acceptance criterion,
then run `python3 scripts/unit_economics.py path/to/input.json`. Keep the
input file and its cited evidence together. The template intentionally has
no economic assumptions or sample savings.

For each of four alternatives, `attempts` counts eligible episodes and
`accepted_authorized_completions` counts independently accepted outcomes.
All costs use the same currency and period. `setup_amortized`, `licensing`,
`maintenance`, and `allocated_fixed` are period totals. `model`, `tools`,
`human_operation`, `verification`, `recovery`, and `support` are costs per
attempt, including failed and correctly stopped attempts. Enter zero only
when evidence supports zero; leave unknown values `null`.

The script calculates:

`total_cost = sum(fixed period costs) + attempts × sum(costs per attempt)`

`unit_cost = total_cost / accepted_authorized_completions`

It withholds both costs if any input is missing and withholds unit cost when
there are zero accepted completions. Sensitivity rows vary volume by 0.5×
and 2× and acceptance rate by ±10 percentage points, holding cost inputs
fixed. These are mechanical hypotheticals, not forecasts or ROI claims.
The `comparable` flag stays false until context and all inputs are supplied
and the four alternatives use the same number of eligible attempts.

Still needed for issue #3: dated primary-source capability research, real
prospect observations, cited cost inputs, a substitute map, and a decision
memo. The ranking CSV and synthetic workflow catalog cannot supply those
measurements.
