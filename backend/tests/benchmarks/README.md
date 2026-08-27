# External benchmark cases

This directory tests downstream deterministic assessment and feasibility rules from already structured inputs. It does not score LLM interpretation. The separate live-model harness is documented in `backend/evaluation/README.md`.

Add normalized benchmark cases as `.json` files under `cases/`. The test harness discovers every file automatically; no Python test registration is required.

A file may contain one case object or a JSON array of cases. Each case is validated by `schema.py`, loaded into a fresh in-memory SQLite database, evaluated through the production assessment and feasibility services, and compared with its declared expectations.

Use only tender text and metadata you are authorized to process. Source text in a benchmark file is test data, not executable instructions.

Required concepts:

- tender closing time;
- one normalized requirement and deterministic `rule_config`;
- employees and Evidence Registry records;
- optional recovery tasks;
- expected assessment, operational state, usable employee count, and candidate count.

The legacy harness continues to cover the production `certified_staff` rule and the explicit
uncertain fallback used by the R17 demo. The generic v3 procurement vocabulary is evaluated by the
separate production-rule harness documented in `backend/evaluation/README.md`; this keeps hero
fixtures, known interpretation regression cases, and genuinely blind teammate data distinct.
