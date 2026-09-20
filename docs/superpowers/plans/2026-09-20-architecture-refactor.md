# BayesMail Architecture Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate BayesMail's parsing, cleaning, grouping, model, artifact, and CLI responsibilities without changing public behavior or generated schemas.

**Architecture:** Introduce policy-neutral email parsing and artifact infrastructure at the bottom layer, move cleaning and grouping into focused domain modules, and leave the existing CLI modules as orchestration and compatibility facades. Migrate one boundary at a time under characterization tests.

**Tech Stack:** Python 3.10+ standard library, `unittest`, JSON/JSONL, `email`, `html.parser`, SHA-256.

**Spec:** `docs/superpowers/specs/2026-09-20-architecture-refactor-design.md`

## Global Constraints

- Preserve the existing CLI modules, arguments, defaults, output filenames, and localized failure messages.
- Preserve generated JSON fields, deterministic ordering, hashes, content-group IDs, and model serialization.
- Preserve exclusive creation and failure-on-overwrite behavior.
- Preserve the standard-library-only runtime for the implemented pipeline.
- Keep `RULE_VERSION = "clean-v1"`; this refactor must not change cleaning semantics.
- Do not implement prediction, change tokenization, add jieba/scikit-learn use, or rewrite report artifacts.
- The workspace has no Git repository metadata; replace commit steps with a full test run and workspace diff inspection checkpoint.

## Review Focus

- Malformed base64 payloads must retain the current flat-body fallback and audit/warning behavior.
- Multipart headers without boundaries must continue to expose their readable flat bodies.
- HTML with omitted closing `head` or opening `body` must retain visible body text while hiding metadata.
- Reviewed Subject repairs and charset overrides must remain hash-guarded and deterministic.
- Output failures must never result in a manifest marked `complete` before every declared artifact is hashed.

---

### Task 1: Shared Artifact Infrastructure

**Files:**
- Create: `src/bayesmail/artifacts.py`
- Create: `tests/test_artifacts.py`
- Modify: `src/bayesmail/train.py`
- Modify: `src/bayesmail/evaluate.py`

**Interfaces:**
- `sha256_bytes(value: bytes) -> str`
- `sha256_file(path: Path) -> str`
- `canonical_hash(value: object) -> str`
- `read_json(path: Path) -> object`
- `read_jsonl(path: Path) -> list[dict]`
- `write_json(path: Path, value: object) -> None`
- `write_jsonl(path: Path, rows: Iterable[dict]) -> None`
- `utc_now() -> str`
- `artifact_hashes(output: Path, names: Iterable[str]) -> dict[str, str]`

- [ ] **Step 1: Write failing artifact boundary tests**

Add tests proving canonical JSON hashing is stable, JSONL skips blank input lines,
JSONL output uses exclusive creation, and artifact hashes match file contents.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_artifacts -v`

Expected: import failure because `bayesmail.artifacts` does not exist.

- [ ] **Step 3: Implement the minimal artifact module**

Implement the listed interfaces with UTF-8, `ensure_ascii=False`, canonical
separators for hashes, one JSON object per JSONL line, timezone-aware UTC, and
exclusive JSONL creation.

- [ ] **Step 4: Verify focused tests GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_artifacts -v`

Expected: all artifact tests pass.

- [ ] **Step 5: Migrate training and evaluation helpers**

Replace private JSON, JSONL, SHA-256, timestamp, and JSONL-read implementations
with imports from `artifacts.py`. Keep their return values and manifests byte-
compatible except for unavoidable timestamp values and absolute temp paths.

- [ ] **Step 6: Run affected and full suites**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_training tests.test_evaluate -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests pass.

### Task 2: Shared Policy-Neutral Email Parser

**Files:**
- Create: `src/bayesmail/email_parser.py`
- Create: `tests/test_email_parser.py`
- Modify: `src/bayesmail/data.py`
- Modify: `src/bayesmail/preprocessing.py`

**Interfaces:**
- `decode_bytes(raw: bytes, charset: str | None = None) -> str`
- `decode_subject(message, override_charset: str | None = None) -> str`
- `visible_html(text: str) -> str`
- `parse_email(raw: bytes, *, identifier: str, subject_charset: str | None = None, force_html: bool = False) -> ParsedEmail`
- `ParsedEmail(subject, body, actions, warnings, mime_defects)`

- [ ] **Step 1: Write failing parser characterization tests**

Cover valid GBK Subject/body decoding, malformed base64 flat fallback, malformed
multipart flat fallback, HTML hidden metadata, implicit body start, attachment
exclusion, empty-plain-to-HTML fallback, and parser metadata.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_email_parser -v`

Expected: import failure because `bayesmail.email_parser` does not exist.

- [ ] **Step 3: Implement the shared parser**

Move the strongest existing decoding and HTML behavior into `email_parser.py`.
The parser returns metadata instead of applying cleaning statuses. Preserve
warning text required by sampling and action names required by cleaning.

- [ ] **Step 4: Verify parser tests GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_email_parser -v`

Expected: all parser tests pass.

- [ ] **Step 5: Migrate `data.read_email`**

Keep `read_email(path, identifier, label)` public. Validate the label, read raw
bytes, call `parse_email`, replay parser warnings through `warnings.warn`, and
return the existing four-field record.

- [ ] **Step 6: Migrate cleaning parsing calls**

After reviewed raw repairs and Subject-fold repair, call `parse_email` with the
reviewed charset/HTML options. Transfer parser actions, warnings, and MIME
defects into the existing cleaning record fields.

- [ ] **Step 7: Prove parsing parity**

Add a test that feeds the same repaired raw message through sampling and
cleaning and asserts equal decoded Subject/body before cleaning normalization.
Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_data tests.test_preprocessing tests.test_email_parser -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests pass with only warnings explicitly asserted by tests.

### Task 3: Extract Cleaning Policy and Grouping

**Files:**
- Create: `src/bayesmail/cleaning.py`
- Create: `src/bayesmail/grouping.py`
- Create: `tests/test_grouping.py`
- Modify: `src/bayesmail/preprocessing.py`
- Modify: `tests/test_preprocessing.py`

**Interfaces:**
- `clean_email(raw, identifier, label, overrides=None) -> dict`
- `normalize(text: str) -> str`
- `repair_raw(raw, identifier, overrides) -> tuple[bytes, dict | None]`
- `repair_subject_fold(raw, required=False) -> bytes`
- `group_records(records: Iterable[dict]) -> list[dict]`

- [ ] **Step 1: Write a failing ownership test**

Import cleaning functions from `bayesmail.cleaning` and grouping from
`bayesmail.grouping`. Exercise subject-only grouping, same-body grouping, and
cross-label quarantine through the new module.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_grouping -v`

Expected: import failure because the domain modules do not exist.

- [ ] **Step 3: Move cleaning policy**

Move repair, normalization, quality flags, and status decisions to
`cleaning.py`. It imports the shared parser but does not import CLI or artifact
modules.

- [ ] **Step 4: Move grouping logic**

Move content hashes, duplicate reports, content-group IDs, and cross-label
quarantine to `grouping.py`. Use `artifacts.canonical_hash`.

- [ ] **Step 5: Add compatibility exports**

Import and re-export the historically tested functions from
`preprocessing.py` so existing consumers continue to work during and after the
migration. New code imports the owning modules directly.

- [ ] **Step 6: Verify focused and full suites**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_grouping tests.test_preprocessing -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests pass.

### Task 4: Reduce Cleaning Pipeline to Orchestration

**Files:**
- Modify: `src/bayesmail/preprocessing.py`
- Create: `tests/test_cleaning_pipeline.py`
- Modify: `README.md`

**Interfaces:**
- `build_cleaning_summary(records, groups, source_hashes_checked) -> dict`
- `run_cleaning(root, output, overrides, source_audit=None) -> dict`

- [ ] **Step 1: Write failing summary tests**

Use synthetic records and groups to assert status counts, per-label counts,
before/after metrics, duplicate statistics, unique-content counts, and eligible
group count without invoking filesystem orchestration.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_cleaning_pipeline -v`

Expected: import or attribute failure because the summary builder does not yet
exist.

- [ ] **Step 3: Extract summary construction**

Move aggregate calculations from `run_cleaning` into a deterministic function.
Keep the exact output keys and numeric semantics.

- [ ] **Step 4: Migrate cleaning artifacts**

Use `artifacts.py` for JSON/JSONL reads and writes, hashes, UTC timestamps, and
artifact hash collection. Retain the in-progress-before-output and complete-
after-hashing order.

- [ ] **Step 5: Simplify orchestration and document ownership**

Leave `preprocessing.py` responsible for validation, corpus iteration, calls
to cleaning/grouping/summary operations, artifact writes, progress output, and
the CLI. Update the README directory overview with the new modules.

- [ ] **Step 6: Verify output compatibility**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_cleaning_pipeline tests.test_preprocessing -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
```

Expected: all tests and compilation pass.

### Task 5: Architecture and Final Verification

**Files:**
- Modify as required by review findings only.

- [ ] **Step 1: Check dependency direction**

Run an AST/import inspection confirming `email_parser.py`, `artifacts.py`,
`cleaning.py`, and `grouping.py` do not import CLI modules and no cycle exists.

- [ ] **Step 2: Inspect the final workspace diff**

Confirm the changes are limited to the approved modules, tests, README, spec,
and plan. Confirm no report outputs or corpus files changed.

- [ ] **Step 3: Request independent code review**

Ask a reviewer to check behavior preservation, dependency direction, parser
parity, manifest completion ordering, and unnecessary abstraction. Address all
critical and important findings.

- [ ] **Step 4: Run fresh final verification**

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
```

Expected: zero failures and successful compilation.

- [ ] **Step 5: Report the architecture outcome**

Report files created/changed, test counts, compatibility constraints verified,
and any intentionally deferred work. Do not claim success without the fresh
commands from Step 4.
