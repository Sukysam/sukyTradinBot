# Benchmarks

One JSON file per tagged milestone, recording what was actually measured
at that point — not a live dashboard, a historical record. The point is
comparability over time: six months from now, "did training get slower"
or "did memory usage regress" should be answerable by diffing two files
here, not by re-deriving numbers from old PR descriptions.

## Format

Each file is named after its git tag (`vN-<milestone-name>.json`) and
records whatever that milestone's own performance-marked tests actually
measured — the schema is milestone-specific (a feature pipeline and an
HMM trainer measure different things), but every file includes:

- `tag` — the git tag this snapshot corresponds to.
- `date` — when it was measured (not necessarily the tag date, if
  backfilled).
- `python_version` — the exact interpreter used (`python3 --version`).
- `platform` — OS, since peak-RSS measurement is platform-sensitive (see
  below).
- `dataset` — a plain-language description of what was run, precise
  enough to reproduce (row count, feature count, synthetic vs. real).
- `source` — which test(s) the numbers came from, so the methodology is
  traceable, not just the result.

## Memory methodology

`memory_mb` is **peak resident set size for the whole Python process**
(`resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`, converted to MB —
bytes on macOS, KB on Linux; watch the platform when comparing across
machines), measured immediately after the operation being benchmarked
completes. This includes Python/numpy/scipy/hmmlearn import overhead, not
just the incremental cost of the operation itself — an honest "how much
memory does this process need," not an idealized "memory used by training
alone" number, which was not separately measured.

## Adding a new snapshot

When a milestone's own performance tests are green, run the same
scenario once more with timing + `resource.getrusage` wrapped around it
(see `v0.4-hmm-regime-detection.json`'s `source` field for the exact
script shape used), and add `benchmarks/vN-<milestone-name>.json` in the
same change that tags that milestone. Never edit a past file after the
fact — like `CHANGELOG.md`, this is a historical record; a corrected
methodology gets a note in the new file, not a retroactive edit to an old
one.
