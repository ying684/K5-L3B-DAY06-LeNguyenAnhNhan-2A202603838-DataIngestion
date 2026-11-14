"""Persistent storage, exact cosine search and parameterized JSON metadata filter."""
import math
import psycopg
from psycopg.types.json import Jsonb


class PgVectorStore:
    def __init__(self,database_url: str,dimensions: int) -> None:
        if not 1<=dimensions<=16000: raise ValueError('Invalid vector dimension')
        self.database_url=database_url; self.dimensions=dimensions

    def connect(self):
        return psycopg.connect(self.database_url,connect_timeout=5)

    def vector(self,values):
        if len(values)!=self.dimensions or not all(math.isfinite(v) for v in values) or not any(values):
            raise ValueError('Invalid vector')
        return '['+','.join(str(float(v)) for v in values)+']'

    def create_schema(self) -> None:
        with self.connect() as c:
            c.execute(f'''CREATE TABLE IF NOT EXISTS day6_chunks (
                strategy text NOT NULL, chunk_id text NOT NULL, document_id text NOT NULL,
                source text NOT NULL, page integer NOT NULL, text text NOT NULL,
                metadata jsonb NOT NULL, embedding vector({self.dimensions}) NOT NULL,
                PRIMARY KEY(strategy,chunk_id))''')
            row=c.execute("SELECT format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='day6_chunks'::regclass AND attname='embedding'").fetchone()
            if row[0]!=f'vector({self.dimensions})': raise ValueError('Existing table uses another dimension')

    def upsert(self,strategy,chunks,vectors) -> None:
        if len(chunks)!=len(vectors) or not chunks: raise ValueError('Chunks/vectors must be aligned and nonempty')
        rows=[(strategy,x.chunk_id,x.document_id,x.source,x.page,x.text,
               Jsonb({**x.metadata,'document_id':x.document_id,'source':x.source,'page':x.page}),self.vector(v))
              for x,v in zip(chunks,vectors)]
        with self.connect() as c:
            with c.cursor() as cursor:
                cursor.executemany('''INSERT INTO day6_chunks VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)
                    ON CONFLICT(strategy,chunk_id) DO UPDATE SET document_id=excluded.document_id,
                    source=excluded.source,page=excluded.page,text=excluded.text,
                    metadata=excluded.metadata,embedding=excluded.embedding''',rows)
            c.execute('DELETE FROM day6_chunks WHERE strategy=%s AND document_id=ANY(%s) AND NOT(chunk_id=ANY(%s))',
                      (strategy,sorted({x.document_id for x in chunks}),[x.chunk_id for x in chunks]))

    def count(self,strategy: str) -> int:
        with self.connect() as c:
            return c.execute('SELECT count(*) FROM day6_chunks WHERE strategy=%s',(strategy,)).fetchone()[0]

    def search(self,strategy,query_vector,top_k=3,filters=None):
        filters=filters or {}
        if set(filters)-{'chapter','language'}: raise ValueError('Unsupported metadata filter')
        if not 1<=top_k<=100: raise ValueError('Invalid top_k')
        vector=self.vector(query_vector)
        with self.connect() as c:
            rows=c.execute('''SELECT chunk_id,document_id,source,page,text,metadata,
                1-(embedding <=> %s::vector) AS score FROM day6_chunks
                WHERE strategy=%s AND metadata @> %s::jsonb
                ORDER BY embedding <=> %s::vector,chunk_id LIMIT %s''',
                (vector,strategy,Jsonb(filters),vector,top_k)).fetchall()
        return [dict(zip(('chunk_id','document_id','source','page','text','metadata','score'),r)) for r in rows]
