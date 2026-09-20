"""Leakage-safe grouped split, vocabulary fitting, and model training."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

from .artifacts import (
    artifact_hashes,
    read_jsonl,
    sha256_file,
    utc_now,
    write_json,
    write_jsonl,
)
from .model import MultinomialNaiveBayes, build_vocabulary


def _seed_for_label(seed, label):
    raw = f'{seed}:{label}'.encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], 'big')


def split_by_content_group(records, test_fraction=0.2, seed=20260920):
    """Stratify groups by label while keeping every group in one split."""
    if not 0 < test_fraction < 1:
        raise ValueError('test_fraction 必须在 0 和 1 之间')
    records = list(records)
    if not records:
        raise ValueError('记录不能为空')
    groups = defaultdict(list)
    for record in records:
        group = record.get('content_group_id')
        if not group:
            raise ValueError(f"{record.get('id', '<unknown>')}: 缺少 content_group_id")
        if record.get('label') not in ('ham', 'spam'):
            raise ValueError(f"{record.get('id', '<unknown>')}: label 必须是 ham 或 spam")
        groups[group].append(record)
    groups_by_label = defaultdict(list)
    for group, members in groups.items():
        labels = {member['label'] for member in members}
        if len(labels) != 1:
            raise ValueError(f'内容组 {group} 包含多个标签')
        groups_by_label[next(iter(labels))].append(group)
    test_groups = set()
    for label, label_groups in sorted(groups_by_label.items()):
        if len(label_groups) < 2:
            raise ValueError(f'{label} 至少需要两个内容组')
        label_groups.sort()
        random.Random(_seed_for_label(seed, label)).shuffle(label_groups)
        count = max(1, min(len(label_groups) - 1,
                           round(len(label_groups) * test_fraction)))
        test_groups.update(label_groups[:count])
    training = sorted(
        (record for record in records if record['content_group_id'] not in test_groups),
        key=lambda record: record['id'])
    test = sorted(
        (record for record in records if record['content_group_id'] in test_groups),
        key=lambda record: record['id'])
    return training, test


def _distribution(records, key):
    return dict(sorted(Counter(record[key] for record in records).items()))


def _group_distribution(records):
    labels_by_group = {}
    for record in records:
        group = record['content_group_id']
        label = record['label']
        if group in labels_by_group and labels_by_group[group] != label:
            raise ValueError(f'内容组 {group} 包含多个标签')
        labels_by_group[group] = label
    return dict(sorted(Counter(labels_by_group.values()).items()))


def run_training(source, output, test_fraction=0.2, seed=20260920,
                 min_document_frequency=2, max_features=None, alpha=1.0):
    source = Path(source).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    rows = read_jsonl(source)
    training, test = split_by_content_group(rows, test_fraction, seed)
    vocabulary = build_vocabulary(training, min_document_frequency, max_features)
    model = MultinomialNaiveBayes.fit(training, vocabulary, alpha)

    all_groups = {record['content_group_id'] for record in rows}
    training_groups = {record['content_group_id'] for record in training}
    test_groups = {record['content_group_id'] for record in test}
    if training_groups & test_groups:
        raise AssertionError('训练集与测试集存在内容组泄漏')
    summary = {
        'records': {'all': len(rows), 'train': len(training), 'test': len(test)},
        'content_groups': {'all': len(all_groups), 'train': len(training_groups),
                           'test': len(test_groups)},
        'records_by_label': {
            'all': _distribution(rows, 'label'),
            'train': _distribution(training, 'label'),
            'test': _distribution(test, 'label'),
        },
        'groups_by_label': {'train': _group_distribution(training),
                            'test': _group_distribution(test)},
        'test_fraction': test_fraction,
        'seed': seed,
        'vocabulary_size': len(vocabulary),
        'min_document_frequency': min_document_frequency,
        'max_features': max_features,
        'alpha': alpha,
        'tokenizer': 'lowercase_ascii_terms_and_single_cjk_characters',
    }

    output.mkdir(parents=True)
    manifest = {
        'state': 'in_progress', 'started_utc': utc_now(),
        'source': str(source), 'source_sha256': sha256_file(source),
        'parameters': {key: summary[key] for key in
                       ('test_fraction', 'seed', 'min_document_frequency',
                        'max_features', 'alpha')},
    }
    write_json(output / 'manifest.json', manifest)
    write_jsonl(output / 'train.jsonl', training)
    write_jsonl(output / 'test.jsonl', test)
    write_json(output / 'vocabulary.json',
               sorted(vocabulary, key=vocabulary.get))
    write_json(output / 'model.json', model.to_dict())
    write_json(output / 'summary.json', summary)
    artifact_names = ('train.jsonl', 'test.jsonl', 'vocabulary.json',
                      'model.json', 'summary.json')
    manifest.update(
        state='complete', finished_utc=utc_now(),
        artifact_sha256=artifact_hashes(output, artifact_names))
    write_json(output / 'manifest.json', manifest)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description='按内容组划分数据，仅用训练集建立词表并训练朴素贝叶斯')
    parser.add_argument('source', type=Path,
                        help='清洗验证后的 cleaned.jsonl')
    parser.add_argument('--output', type=Path,
                        default=Path('reports/training_v1'))
    parser.add_argument('--test-fraction', type=float, default=0.2)
    parser.add_argument('--seed', type=int, default=20260920)
    parser.add_argument('--min-document-frequency', type=int, default=2)
    parser.add_argument('--max-features', type=int)
    parser.add_argument('--alpha', type=float, default=1.0)
    args = parser.parse_args()
    try:
        summary = run_training(
            args.source, args.output, args.test_fraction, args.seed,
            args.min_document_frequency, args.max_features, args.alpha)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f'训练失败：{exc}\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'训练产物：{args.output}')


if __name__ == '__main__':
    main()
