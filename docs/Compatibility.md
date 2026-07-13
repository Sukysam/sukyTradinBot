# Component Compatibility Matrix

Which version of which contract/package a given piece of this platform
was built and verified against. Exists so retraining a model or evolving
a contract doesn't silently produce output nothing downstream actually
expects — before touching a version listed here, check what depends on
it (the "Consumers" column) and confirm they tolerate the change per that
contract's own backward-compatibility policy.

Two different kinds of "version" appear below, and they answer different
questions — don't conflate them:

- **Package version** (`X.__version__`) — this first-party Python
  package's own release version. Bump it under normal semver judgment
  when its *implementation* changes in a way worth noting, independent of
  whether its *contract* changed.
- **Contract version** — the frozen interface version, per that
  contract's own Standards doc (e.g. `PIPELINE_VERSION` for
  `FeatureVector`). Bump it only per that document's own versioning
  policy — usually a much rarer, more deliberate event than a package
  version bump.

| Component | Package | Package Version | Contract | Contract Version | Consumers | Defined In |
|---|---|---|---|---|---|---|
| Market Data | `market_data` | 0.1.0 | — (no frozen output contract yet; `Bar`/`Trade`/etc. are stable models, not yet a versioned contract) | — | `features` | [ADR-002](engineering-handbook/Architecture/ADR/ADR-002-Market-Data.md) |
| Feature Pipeline | `features` | 0.1.0 | `FeatureVector` | v2 (`PIPELINE_VERSION = "2"`) | `hmm`; (planned) `strategy`, backtesting, risk | [ADR-003](engineering-handbook/Architecture/ADR/ADR-003-Feature-Engineering.md), [ADR-004](engineering-handbook/Architecture/ADR/ADR-004-FeatureVector-Contract-Freeze.md), [ADR-005](engineering-handbook/Architecture/ADR/ADR-005-FeatureVector-Provenance.md); binding spec: [Standards/FeatureVector Contract.md](engineering-handbook/Standards/FeatureVector%20Contract.md) |
| Feature Manifest | `features` | 0.1.0 | `config/feature_manifest.yaml` schema | 1 (`MANIFEST_SCHEMA_VERSION = "1"`) | tooling/humans reading the catalog directly | [ADR-003](engineering-handbook/Architecture/ADR/ADR-003-Feature-Engineering.md) |
| HMM & Regime Detection | `hmm` | 0.1.0 | `RegimeState` | v1 | (planned) `strategy`, risk | [ADR-006](engineering-handbook/Architecture/ADR/ADR-006-RegimeState-Contract.md), [ADR-007](engineering-handbook/Architecture/ADR/ADR-007-HMM-Design.md); binding spec: [Standards/RegimeState Contract.md](engineering-handbook/Standards/RegimeState%20Contract.md) |
| Strategy Engine | `strategy` | 0.1.0 | `StrategyDecision` | v1 | `risk`; (planned) execution, adaptive learning, signal orchestration | [ADR-008](engineering-handbook/Architecture/ADR/ADR-008-StrategyDecision-Contract.md) (contract freeze), [ADR-009](engineering-handbook/Architecture/ADR/ADR-009-Strategy-Engine-Design.md) (design); binding spec: [Standards/StrategyDecision Contract.md](engineering-handbook/Standards/StrategyDecision%20Contract.md) |
| Risk Management | `risk` | 0.1.0 | `ExecutionDecision` | v1 | (planned) execution, adaptive learning, signal orchestration | [ADR-010](engineering-handbook/Architecture/ADR/ADR-010-ExecutionDecision-Contract.md) (contract freeze), [ADR-011](engineering-handbook/Architecture/ADR/ADR-011-Risk-Manager-Design.md) (design); binding spec: [Standards/ExecutionDecision Contract.md](engineering-handbook/Standards/ExecutionDecision%20Contract.md) |

Trained model artifacts (`hmm.persistence`'s `model.pkl`/`normalizer.pkl`/
`metadata.json`) carry their own `model_version` per
`hmm.models.ModelMetadata` — a caller-assigned string per training run,
not a package-level version. See
[Standards/RegimeState Contract.md](engineering-handbook/Standards/RegimeState%20Contract.md#model-and-feature-versioning-together)
for how `model_version` and `feature_pipeline_version` travel together on
every `RegimeState`.

## Updating this file

Update the relevant row in the same change that bumps a package version
or a contract version — same discipline as
[CHANGELOG.md](../CHANGELOG.md) and
[PROJECT_STATUS.md](../PROJECT_STATUS.md), never edited retroactively to
reflect a later correction; if a past row turns out to have been wrong,
that's a note in the new row, not a rewrite of history.
