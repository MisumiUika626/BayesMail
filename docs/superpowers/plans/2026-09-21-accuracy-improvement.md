# BayesMail Accuracy Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable jieba word and Chinese-bigram features, select a model on a leakage-safe validation split, and improve frozen-test accuracy without worsening the baseline ham false-positive rate.

**Architecture:** A new `features.py` owns serializable feature configurations and all token extraction. The handwritten multinomial naive Bayes stores that configuration and uses it consistently in training and prediction. A new `experiment.py` performs grouped validation search, deterministic selection, full-development refit, and one final frozen-test evaluation with auditable artifacts.

**Tech Stack:** Python 3.10+, standard library, jieba 0.42.x, `unittest`, existing handwritten multinomial naive Bayes.

**Spec:** `docs/superpowers/specs/2026-09-21-accuracy-improvement-design.md`

## Global Constraints

- Candidate selection must not read frozen-test labels or metrics.
- Every `content_group_id` must remain in exactly one split.
- Preserve loading and predictions of existing model JSON without `feature_config`.
- Keep the handwritten multinomial naive Bayes implementation.
- Preserve existing training/evaluation CLI behavior unless a new optional argument is explicitly added.
- Never overwrite experiment outputs.
- Accept a new model only if frozen-test accuracy exceeds `0.937151584574265` and ham false-positive rate is at most `0.06889352818371608`.
- Run the frozen-test evaluation once after validation selection; do not use it to revise the candidate grid.

## Review Focus

- Mixed Chinese, ASCII, email, URL, and punctuation inputs must produce deterministic features.
- A jieba-based serialized model must never silently fall back to legacy tokenization when jieba is unavailable.
- Stop-word filtering must affect only whole jieba word features, not ASCII or Chinese bigrams.
- Vocabulary fitting must consume internal-training records only during candidate selection.
- A failed experiment must leave the manifest `in_progress`, never `complete`.

---

### Task 1: Configurable Feature Extraction

**Files:**
- Create: `src/bayesmail/features.py`
- Create: `tests/test_features.py`
- Modify: `requirements.txt`

**Interfaces:**
- `FeatureConfig(tokenizer="legacy_char", use_stop_words=False, min_document_frequency=2)`
- `FeatureConfig.to_dict() -> dict`
- `FeatureConfig.from_dict(value) -> FeatureConfig`
- `extract_features(text, config=None) -> list[str]`
- `stop_words_hash() -> str`

- [ ] **Step 1: Add failing literal feature tests**

Test that legacy output equals the current tokenizer; configuration rejects a
minimum document frequency below one; jieba-word output retains
Chinese words and lowercase ASCII/email/domain-like terms; hybrid output emits
`w:`, `c2:`, and `a:` namespaces; stop words remove only matching `w:` tokens;
unknown tokenizer names and malformed configurations raise `ValueError`.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_features -v`

Expected: import failure because `bayesmail.features` does not exist.

- [ ] **Step 3: Add the dependency declaration**

Add `jieba>=0.42.1,<0.43` to `requirements.txt` without changing the existing
scikit-learn declaration.

- [ ] **Step 4: Implement feature extraction**

Use the current ASCII token pattern, contiguous CJK spans, jieba segmentation,
overlapping bigrams, a small immutable stop-word set, and deterministic feature
ordering. Import jieba lazily and raise an actionable `RuntimeError` when a
jieba configuration is used without the dependency.

- [ ] **Step 5: Verify GREEN and full regression**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_features -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt src/bayesmail/features.py tests/test_features.py
git commit -m "feat: add configurable email feature extraction"
```

### Task 2: Model Configuration and Backward Compatibility

**Files:**
- Modify: `src/bayesmail/model.py`
- Modify: `src/bayesmail/train.py`
- Modify: `tests/test_training.py`

**Interfaces:**
- `build_vocabulary(records, min_document_frequency=2, max_features=None, feature_config=None)`
- `MultinomialNaiveBayes.fit(records, vocabulary, alpha=1.0, feature_config=None)`
- serialized `feature_config` on newly written models

- [ ] **Step 1: Write failing model compatibility tests**

Prove that a legacy model dictionary without `feature_config` loads with
`legacy_char`; a hybrid model round trip preserves configuration and prediction;
and vocabulary fitting uses the supplied configuration.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_training -v`

Expected: failures because the model does not accept or serialize feature
configuration.

- [ ] **Step 3: Migrate model tokenization**

Move legacy token behavior behind `features.extract_features`. Store a
`FeatureConfig` in the model and use it in vocabulary fitting, fitting, scoring,
serialization, and deserialization. Keep the public `tokenize()` compatibility
function as the legacy strategy.

- [ ] **Step 4: Thread configuration through training**

Keep existing CLI defaults legacy-compatible. Add optional `feature_config` to
the Python `run_training` interface only where needed by the experiment; do not
change existing positional arguments.

- [ ] **Step 5: Verify GREEN and full regression**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_training tests.test_evaluate -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests pass, including legacy round trips.

- [ ] **Step 6: Commit**

```bash
git add src/bayesmail/model.py src/bayesmail/train.py tests/test_training.py
git commit -m "refactor: persist model feature configuration"
```

### Task 3: Leakage-Safe Candidate Selection

**Files:**
- Create: `src/bayesmail/experiment.py`
- Create: `tests/test_experiment.py`

**Interfaces:**
- `candidate_configs() -> list[dict]`
- `select_candidate(development_records, validation_fraction, seed) -> tuple[dict, list[dict], dict]`
- `rank_candidate(result) -> tuple`

- [ ] **Step 1: Write failing selection tests**

Use synthetic grouped records to prove deterministic, label-stratified,
group-disjoint internal splits; candidate vocabulary is fitted only on internal
training; all planned configurations are recorded; and ties rank by validation
accuracy, lower ham false-positive rate, higher spam F1, then canonical config.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_experiment -v`

Expected: import failure because `bayesmail.experiment` does not exist.

- [ ] **Step 3: Implement candidate generation and ranking**

Generate the fixed tokenizer/stop-word/min-document-frequency/alpha grid. Skip
meaningless legacy stop-word duplicates so every emitted candidate is unique.

- [ ] **Step 4: Implement grouped validation selection**

Reuse `split_by_content_group` and `evaluate_records`. Return the winner,
candidate results, and split summary without accepting a frozen-test input.
Record fit/evaluation duration per candidate.

- [ ] **Step 5: Verify GREEN and full regression**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_experiment -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/bayesmail/experiment.py tests/test_experiment.py
git commit -m "feat: select naive Bayes features on grouped validation"
```

### Task 4: Auditable Experiment Pipeline

**Files:**
- Modify: `src/bayesmail/experiment.py`
- Modify: `tests/test_experiment.py`
- Modify: `README.md`

**Interfaces:**
- `run_experiment(development_path, frozen_test_path, output, validation_fraction=0.2, seed=20260921) -> dict`
- `python -m bayesmail.experiment DEVELOPMENT FROZEN_TEST --output OUTPUT`

- [ ] **Step 1: Write failing pipeline tests**

With small synthetic JSONL files, assert non-overwrite behavior, an in-progress
manifest before candidate work, declared output names and hashes, full-
development winner refit, exactly one final-evaluation call, and disjoint
development/frozen-test group IDs.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_experiment -v`

Expected: failures because the pipeline and CLI do not exist.

- [ ] **Step 3: Implement artifact pipeline and CLI**

Use `artifacts.py` for all reads, writes, times, hashes, and manifest completion.
Write candidates, selection, split summary, model, vocabulary, final metrics,
and final mistakes. Record jieba version and stop-word hash.

- [ ] **Step 4: Update usage documentation**

Document dependency installation, experiment command, leakage protections,
selection criteria, and acceptance thresholds in `README.md`.

- [ ] **Step 5: Verify GREEN, CLI, and full regression**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_experiment -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
```

Expected: all tests and compilation pass.

- [ ] **Step 6: Commit**

```bash
git add src/bayesmail/experiment.py tests/test_experiment.py README.md
git commit -m "feat: add auditable accuracy experiment pipeline"
```

### Task 5: Run and Accept the Experiment

**Files:**
- Experiment outputs under ignored `reports/accuracy_experiment_*`
- Modify source/tests only for Critical or Important final-review findings

- [ ] **Step 1: Install declared dependencies**

Run: `python3 -m pip install -r requirements.txt`

Expected: compatible jieba and scikit-learn versions install successfully.

- [ ] **Step 2: Run the experiment once**

Run:

```bash
PYTHONPATH=src python3 -m bayesmail.experiment \
  reports/training_v1/train.jsonl \
  reports/training_v1/test.jsonl \
  --output reports/accuracy_experiment_v1
```

Expected: a complete manifest, validation candidates, selected model, and one
final frozen-test report.

- [ ] **Step 3: Apply acceptance criteria**

Accept the winner only when final accuracy is greater than
`0.937151584574265` and ham false-positive rate is at most
`0.06889352818371608`. Otherwise retain the legacy model as production and
report the experiment honestly without expanding or revising the grid.

- [ ] **Step 4: Request independent code review**

Review feature determinism, model compatibility, split isolation, frozen-test
single use, manifest ordering, and candidate ranking. Fix all Critical and
Important findings with RED→GREEN tests in one pass; defer Minor findings.

- [ ] **Step 5: Run fresh final verification**

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
git status --short
```

Expected: all tests pass, compilation succeeds, and only intentional tracked
changes remain.

- [ ] **Step 6: Commit review fixes if any**

```bash
git add src tests README.md requirements.txt
git commit -m "fix: address accuracy experiment review"
```

Skip the commit when the review produced no tracked changes.
