# Offline pilot scope rehearsal

From the repository root:

```sh
for case in matched missing-entitlement wrong-entitlement wrong-destination wrong-pilot; do
  python3 tests/test_synthetic_pilot_scope.py "$case" || exit
done
python3 -m unittest discover -s tests -p 'test_synthetic_pilot_scope.py' -v
```

All dataset, use, destination and pilot names are invented. A mock request
matches only if the entitlement, destination and pilot records cover the same
dataset and use, and the relevant destination and pilot IDs also match.
A negative case passes only when the intended stop is recorded.

No data is read from a provider or transferred. The fixture grants no rights,
makes no legal or entitlement determination, and uses no live service. Actual
pilot permission still needs separately authorized evidence of Terminal and
destination rights, permitted use, and the named pilot.
