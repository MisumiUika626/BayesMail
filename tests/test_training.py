import json
import tempfile
import unittest
from pathlib import Path

from bayesmail import model, train
from bayesmail.model import MultinomialNaiveBayes, build_vocabulary, tokenize
from bayesmail.train import run_training, split_by_content_group


class TrainingApiTests(unittest.TestCase):
    def test_training_api_exists(self):
        self.assertTrue(hasattr(train, 'split_by_content_group'))
        self.assertTrue(hasattr(train, 'run_training'))
        self.assertTrue(hasattr(model, 'tokenize'))
        self.assertTrue(hasattr(model, 'build_vocabulary'))
        self.assertTrue(hasattr(model, 'MultinomialNaiveBayes'))


def record(identifier, label, group, subject='', body=''):
    return {'id': identifier, 'label': label, 'subject': subject, 'body': body,
            'content_group_id': group}


class GroupSplitTests(unittest.TestCase):
    def test_split_keeps_groups_together_and_is_reproducible(self):
        rows = []
        for label in ('ham', 'spam'):
            for number in range(10):
                group = f'{label}-{number}'
                rows.append(record(f'{group}-a', label, group, body=group))
                if number == 0:
                    rows.append(record(f'{group}-b', label, group, body=group))

        train, test = split_by_content_group(rows, test_fraction=0.2, seed=17)
        again = split_by_content_group(list(reversed(rows)), test_fraction=0.2, seed=17)

        train_groups = {row['content_group_id'] for row in train}
        test_groups = {row['content_group_id'] for row in test}
        self.assertFalse(train_groups & test_groups)
        self.assertEqual(len(test_groups), 4)
        self.assertEqual({row['label'] for row in test}, {'ham', 'spam'})
        self.assertEqual([row['id'] for row in train], [row['id'] for row in again[0]])
        self.assertEqual([row['id'] for row in test], [row['id'] for row in again[1]])

    def test_split_rejects_missing_or_cross_label_groups(self):
        with self.assertRaisesRegex(ValueError, 'content_group_id'):
            split_by_content_group([record('1', 'ham', '', body='x')])
        with self.assertRaisesRegex(ValueError, '多个标签'):
            split_by_content_group([
                record('1', 'ham', 'same', body='x'),
                record('2', 'spam', 'same', body='x'),
            ])


class VocabularyAndModelTests(unittest.TestCase):
    def test_vocabulary_is_fitted_only_from_training_documents(self):
        training = [
            record('1', 'ham', 'h1', subject='会议', body='project update'),
            record('2', 'spam', 's1', subject='优惠', body='limited offer'),
        ]
        vocabulary = build_vocabulary(training, min_document_frequency=1)

        self.assertIn('会', vocabulary)
        self.assertIn('project', vocabulary)
        self.assertNotIn('test-only', vocabulary)
        self.assertEqual(tokenize('ABC 中文 abc'), ['abc', '中', '文', 'abc'])

    def test_multinomial_naive_bayes_learns_and_round_trips(self):
        rows = [
            record('h1', 'ham', 'hg1', body='meeting project'),
            record('h2', 'ham', 'hg2', body='project update'),
            record('s1', 'spam', 'sg1', body='cheap offer'),
            record('s2', 'spam', 'sg2', body='cheap discount'),
        ]
        vocabulary = build_vocabulary(rows, min_document_frequency=1)
        model = MultinomialNaiveBayes.fit(rows, vocabulary, alpha=1.0)

        self.assertEqual(model.predict('project meeting'), 'ham')
        self.assertEqual(model.predict('cheap offer'), 'spam')
        restored = MultinomialNaiveBayes.from_dict(model.to_dict())
        self.assertEqual(restored.predict('cheap discount'), 'spam')

    def test_group_distribution_has_a_single_pass_interface(self):
        helper = getattr(train, '_group_distribution', None)
        self.assertIsNotNone(helper)

        class OneShotRecords:
            def __init__(self, rows):
                self.rows = rows
                self.iterations = 0

            def __iter__(self):
                self.iterations += 1
                if self.iterations > 1:
                    raise AssertionError('records were scanned more than once')
                return iter(self.rows)

        rows = OneShotRecords([record('1', 'ham', 'h'), record('2', 'ham', 'h'), record('3', 'spam', 's')])
        self.assertEqual(helper(rows), {'ham': 1, 'spam': 1})


class TrainingPipelineTests(unittest.TestCase):
    def test_pipeline_writes_auditable_non_overwriting_artifact(self):
        rows = []
        for label, word in (('ham', 'meeting'), ('spam', 'offer')):
            for number in range(10):
                rows.append(record(f'{label}-{number}', label, f'{label}-g{number}', body=f'{word} common'))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'cleaned.jsonl'
            source.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
            output = root / 'training'

            summary = run_training(source, output, test_fraction=0.2, seed=7,
                                   min_document_frequency=1)

            self.assertEqual(summary['content_groups'], {'all': 20, 'train': 16, 'test': 4})
            self.assertEqual(summary['records'], {'all': 20, 'train': 16, 'test': 4})
            self.assertEqual(json.loads((output / 'manifest.json').read_text())['state'], 'complete')
            self.assertTrue((output / 'vocabulary.json').is_file())
            self.assertTrue((output / 'model.json').is_file())
            train_groups = {json.loads(line)['content_group_id'] for line in (output / 'train.jsonl').read_text().splitlines()}
            test_groups = {json.loads(line)['content_group_id'] for line in (output / 'test.jsonl').read_text().splitlines()}
            self.assertFalse(train_groups & test_groups)
            with self.assertRaises(FileExistsError):
                run_training(source, output)


if __name__ == '__main__':
    unittest.main()
