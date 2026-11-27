# Offline pilot wedge rehearsal

From the repository root:

```sh
for case in choose-one missing-rights missing-pilot-evidence insufficient-demand tie; do
  python3 tests/test_synthetic_pilot_wedge.py "$case" || exit
done
python3 -m unittest discover -s tests -p 'test_synthetic_pilot_wedge.py' -v
```

All identities, interview signals, workload frequencies and matched pilot
minutes are invented. A candidate needs scope, enough interview and recurrence
signals, and improvement on enough comparable pilot examples. The fixture
ranks eligible candidates by minutes saved per week; ties or unsupported
evidence produce no selection. Pricing and launch decisions stay unset even
when a synthetic candidate is selected.

This exercise proves neither demand, authorization, economics nor pilot
outcomes in the real world. Those require verified buyer research, permission,
comparable pilot evidence and separately reviewed pricing and launch decisions.
No real data, provider, external calls or deployment are involved.
