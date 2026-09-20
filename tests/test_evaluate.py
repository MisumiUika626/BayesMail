import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from bayesmail.model import MultinomialNaiveBayes, build_vocabulary
from bayesmail.evaluate import evaluate_records, run_evaluation


class EvaluationApiTests(unittest.TestCase):
    def test_evaluation_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('bayesmail.evaluate'))


def row(identifier, label, text):
    return {'id': identifier, 'label': label, 'subject': '', 'body': text,
            'content_group_id': identifier}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        training = [
            row('h1', 'ham', 'meeting project'),
            row('h2', 'ham', 'meeting update'),
            row('s1', 'spam', 'cheap offer'),
            row('s2', 'spam', 'cheap discount'),
        ]
        vocabulary = build_vocabulary(training, min_document_frequency=1)
        self.model = MultinomialNaiveBayes.fit(training, vocabulary)

    def test_metrics_use_spam_as_positive_class(self):
        records = [
            row('1', 'ham', 'meeting'),
            row('2', 'ham', 'cheap'),
            row('3', 'spam', 'offer'),
            row('4', 'spam', 'project'),
        ]

        report, mistakes = evaluate_records(records, self.model)

        self.assertEqual(report['confusion_matrix'], {
            'true_ham_pred_ham': 1,
            'true_ham_pred_spam': 1,
            'true_spam_pred_ham': 1,
            'true_spam_pred_spam': 1,
        })
        self.assertEqual(report['metrics'], {
            'accuracy': 0.5,
            'precision_spam': 0.5,
            'recall_spam': 0.5,
            'f1_spam': 0.5,
            'ham_false_positive_rate': 0.5,
        })
        self.assertEqual([item['id'] for item in mistakes], ['2', '4'])

    def test_pipeline_writes_report_and_mistakes_without_overwrite(self):
        records = [row('1', 'ham', 'meeting'), row('2', 'spam', 'offer')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test_path = root / 'test.jsonl'
            model_path = root / 'model.json'
            output = root / 'evaluation'
            test_path.write_text(''.join(json.dumps(item) + '\n' for item in records), encoding='utf-8')
            model_path.write_text(json.dumps(self.model.to_dict()), encoding='utf-8')

            report = run_evaluation(test_path, model_path, output)

            self.assertEqual(report['records'], 2)
            self.assertEqual(json.loads((output / 'manifest.json').read_text())['state'], 'complete')
            self.assertTrue((output / 'evaluation.json').is_file())
            self.assertTrue((output / 'misclassified.jsonl').is_file())
            with self.assertRaises(FileExistsError):
                run_evaluation(test_path, model_path, output)

    def test_rejects_empty_or_unknown_labels(self):
        with self.assertRaisesRegex(ValueError, '不能为空'):
            evaluate_records([], self.model)
        with self.assertRaisesRegex(ValueError, 'ham 或 spam'):
            evaluate_records([row('1', 'other', 'meeting')], self.model)


if __name__ == '__main__':
    unittest.main()
