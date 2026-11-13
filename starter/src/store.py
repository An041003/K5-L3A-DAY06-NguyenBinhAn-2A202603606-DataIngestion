"""Persistent pgvector exact cosine search and transactional source replacement."""
import json
import psycopg
from psycopg.types.json import Jsonb
from .embeddings import MODEL, validate_vector


class PgVectorStore:
    def __init__(self,database_url,dimensions=768):
        if dimensions!=768:
            raise ValueError('Expected 768 dimensions')
        self.url,self.dimensions = database_url,dimensions

    def connect(self):
        return psycopg.connect(self.url,connect_timeout=5)

    def create_schema(self):
        with self.connect() as conn:
            conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
            conn.execute('''CREATE TABLE IF NOT EXISTS day06_chunks (
                strategy text NOT NULL CHECK (strategy IN ('A','B')), chunk_id text NOT NULL,
                document_id text NOT NULL, source text NOT NULL, page integer NOT NULL,
                text text NOT NULL, metadata jsonb NOT NULL, model text NOT NULL,
                embedding vector(768) NOT NULL, PRIMARY KEY(strategy,chunk_id))''')

    def upsert(self,strategy,chunks,vectors):
        if strategy not in ('A','B') or not chunks or len(chunks)!=len(vectors):
            raise ValueError('Invalid strategy or chunk/vector count')
        if len({c.chunk_id for c in chunks})!=len(chunks):
            raise ValueError('Duplicate chunk IDs')
        for vector in vectors:
            validate_vector(vector)
        with self.connect() as conn:
            conn.execute('LOCK TABLE day06_chunks IN SHARE ROW EXCLUSIVE MODE')
            for document in sorted({c.document_id for c in chunks}):
                ids = [c.chunk_id for c in chunks if c.document_id==document]
                conn.execute('DELETE FROM day06_chunks WHERE strategy=%s AND document_id=%s AND NOT (chunk_id=ANY(%s))',(strategy,document,ids))
            with conn.cursor() as cur:
                cur.executemany('''INSERT INTO day06_chunks VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                    ON CONFLICT(strategy,chunk_id) DO UPDATE SET text=excluded.text, metadata=excluded.metadata,
                    embedding=excluded.embedding,model=excluded.model,source=excluded.source,page=excluded.page''',
                    [(strategy,c.chunk_id,c.document_id,c.source,c.page,c.text,Jsonb(c.metadata),MODEL,json.dumps(v)) for c,v in zip(chunks,vectors)])

    def snapshot(self,strategy):
        with self.connect() as conn:
            return [r[0] for r in conn.execute('SELECT chunk_id FROM day06_chunks WHERE strategy=%s ORDER BY chunk_id',(strategy,))]

    def versions(self):
        with self.connect() as conn:
            row=conn.execute("SELECT current_setting('server_version'),extversion FROM pg_extension WHERE extname='vector'").fetchone()
            return {'postgresql':row[0],'pgvector':row[1],'search':'exact cosine; no ANN index'}

    def search(self,strategy,query_vector,top_k=3,filters=None):
        if strategy not in ('A','B','C') or not 1<=top_k<=100:
            raise ValueError('Invalid strategy/top_k')
        validate_vector(query_vector)
        conditions,args=['strategy=%s','model=%s'],['B' if strategy=='C' else strategy,MODEL]
        for field,value in (filters or {}).items():
            if field!='section' or not isinstance(value,str) or not value:
                raise ValueError('Only source-proven section string filters allowed')
            conditions.append('metadata->>%s=%s')
            args.extend([field,value])
        vec=json.dumps(query_vector)
        query='''SELECT chunk_id,document_id,source,page,text,metadata,1-(embedding <=> %s::vector)
            FROM day06_chunks WHERE '''+' AND '.join(conditions)+' ORDER BY embedding <=> %s::vector,chunk_id LIMIT %s'
        with self.connect() as conn:
            rows=conn.execute(query,[vec,*args,vec,top_k]).fetchall()
        return [dict(zip(['chunk_id','document_id','source','page','text','metadata','score'],row)) for row in rows]
