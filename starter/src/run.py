"""Run from starter/: python -m src.run prepare|dev|test|audit."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from pypdf import PdfReader
from .chunking import fixed_size, by_paragraph
from .embeddings import MyEmbedder
from .evaluation import comparable, golds, evaluate_query, summarize
from .ingestion import load_pdf
from .store import PgVectorStore

ROOT=Path(__file__).resolve().parents[2]
SOURCE='starter/data/raw/book_ML_color.pdf'
DOC='mlcb-20180327'
MODEL='baai/bge-m3'
STRATEGIES={'A':{'chunking':'fixed','size':500,'overlap':50,'filter':False},
            'B':{'chunking':'paragraph','size':1000,'overlap':0,'filter':False},
            'C':{'chunking':'paragraph','size':1000,'overlap':0,'filter':True}}
CHAPTERS={5:(78,82,'Các khái niệm cơ bản'),6:(83,94,'Giới thiệu về feature engineering'),
          7:(95,102,'Linear regression'),8:(103,109,'Overfitting')}


def now():
    # Fixed UTC+07 fallback avoids requiring tzdata on Windows.
    from datetime import timezone,timedelta
    return datetime.now(timezone(timedelta(hours=7))).isoformat()


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')


def read_json(path): return json.loads(path.read_text(encoding='utf-8'))


def corpus():
    pages=load_pdf(ROOT/SOURCE,DOC,SOURCE,list(range(78,110)))
    for page in pages:
        chapter=next(c for c,(first,last,_) in CHAPTERS.items() if first<=page.page<=last)
        page.metadata={'chapter':chapter,'chapter_title':CHAPTERS[chapter][2],
                       'language':'vi','printed_page':page.page-12,'snapshot':'2018-03-27'}
    if len(pages)<30: raise ValueError('Corpus needs at least 30 selected content pages')
    return pages


def chunks_for(pages):
    a=[c for p in pages for c in fixed_size(p,500,50)]
    b=[c for p in pages for c in by_paragraph(p,1000)]
    return {'A':a,'B':b,'C':b}


def benchmark(pages):
    questions=read_json(ROOT/'benchmark/questions.json')
    if len({q['id'] for q in questions})!=len(questions): raise ValueError('Duplicate question IDs')
    if sum(q['split']=='dev' for q in questions)<15 or sum(q['split']=='test' for q in questions)<5:
        raise ValueError('Need at least 15 dev and 5 test questions')
    if sum(bool(q.get('filter')) for q in questions)<3 or not any(q.get('filter') and q['split']=='test' for q in questions):
        raise ValueError('Need >=3 filters including one test filter')
    by_page={p.page:p for p in pages}
    for q in questions:
        if q['split'] not in ('dev','test'): raise ValueError('Invalid split')
        for g in golds(q):
            page=by_page[g['page']]
            if g['source_id']!=page.document_id or comparable(g['quote']) not in comparable(page.text):
                raise ValueError(f"Gold evidence absent: {q['id']}, page {g['page']}")
            if any(page.metadata.get(k)!=v for k,v in q.get('filter',{}).items()):
                raise ValueError(f"Filter contradicts evidence: {q['id']}")
    return questions


def fingerprint():
    files=sorted((ROOT/'starter/src').glob('*.py'))+[ROOT/'benchmark/questions.json',ROOT/'artifacts/protocol.json']
    return hashlib.sha256(''.join(str(p.relative_to(ROOT))+digest(p) for p in files).encode()).hexdigest()


def snapshot():
    return {'corpus_sha256':digest(ROOT/SOURCE),'code_benchmark_protocol_sha256':fingerprint(),
            'model':MODEL,'dimensions':1024,'strategies':STRATEGIES,'cosine_search':'exact','top_k':3}


def prepare():
    pages=corpus(); questions=benchmark(pages); groups=chunks_for(pages)
    protocol={'created_at':now(),'model':MODEL,'dimensions':1024,'strategies':STRATEGIES,
              'selection_rule':'Max dev Hit@3, then dev Hit@1, then fewer chunks, then alphabetical strategy ID',
              'split_rule':'dev: concepts/feature engineering/linear regression; test: Overfitting (chapter 8)',
              'leakage_limit':'Same book and related topics; test questions authored by same AI assistant. No test retrieval used for tuning.',
              'evidence_metric':'Same source+physical page and entire normalized evidence quote in one chunk; any declared alternative accepted',
              'coherence_positions':[{'page':p.page,'offset':len(p.text)//2} for p in pages[:10]],
              'manual_labels':'Author must review source, chunks and top-3; labels start blank. AI suggestions are not human audit.',
              'api_batch_size':16,'automatic_retries':0,'judge':'none'}
    protocol_path=ROOT/'artifacts/protocol.json'
    if protocol_path.exists():
        existing=read_json(protocol_path)
        protocol['created_at']=existing['created_at']
        if existing!=protocol: raise ValueError('Protocol already frozen; do not overwrite experimental design')
    else: write_json(protocol_path,protocol)
    manifest={'source_id':DOC,'title':'Machine Learning cơ bản','author':'Vũ Hữu Tiệp',
              'source_path_or_url':SOURCE,'original_url':'https://machinelearningcoban.com/ebook/',
              'license_or_permission':'User attests permitted processing in conversation; no independent written permission supplied. Copyright terms at physical page 9.',
              'permission_evidence':'User statement: hợp lệ hết khỏi lo; external API processing and redistribution terms not independently verified',
              'accessed_at':now(),'snapshot':'2018-03-27','sha256':digest(ROOT/SOURCE),'physical_pages':len(PdfReader(ROOT/SOURCE).pages),
              'counted_content_pages':len(pages),'counting_rule':'Physical PDF pages 78-109 inclusive, substantive chapters 5-8; no cover, TOC, blank or references-only pages. No character threshold used for PDF.',
              'excluded_scope':'All other physical pages excluded intentionally; not an extraction failure.',
              'metadata_types':{'chapter':'integer from chapter headings','printed_page':'integer, physical page minus 12 for selected range','language':'vi, observed source language'},
              'pages':[{'page':p.page,'characters':len(p.text),**p.metadata} for p in pages]}
    write_json(ROOT/'data/manifest.json',manifest)
    jsonl(ROOT/'starter/results/prepared/pages.jsonl',[asdict(p) for p in pages])
    stats={}
    for strategy,chunks in groups.items():
        jsonl(ROOT/f'starter/results/prepared/chunks_{strategy}.jsonl',[asdict(c) for c in chunks])
        sizes=[len(c.text) for c in chunks]
        stats[strategy]={'chunk_count':len(chunks),'characters':sum(sizes),'min':min(sizes),
                         'median':statistics.median(sizes),'max':max(sizes),'mean':statistics.mean(sizes)}
        for c in chunks:
            p=next(p for p in pages if p.page==c.page)
            if p.text[c.metadata['start_char']:c.metadata['end_char']]!=c.text: raise ValueError('Bad chunk offsets')
        for p in pages:
            covered=set()
            for c in chunks:
                if c.page==p.page: covered.update(range(c.metadata['start_char'],c.metadata['end_char']))
            if any(i not in covered for i,char in enumerate(p.text) if not char.isspace()):
                raise ValueError(f'Lost source characters in {strategy}, page {p.page}')
    embedder=MyEmbedder(MODEL,ROOT/'starter/.cache/embeddings')
    inputs=[c.text for s in ('A','B') for c in groups[s]]+[q['question'] for q in questions]
    query_calls=sum((embedder.missing([q['question'] for q in questions if q['split']==split])+15)//16
                    for split in ('dev','test'))
    plan={'timestamp':now(),'snapshot':snapshot(),'pages':len(pages),'questions':len(questions),
          'evidence_validation':'all evidence quotes found in selected normalized pages','stats':stats,
          'unique_inputs':len(set(inputs)),'uncached_inputs':embedder.missing(inputs),
          'input_characters_unique':sum(len(t) for t in set(inputs)),
          'api_calls_estimate':sum((embedder.missing([c.text for c in groups[s]])+15)//16 for s in ('A','B'))+query_calls,
          'cost':'No API called in prepare. Exact token count/cost unknown until provider returns usage.'}
    write_json(ROOT/'starter/results/prepared/plan.json',plan)
    print(json.dumps(plan,ensure_ascii=False,indent=2))


def run_split(split,allow_api):
    pages=corpus(); questions=benchmark(pages); groups=chunks_for(pages)
    plan=read_json(ROOT/'starter/results/prepared/plan.json')
    if snapshot()!=plan['snapshot']: raise ValueError('Prepared design changed; re-review before running')
    root=ROOT/'starter/results/runs'; root.mkdir(parents=True,exist_ok=True)
    dev_path=ROOT/'artifacts/dev_selection.json'
    if split=='test':
        selection=read_json(dev_path)
        if selection['snapshot']!=snapshot(): raise ValueError('Code/config changed after dev selection')
    # Preserve all attempts; prohibit casually rerunning scored questions.
    if any((r/f'traces_{split}.jsonl').exists() for r in root.iterdir() if r.is_dir()):
        raise RuntimeError(f'{split} already scored. Review history; do not rerun to select a better score.')
    run_dir=root/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+split)
    run_dir.mkdir()
    embedder=MyEmbedder(MODEL,ROOT/'starter/.cache/embeddings',allow_api)
    store=PgVectorStore(os.environ['DATABASE_URL'],1024)
    info={'started_at':now(),'split':split,'snapshot':snapshot(),'status':'running',
          'versions':{'python':platform.python_version(),**{m:importlib.metadata.version(m) for m in ['pypdf','psycopg','python-dotenv']}},
          'judge':'none','trace':f'traces_{split}.jsonl','ingestion':{},'query_seconds':{},'api_usage':[]}
    write_json(run_dir/'run.json',info)
    traces=[]
    try:
        store.create_schema()
        if split=='dev':
            for strategy,chunks in groups.items():
                begin=time.perf_counter(); prior=len(embedder.usage)
                vectors=embedder.embed_documents([c.text for c in chunks])
                store.upsert(strategy,chunks,vectors)
                count1=store.count(strategy)
                store.upsert(strategy,chunks,vectors)
                count2=store.count(strategy)
                if count1!=len(chunks) or count2!=count1: raise ValueError('Re-ingest duplicates/count mismatch')
                info['ingestion'][strategy]={'seconds_including_repeat':time.perf_counter()-begin,
                     'chunks':len(chunks),'count_after_first':count1,'count_after_repeat':count2,
                     'paid_batches':len(embedder.usage)-prior,'vectors_reused_from_B':strategy=='C'}
                write_json(run_dir/'run.json',{**info,'api_usage':embedder.usage})
        split_questions=[q for q in questions if q['split']==split]
        question_vectors=embedder.embed_documents([q['question'] for q in split_questions])
        for q,vector in zip(split_questions,question_vectors):
            for strategy in STRATEGIES:
                start=time.perf_counter()
                actual_filter=q.get('filter',{}) if strategy=='C' else {}
                hits=store.search(strategy,vector,3,actual_filter)
                trace=evaluate_query(q,hits)
                trace.update({'strategy':strategy,'applied_filter':actual_filter,'retrieval_seconds':time.perf_counter()-start})
                traces.append(trace)
                jsonl(run_dir/f'traces_{split}.jsonl',traces)
                print(f"{split} {q['id']} {strategy}: Hit@1={int(trace['hit1'])}, Hit@3={int(trace['hit3'])}",flush=True)
        summary=summarize(traces)
        write_json(run_dir/'summary.json',summary)
        if split=='dev':
            ranked=sorted(summary,key=lambda r:(-r['hit3'],-r['hit1'],len(groups[r['strategy']]),r['strategy']))
            write_json(dev_path,{'selected_at':now(),'strategy':ranked[0]['strategy'],'rule':read_json(ROOT/'artifacts/protocol.json')['selection_rule'],
                                 'snapshot':snapshot(),'dev_run':str(run_dir.relative_to(ROOT)),'metrics':summary})
        info['status']='complete'; info['summary']=summary
    except Exception as e:
        info['status']='failed'; info['error_type']=type(e).__name__
        info['error']=str(e) if not isinstance(e,(__import__('psycopg').Error,)) else 'Database operation failed (details omitted to protect connection credentials)'
        raise
    finally:
        info['finished_at']=now(); info['api_usage']=embedder.usage; info['cache_hits']=embedder.cache_hits
        info['billed_cost_usd_reported']=sum(x['usage']['cost'] for x in embedder.usage if isinstance(x.get('usage',{}).get('cost'),(int,float))) if embedder.usage and all(isinstance(x.get('usage',{}).get('cost'),(int,float)) for x in embedder.usage) else None
        write_json(run_dir/'run.json',info)


def audit():
    pages=corpus(); groups=chunks_for(pages)
    positions=read_json(ROOT/'artifacts/protocol.json')['coherence_positions']
    folder=ROOT/'starter/results/audit'; folder.mkdir(parents=True,exist_ok=True)
    def seed_csv(name,rows,fields):
        path=folder/name
        if path.exists(): return
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    coherence=[]
    for strategy,chunks in groups.items():
        for position in positions:
            candidates=[c for c in chunks if c.page==position['page'] and c.metadata['start_char']<=position['offset']<c.metadata['end_char']]
            chunk=min(candidates,key=lambda c:c.metadata['start_char'])
            coherence.append({'strategy':strategy,'page':chunk.page,'offset':position['offset'],
                              'chunk_id':chunk.chunk_id,'text':chunk.text,'label':'','reason':'','reviewer':''})
    seed_csv('coherence.csv',coherence,['strategy','page','offset','chunk_id','text','label','reason','reviewer'])
    traces=[]
    for file in sorted((ROOT/'starter/results/runs').glob('*/traces_test.jsonl')):
        traces += [json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
    ground=[]; meta=[]
    for trace in traces:
        ground.append({'strategy':trace['strategy'],'question_id':trace['question_id'],
                       'question':trace['question'],'top3':json.dumps(trace['hits'],ensure_ascii=False),
                       'label':'','reason':'','reviewer':''})
        for rank,hit in enumerate(trace['hits'],1):
            meta.append({'strategy':trace['strategy'],'question_id':trace['question_id'],'rank':rank,
                         'chunk_id':hit['chunk_id'],'source':hit['source'],'page':hit['page'],
                         'metadata':json.dumps(hit['metadata'],ensure_ascii=False),
                         'requested_filter':json.dumps(trace['requested_filter'],ensure_ascii=False),
                         'correct_and_complete':'','filter_compliant':'','reason':'','reviewer':''})
    if ground: seed_csv('grounding.csv',ground,['strategy','question_id','question','top3','label','reason','reviewer'])
    if meta: seed_csv('metadata.csv',meta,['strategy','question_id','rank','chunk_id','source','page','metadata','requested_filter','correct_and_complete','filter_compliant','reason','reviewer'])
    print(f'Audit sheets prepared: coherence={len(coherence)}, grounding={len(ground)}, metadata={len(meta)}; manual labels remain blank.')


def main():
    load_dotenv(ROOT/'starter/.env')
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['prepare','dev','test','audit'])
    parser.add_argument('--allow-api',action='store_true',help='Explicitly permit paid OpenRouter requests')
    args=parser.parse_args()
    if os.getenv('EMBEDDING_MODEL',MODEL)!=MODEL: parser.error(f'Model must be frozen to {MODEL}')
    if args.stage=='prepare': prepare()
    elif args.stage=='audit': audit()
    else: run_split(args.stage,args.allow_api)


if __name__=='__main__': main()
