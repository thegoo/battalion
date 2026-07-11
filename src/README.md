# Source Layout

This directory is reserved for a future `src/` package layout.

The active Python package currently remains at:

```text
battalion/
```

That package is retained to preserve import paths, editable installation behavior, and Git history during Doctrine v1.0 realignment.

This directory is architectural intent, not a current import root or package boundary.

If Battalion later migrates to `src/battalion`, that work should be handled as a focused packaging compatibility slice with explicit tests for editable installs, console entry points, and packaged data files.
