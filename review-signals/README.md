# Review Signals

Review signals are deterministic indicators that help Battalion explain engineering evidence.

Examples include:

- acceptance criterion satisfied;
- required evidence missing;
- runtime value differs from expected value;
- source and runtime evidence disagree;
- dependency or build artifacts appear stale.

Review signals support Mission Assurance. They do not replace human engineering judgment.

Future signal catalogs should remain executor-agnostic and should report what was observed, what was expected, and what evidence supports the finding.

This directory is architectural intent, not a current runtime signal-catalog path or package boundary.
