# Evidence Report v1 Retrospective

## What Changed

- Added Evidence Report v1 as a deterministic consumer of Plan Review JSON.
- Added a local CLI command, `battalion evidence-report`, that writes Markdown and JSON runtime artifacts under `.battalion/`.
- Added lifecycle, version, and lineage metadata without adding an artifact resolver or catalog.
- Added concise summaries for verified, failed, unable-to-verify, and out-of-scope deviation findings.
- Preserved observed human decision evidence from Plan Review while keeping Battalion recommendations advisory.
- Documented the command and added focused regression tests.

## Dogfooding Friction

- Plan Review output is a workable v1 input, but it does not yet carry rich Plan metadata such as a material Plan artifact version. Evidence Report v1 records `not recorded` when that metadata is absent rather than inventing it.
- The distinction between Plan Review and Evidence Report needed to stay explicit. The implementation intentionally avoids reclassifying evidence or rerunning Plan Review logic.
- Lifecycle status is recorded as `Completed` for generated reports, while the human decision remains separate and pending until evidenced by PR approval, merge, or an explicit fallback record.
- Regenerating the dogfood Plan Review against the Evidence Report v1 Plan exposed an over-broad Plan Review status parser. Requirement-level `PASS` evidence was incorrectly treated as failed when later text discussed "failed findings." The fix kept status detection scoped to explicit requirement status markers and added regression coverage.

## Recommendations

- Keep Evidence Report v1 as a thin synthesis layer until artifact metadata becomes richer.
- Do not add a resolver or catalog until multiple versioned runtime artifacts make that problem concrete.
- A future artifact metadata slice should decide how Plan versions are recorded at generation time so Evidence Reports can reference a real Plan version instead of `not recorded`.
