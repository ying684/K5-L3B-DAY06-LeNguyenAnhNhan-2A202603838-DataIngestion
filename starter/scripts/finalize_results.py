"""Consolidate existing runs and audits offline; never call an API or rerun retrieval."""
import csv
import json
import sys
from pathlib import Path
from collections import Counter
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'starter'))
from src.run import snapshot
from src.evaluation import evaluate_query, summarize


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows, fields=None):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    runs = []
    failures = []
    traces = []
    questions = {q['id']: q for q in read_json(ROOT / 'benchmark/questions.json')}
    current = snapshot()
    for folder in sorted((ROOT / 'starter/results/runs').iterdir()):
        if not folder.is_dir():
            continue
        run = read_json(folder / 'run.json')
        run['path'] = folder.relative_to(ROOT).as_posix()
        if run['status'] != 'complete':
            failures.append({'path': run['path'], 'status': run['status'],
                             'error': run.get('error'), 'cost_usd': run.get('billed_cost_usd_reported')})
            continue
        if run['snapshot'] != current:
            raise ValueError('Completed run no longer matches frozen code/corpus: ' + run['path'])
        rows = [json.loads(line) for line in (folder / run['trace']).read_text(encoding='utf-8').splitlines()]
        for row in rows:
            recalculated = evaluate_query(questions[row['question_id']], row['hits'])
            if any(row[k] != recalculated[k] for k in ['hit1', 'hit3', 'evidence_matches']):
                raise ValueError('Trace metric mismatch')
            if len(row['hits']) != 3:
                raise ValueError('Expected three retrieved records')
        if summarize(rows) != read_json(folder / 'summary.json'):
            raise ValueError('Run summary mismatch')
        runs.append(run)
        traces.extend(rows)
    if len(runs) != 2 or {r['split'] for r in runs} != {'dev', 'test'}:
        raise ValueError('Expected exactly one complete dev run and one complete test run')
    keys = [(t['strategy'], t['question_id']) for t in traces]
    if len(keys) != 60 or len(set(keys)) != 60:
        raise ValueError('Incomplete or duplicate traces')
    dev = next(r for r in runs if r['split'] == 'dev')
    test = next(r for r in runs if r['split'] == 'test')
    selection = read_json(ROOT / 'artifacts/dev_selection.json')
    if not dev['finished_at'] <= selection['selected_at'] <= test['started_at']:
        # Selection is written immediately before dev run finished_at; allow that order.
        if not dev['started_at'] <= selection['selected_at'] <= dev['finished_at'] <= test['started_at']:
            raise ValueError('Selection chronology invalid')
    metrics = summarize(traces)
    for row in metrics:
        strategy = row['strategy']
        row['chunks'] = dev['ingestion'][strategy]['chunks']
        row['retrieval_seconds'] = sum(t['retrieval_seconds'] for t in traces
                                       if t['strategy'] == strategy and t['split'] == row['split'])
    write_csv(ROOT / 'starter/results/summary.csv', metrics)
    logs = csv_rows(ROOT / 'artifacts/experiment_log.csv')
    for row in logs:
        s = row['strategy']
        for split in ['dev', 'test']:
            metric = next(m for m in metrics if m['strategy'] == s and m['split'] == split)
            row[split + '_hit1'] = f"{metric['hit1_n']}/{metric['n']}"
            row[split + '_hit3'] = f"{metric['hit3_n']}/{metric['n']}"
        row['notes'] = ('Measured in frozen complete runs; audit labels recorded with reviewer provenance. ' +
                        ('A-B changes method, size and overlap.' if s in ['A', 'B'] else
                         'B-C changes only filter; shares B embedding vectors and cache.'))
    write_csv(ROOT / 'artifacts/experiment_log.csv', logs)
    audits = {}
    for strategy in ['A', 'B', 'C']:
        result = {}
        for filename in ['coherence', 'grounding', 'metadata']:
            rows = [r for r in csv_rows(ROOT / f'starter/results/audit/{filename}.csv')
                    if r['strategy'] == strategy]
            if filename in ['coherence', 'grounding']:
                recorded = [int(r['label']) for r in rows if r.get('label', '').strip()]
                if any(v not in [0, 1, 2] for v in recorded):
                    raise ValueError('Audit labels must be 0, 1 or 2')
                result[filename] = {'n': len(rows), 'recorded_labeled_n': len(recorded),
                                    'recorded_mean': sum(recorded) / len(recorded) if recorded else None,
                                    'recorded_counts_0_1_2': [recorded.count(i) for i in range(3)],
                                    'reviewers': dict(Counter(r['reviewer'] for r in rows if r.get('label', '').strip()))}
            else:
                recorded = [r for r in rows if r.get('correct_and_complete', '').strip()]
                result[filename] = {'n': len(rows), 'recorded_labeled_n': len(recorded),
                    'recorded_correct_n': sum(r['correct_and_complete'] == '1' for r in recorded),
                    'reviewers': dict(Counter(r['reviewer'] for r in recorded))}
        filtered = [t for t in traces if t['strategy'] == strategy and t['split'] == 'test' and t['requested_filter']]
        result['test_filter_from_trace'] = {
            'compliant_n': sum(all(all(h['metadata'].get(k) == v for k, v in t['requested_filter'].items())
                                   for h in t['hits']) for t in filtered), 'n': len(filtered),
            'note': 'Automated trace check; A/B do not apply a filter even when retrieved records happen to comply.'}
        audits[strategy] = result
    usage = [u for run in runs for u in run['api_usage']]
    result = {'snapshot': current, 'selection': selection['strategy'], 'retrieval': metrics,
              'trace_count': len(traces), 'retrieved_records': sum(len(t['hits']) for t in traces),
              'complete_run_paths': [r['path'] for r in runs], 'failed_attempts': failures,
              'successful_usage': {'requests': len(usage), 'inputs': sum(u['inputs'] for u in usage),
                  'total_tokens': sum(u['usage']['total_tokens'] for u in usage),
                  'provider_reported_usd': str(sum((Decimal(str(u['usage']['cost'])) for u in usage), Decimal('0'))),
                  'excludes_unknown_failed_attempt_cost': True},
              'audit': audits}
    (ROOT / 'starter/results/consolidated.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
