# Agent verification tools

Keep QA as a read-only evidence renderer. Its action, Review and raw-reference inputs are useful shortcuts; add one general JSON sequence input with ordered processed references, per-step duration and WebP-style loop count. This lets an agent inspect unusual timing without changing project actions or asking the tool to judge visual quality. The same sequence format may be used for objective composition checks.

Add two read-only checks under `tools/projects.py`:

- `check-composition`: compare the exact runtime references and per-step durations of a complete action with a saved runtime Review or explicit sequence. Report the first mismatch and clip boundary locations. Never change the action or approve its visual quality.
- `check-export`: inspect a resource ZIP using its embedded project configuration and current processed PNGs. Check archive integrity, included frame bytes, atlas pixels, playback records, and animated preview timing/visible frames where the encoder preserves the authored step count. Report format limitations and mismatches. Reject project backups as outside this check.

Both checks return JSON and use nonzero status on a failed check. They must not write project art or silently repair anything. Current processed files are the verification baseline, so a ZIP from an older project revision should report a mismatch rather than claim it is valid. Keep candidate alignment and artistic acceptance under agent/human judgment; do not turn project-specific heuristics into a universal auto-fix.

All tests use temporary projects with synthetic PNGs. Preserve existing user files and run the repository's required Python and Node suites.
