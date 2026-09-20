# BayesMail Architecture Refactor Design

## Purpose

Reorganize BayesMail so that its data flow and module responsibilities are
clear without changing its observable behavior. The refactor targets the
current duplication between sampling and cleaning, the mixed responsibilities
inside `preprocessing.py`, and the repeated artifact-management code in the
cleaning, training, and evaluation pipelines.

This is a behavior-preserving refactor. It does not add a GUI, replace the
handwritten naive Bayes model, change tokenization, introduce jieba, or alter
the command-line interfaces and generated artifact schemas.

## Success Criteria

- A reader can identify the parsing, cleaning, grouping, modeling, artifact,
  and CLI orchestration layers from the package structure.
- MIME parsing, subject decoding, body selection, transfer decoding, and HTML
  text extraction have one shared implementation.
- Cleaning policy remains separate from generic email parsing.
- Duplicate grouping remains separate from single-message cleaning.
- JSON, JSONL, SHA-256, UTC timestamps, and manifest finalization use shared
  infrastructure.
- Existing CLI arguments, output filenames, JSON fields, model serialization,
  and failure-on-overwrite behavior remain compatible.
- All existing tests continue to pass, supplemented by boundary tests for the
  extracted modules.

## Package Structure

```text
src/bayesmail/
├── email_parser.py   # Raw MIME bytes to decoded subject/body
├── cleaning.py       # Repairs, normalization, and quality decisions
├── grouping.py       # Content hashes and leakage-prevention groups
├── model.py          # Tokenization, vocabulary, and naive Bayes
├── artifacts.py      # JSON/JSONL, hashing, timestamps, and manifests
├── data.py           # Sampling CLI orchestration
├── preprocessing.py  # Cleaning CLI orchestration
├── train.py          # Training CLI orchestration
├── evaluate.py       # Evaluation CLI orchestration
└── predict.py        # Existing placeholder; outside this refactor
```

Dependencies flow in one direction:

```text
CLI orchestration
    ↓
cleaning / grouping / model domain logic
    ↓
email parsing / artifact infrastructure
```

No lower layer imports a CLI module.

## Module Responsibilities

### `email_parser.py`

Owns reusable, policy-neutral email parsing:

- resilient byte decoding with the existing UTF-8 and GB18030 fallback;
- MIME Subject header decoding;
- preferred plain/HTML body-part selection;
- strict base64 transfer decoding with the existing flat-payload fallback;
- visible-text extraction from HTML;
- representation of parsing warnings and actions needed by cleaning audits.

The parser accepts bytes and returns decoded content plus parsing metadata. It
does not assign `keep`, `quarantine`, or `exclude`, and it does not apply
reviewed corpus-specific overrides.

Sampling and cleaning call the same parser. Sampling converts parser metadata
to the warnings currently exposed by `data.py`; cleaning records the metadata
in its audit fields.

### `cleaning.py`

Owns corpus policy for one message:

- reviewed raw-byte overrides;
- strict Subject-fold repair;
- Unicode and whitespace normalization;
- malformed-content flags;
- `keep`, `quarantine`, and `exclude` decisions;
- before/after audit metadata needed by the cleaning report.

Its primary operation is deterministic and does not write files. The existing
cleaning rule version remains `clean-v1` because this refactor does not change
the rules or output semantics.

### `grouping.py`

Owns normalized content hashes, duplicate-group reports, content-group IDs,
and cross-label conflict quarantine. It mutates or returns cleaned records in
the same form currently consumed by training. It performs no MIME parsing and
no filesystem writes.

### `artifacts.py`

Owns infrastructure shared by cleaning, training, and evaluation:

- `read_json`, `read_jsonl`, `write_json`, and exclusive `write_jsonl`;
- SHA-256 for bytes, canonical JSON values, and files;
- timezone-aware UTC ISO timestamps;
- final artifact hash collection and manifest completion.

It does not know about email labels, model metrics, or cleaning statuses.
Callers retain control over which artifact names belong in a manifest.

### CLI Modules

`data.py`, `preprocessing.py`, `train.py`, and `evaluate.py` retain their
public functions and command-line interfaces where tests or users depend on
them. They validate CLI inputs, call domain operations, write artifacts, and
render terminal output. Domain algorithms no longer live in their `main()`
functions or pipeline orchestration functions.

## Data Flow

The cleaning pipeline becomes:

```text
TREC index
  → read raw bytes
  → apply reviewed raw repair
  → shared MIME parser
  → cleaning policy and audit record
  → content grouping and conflict handling
  → summary construction
  → artifact writer and completed manifest
```

Training and evaluation continue to consume the same JSONL/model schemas. They
only replace their private file helpers with `artifacts.py` operations.

## Compatibility Constraints

- Preserve `python -m bayesmail.data`, `preprocessing`, `train`, and `evaluate`.
- Preserve current argument names and defaults.
- Preserve generated filenames and JSON object fields.
- Preserve deterministic ordering, hashes, grouping IDs, and model output.
- Preserve exclusive creation/no-overwrite behavior.
- Preserve the standard-library-only runtime for the implemented pipeline.
- Keep underscore-prefixed compatibility imports only when an existing test or
  module needs them during migration; new code imports the owning module.
- Do not alter files under generated report directories as part of the core
  refactor.

## Error Handling

Domain functions raise typed built-in exceptions consistent with the current
API (`ValueError`, `OSError`, `FileExistsError`, `KeyError`). CLI modules keep
translating expected failures into localized `argparse` exit messages.

Manifest behavior remains crash-auditable: the output directory receives an
`in_progress` manifest before artifacts, and becomes `complete` only after all
declared artifacts have been written and hashed.

## Migration Strategy

The work proceeds in independently testable stages:

1. Add artifact infrastructure and migrate training/evaluation without schema
   changes.
2. Add shared parsing behind characterization tests, then migrate sampling and
   cleaning to it.
3. Extract cleaning policy and grouping while retaining compatibility exports
   from `preprocessing.py` during the transition.
4. Reduce `preprocessing.py` to orchestration and extract summary construction.
5. Remove migration-only duplication after the full suite proves consumers use
   the new boundaries.

Each extraction follows red-green-refactor. Tests first pin the intended module
interface or an existing behavior that would otherwise drift.

## Verification

Verification includes:

- the complete existing unittest suite;
- focused tests for artifact exclusivity and canonical hashes;
- parity tests showing sampling and cleaning share Subject/body decoding;
- regression tests for invalid base64, malformed multipart messages, implicit
  HTML body starts, reviewed repairs, and cross-label groups;
- checks that generated training, cleaning, and evaluation manifests retain
  their existing fields and artifact hashes;
- compilation of all package and test modules.

No claim of compatibility is made until a fresh full-suite run succeeds.

## Out of Scope

- implementing the prediction CLI;
- changing Chinese tokenization or stop words;
- adopting scikit-learn for the model;
- parallelizing corpus cleaning;
- changing report prose or generated historical artifacts;
- GUI or service development.
