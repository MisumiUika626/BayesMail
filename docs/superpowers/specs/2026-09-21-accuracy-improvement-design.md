# BayesMail Accuracy Improvement Design

## Purpose

Improve the frozen-test accuracy of BayesMail without tuning directly on the
test set or replacing the handwritten multinomial naive Bayes implementation.
The main intervention is a configurable feature pipeline that can compare the
current character baseline with jieba word features and a hybrid of jieba words
plus Chinese character bigrams.

The existing result is the baseline:

- accuracy: 0.937151584574265;
- spam precision: 0.9652834599649328;
- spam recall: 0.9401183970856102;
- spam F1: 0.9525347482553781;
- ham false-positive rate: 0.06889352818371608.

## Success Criteria

- Select feature and model parameters using only a validation split derived
  from the existing training split.
- Keep every `content_group_id` in exactly one of internal-train, validation,
  and frozen-test.
- Evaluate the selected configuration against the frozen test exactly once in
  the final experiment run.
- Improve frozen-test accuracy above the 0.937151584574265 baseline.
- Do not materially worsen ham false-positive rate; a configuration with a
  higher accuracy but ham false-positive rate above 0.06889352818371608 is not
  accepted automatically.
- Store the tokenizer configuration in the model so future prediction uses the
  same feature extraction as training.
- Continue to load existing model files as the legacy character tokenizer.
- Record every candidate, validation metric, selected configuration, runtime,
  dependency version, and final frozen-test metric in auditable JSON output.

## Experimental Integrity

The existing `reports/training_v1/test.jsonl` remains frozen. Candidate
selection must not read its labels or metrics.

`reports/training_v1/train.jsonl` is split by `content_group_id` into:

```text
development records
├── internal training groups
└── validation groups

frozen test groups (untouched during selection)
```

The split reuses the deterministic grouped, label-stratified logic with a new
experiment seed. Vocabulary fitting, stop-word filtering, document frequency,
and model fitting happen only on internal training records. After selection,
the winning configuration is refit on the full original training split and
evaluated once on the original frozen test split.

## Feature Strategies

### Legacy character baseline

Preserve the current behavior: lowercase ASCII terms and individual CJK
characters. This candidate confirms the internal experiment harness reproduces
the existing model family.

### Jieba words

Use jieba to segment contiguous Chinese text into words. Preserve lowercase
ASCII terms, numbers, email-like strings, and URL/domain-like terms rather than
discarding non-Chinese content.

### Hybrid words and Chinese bigrams

Combine jieba word features with overlapping bigrams for every contiguous CJK
sequence. Prefix feature namespaces so collisions are impossible:

```text
w:招聘
c2:招聘
a:www.example.com
```

The hybrid candidate is recommended because word features capture meaning while
bigrams remain robust to unknown advertising terms and imperfect segmentation.

## Stop Words

Stop-word filtering applies only to whole jieba word features. Character
bigrams and ASCII features are retained. The initial stop-word list is a small,
version-controlled set of high-frequency function words whose removal is tested
as a candidate rather than assumed to help.

MIME terms such as `content-type`, `charset`, and `x-mailer` are not silently
hard-coded away in the tokenizer. If excluded, they belong to an explicit
versioned feature-denylist candidate recorded in the experiment configuration.

## Candidate Grid

Keep the grid deliberately small:

- tokenizer: `legacy_char`, `jieba_word`, `jieba_hybrid`;
- stop words: disabled or the versioned minimal list;
- minimum document frequency: 2 or 3;
- alpha: 0.5 or 1.0.

Candidates are ranked by validation accuracy, then lower ham false-positive
rate, then higher spam F1, then a deterministic serialized configuration key.
No decision threshold tuning is included because the baseline analysis showed
large recall losses for small false-positive improvements.

## Architecture

```text
src/bayesmail/
├── features.py      # Tokenizer configurations and feature extraction
├── model.py         # Handwritten multinomial naive Bayes
├── experiment.py    # Validation search, selection, refit, final evaluation
├── train.py         # Existing production training command
└── evaluate.py      # Existing evaluation functions
```

`features.py` owns a serializable `FeatureConfig` and a single extraction
entry point. Vocabulary building, model fitting, and prediction receive the
same configuration. The model serialization contains `feature_config` for new
models; `from_dict()` supplies `legacy_char` when loading old models without
that field.

`experiment.py` orchestrates data splitting and candidate evaluation. It uses
the existing grouping, model, artifact, and evaluation modules and does not
duplicate their algorithms.

## Model API and Serialization

The model gains a feature configuration while preserving existing calls:

```python
MultinomialNaiveBayes.fit(records, vocabulary, alpha=1.0,
                          feature_config=None)
model.predict_scores(text)
model.predict(text)
```

`None` means the legacy tokenizer. New serialized models contain:

```json
{
  "feature_config": {
    "tokenizer": "jieba_hybrid",
    "use_stop_words": true,
    "min_document_frequency": 2
  }
}
```

The jieba version and stop-word-list hash are recorded in the experiment
manifest. Loading a jieba-based model without jieba installed fails with an
actionable dependency message rather than silently changing tokenization.

## Outputs

The experiment command writes a non-overwriting directory containing:

- `manifest.json`: inputs, hashes, seeds, dependency versions, state, and
  artifact hashes;
- `candidates.jsonl`: configuration and validation metrics for every candidate;
- `selection.json`: ranking rules and selected configuration;
- `model.json`: winner refit on the full original training split;
- `vocabulary.json`: winner vocabulary;
- `validation_split.json`: group and label counts, not duplicated message text;
- `final_evaluation.json`: exactly one frozen-test evaluation of the winner;
- `misclassified.jsonl`: final winner errors for follow-up analysis.

The output directory starts with `state: in_progress` and becomes `complete`
only after all declared artifacts are written and hashed.

## Error Handling

- Reject records without labels or `content_group_id` before splitting.
- Reject any overlap among internal-train, validation, and frozen-test group
  IDs.
- Reject an empty vocabulary or a development split lacking both classes.
- Reject unknown tokenizer names and malformed feature configuration.
- Surface missing jieba as a clear installation error.
- Never overwrite an existing experiment directory.

## Testing and Verification

- Unit-test literal token output for legacy, jieba-word, and hybrid strategies.
- Prove the hybrid tokenizer retains ASCII/URL-like terms and emits Chinese
  bigrams with separate namespaces.
- Prove old serialized models load with legacy behavior.
- Prove a new model round trip retains feature configuration and identical
  predictions.
- Prove candidate selection never consumes frozen-test records.
- Prove internal split content groups are disjoint and deterministic.
- Prove tie-breaking is deterministic.
- Run the full existing suite after each migration stage.
- Run the complete experiment and compare final frozen-test metrics against the
  recorded baseline.

## Out of Scope

- neural networks or transformer models;
- hyperparameter searches over the frozen test set;
- probability calibration or threshold tuning;
- GUI or web-service changes;
- deleting the handwritten naive Bayes implementation;
- rewriting historical training or evaluation artifacts.
