# Example messages

The Amazon and H&M examples support frontend development before provider integrations
exist. They contain no downloaded rows, real predictions, executed checks, or measured
metrics.

All response and result examples identify themselves with `fixture: true` and an
implementation status. Task-draft requests cannot carry that marker because the public
request schema rejects undeclared fields; their location in this directory is the
fixture marker.
