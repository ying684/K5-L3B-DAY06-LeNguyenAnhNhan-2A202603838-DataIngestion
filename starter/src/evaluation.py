"""Conservative evidence matching; manual labels remain a separate task."""
import re
import unicodedata
from collections import defaultdict


def comparable(text):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFC',text)).strip()


def golds(question):
    return question.get('gold_evidence') or [{'source_id':question['gold_source_id'],
            'page':question['gold_page'],'quote':question['evidence_quote']}]


def evaluate_query(question,hits):
    matches=[]
    for hit in hits[:3]:
        matches.append(any(hit['document_id']==g['source_id'] and hit['page']==g['page']
                  and comparable(g['quote']) in comparable(hit['text']) for g in golds(question)))
    return {'question_id':question['id'],'split':question['split'],'question':question['question'],
            'expected_answer':question['expected_answer'],'gold_evidence':golds(question),
            'requested_filter':question.get('filter',{}),'hits':hits,'evidence_matches':matches,
            'hit1':bool(matches and matches[0]),'hit3':any(matches)}


def summarize(traces):
    groups=defaultdict(list)
    for t in traces: groups[(t['strategy'],t['split'])].append(t)
    return [{'strategy':s,'split':split,'n':len(rows),'hit1_n':sum(t['hit1'] for t in rows),
             'hit3_n':sum(t['hit3'] for t in rows),'hit1':sum(t['hit1'] for t in rows)/len(rows),
             'hit3':sum(t['hit3'] for t in rows)/len(rows)} for (s,split),rows in sorted(groups.items())]
