"""Dependency-free tokenization and multinomial naive Bayes."""
from collections import Counter
from dataclasses import dataclass
import math
import re


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+(?:[._%+-][a-zA-Z0-9]+)*|[\u3400-\u4dbf\u4e00-\u9fff]")


def tokenize(text):
    """Return lowercase ASCII terms and individual CJK characters."""
    return [token.lower() for token in TOKEN_RE.findall(text or '')]


def record_text(record):
    return f"{record.get('subject', '')} {record.get('body', '')}"


def build_vocabulary(records, min_document_frequency=2, max_features=None):
    """Fit a deterministic token-to-index mapping from training records only."""
    if min_document_frequency < 1:
        raise ValueError('min_document_frequency 必须大于 0')
    if max_features is not None and max_features < 1:
        raise ValueError('max_features 必须大于 0')
    document_frequency = Counter()
    for record in records:
        document_frequency.update(set(tokenize(record_text(record))))
    terms = [item for item in document_frequency.items()
             if item[1] >= min_document_frequency]
    terms.sort(key=lambda item: (-item[1], item[0]))
    if max_features is not None:
        terms = terms[:max_features]
    return {token: index for index, (token, _) in enumerate(terms)}


@dataclass
class MultinomialNaiveBayes:
    classes: list
    vocabulary: dict
    log_priors: dict
    log_likelihoods: dict
    alpha: float
    document_counts: dict
    token_counts: dict

    @classmethod
    def fit(cls, records, vocabulary, alpha=1.0):
        records = list(records)
        if alpha <= 0:
            raise ValueError('alpha 必须大于 0')
        if not records:
            raise ValueError('训练集不能为空')
        if not vocabulary:
            raise ValueError('词表不能为空')
        document_counts = Counter(record['label'] for record in records)
        classes = sorted(document_counts)
        if len(classes) < 2:
            raise ValueError('训练集至少需要两个标签')
        word_counts = {label: Counter() for label in classes}
        for record in records:
            counts = Counter(tokenize(record_text(record)))
            word_counts[record['label']].update(
                {token: count for token, count in counts.items() if token in vocabulary})
        total_documents = len(records)
        vocabulary_size = len(vocabulary)
        log_priors = {
            label: math.log(document_counts[label] / total_documents)
            for label in classes
        }
        log_likelihoods = {}
        token_totals = {}
        ordered_terms = sorted(vocabulary, key=vocabulary.get)
        for label in classes:
            token_totals[label] = sum(word_counts[label].values())
            denominator = token_totals[label] + alpha * vocabulary_size
            log_likelihoods[label] = [
                math.log((word_counts[label][token] + alpha) / denominator)
                for token in ordered_terms
            ]
        return cls(classes, dict(vocabulary), log_priors, log_likelihoods,
                   alpha, dict(document_counts), token_totals)

    def predict_scores(self, text):
        counts = Counter(token for token in tokenize(text) if token in self.vocabulary)
        return {
            label: self.log_priors[label] + sum(
                count * self.log_likelihoods[label][self.vocabulary[token]]
                for token, count in counts.items())
            for label in self.classes
        }

    def predict(self, text):
        scores = self.predict_scores(text)
        return max(self.classes, key=lambda label: (scores[label], label))

    def to_dict(self):
        ordered_terms = sorted(self.vocabulary, key=self.vocabulary.get)
        return {
            'type': 'multinomial_naive_bayes', 'alpha': self.alpha,
            'classes': self.classes, 'vocabulary': ordered_terms,
            'log_priors': self.log_priors,
            'log_likelihoods': self.log_likelihoods,
            'document_counts': self.document_counts,
            'token_counts': self.token_counts,
        }

    @classmethod
    def from_dict(cls, value):
        vocabulary = {token: index for index, token in enumerate(value['vocabulary'])}
        return cls(value['classes'], vocabulary, value['log_priors'],
                   value['log_likelihoods'], value['alpha'],
                   value['document_counts'], value['token_counts'])
