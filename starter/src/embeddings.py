"""Real OpenRouter embeddings with private persistent cache and usage ledger."""
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from .io_utils import digest, write_json

MODEL = 'google/gemini-embedding-2'
DIMENSIONS = 768


def validate_vector(vector,dimensions=768):
    if not isinstance(vector,list) or len(vector)!=dimensions or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in vector):
        raise ValueError('Invalid embedding count/dimension/nonfinite values')
    if sum(v*v for v in vector)<=0:
        raise ValueError('Zero vector cannot support cosine similarity')


class MyEmbedder:
    def __init__(self,model_name=MODEL,cache_dir=None):
        self.model_name = model_name
        self.dimensions = int(os.getenv('EMBEDDING_DIMENSIONS','768'))
        if model_name!=MODEL or self.dimensions!=DIMENSIONS:
            raise ValueError('Locked model/dimensions violated')
        self.base = os.getenv('OPENROUTER_BASE_URL','https://openrouter.ai/api/v1').rstrip('/')
        if self.base!='https://openrouter.ai/api/v1':
            raise ValueError('Unexpected external endpoint')
        self.key = os.getenv('OPENROUTER_API_KEY','').strip()
        if not self.key:
            raise RuntimeError('BLOCKED:API_KEY')
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True,exist_ok=True)
        self.ledger = self.cache.parent/'api_usage.jsonl'
        self.session = requests.Session()

    def embed_documents(self,texts):
        if not texts:
            return []
        if any(not t.strip() or len(t.encode('utf-8'))>8192 for t in texts):
            raise ValueError('Empty input or conservative 8192-byte input ceiling exceeded')
        keys = [digest(f'{MODEL}|768|raw-text-v1|{text}') for text in texts]
        missing = {}
        for key,text in zip(keys,texts):
            if not (self.cache/(key+'.json')).exists():
                missing[key] = text
        pending = list(missing)
        for offset in range(0,len(pending),16):
            batch = pending[offset:offset+16]
            started = time.perf_counter()
            for attempt in range(3):
                try:
                    response = self.session.post(self.base+'/embeddings',headers={'Authorization':'Bearer '+self.key},
                        json={'model':MODEL,'dimensions':768,'input':[missing[k] for k in batch]},timeout=(10,90))
                except requests.RequestException:
                    raise RuntimeError('BLOCKED:API_NETWORK_UNCONFIRMED; explicit rerun required') from None
                if response.status_code in (429,503) and attempt<2:
                    time.sleep(2**attempt)
                    continue
                if response.status_code!=200:
                    raise RuntimeError(f'BLOCKED:API_HTTP_{response.status_code}')
                break
            payload = response.json()
            items = payload.get('data',[])
            if len(items)!=len(batch) or sorted(i.get('index',-1) for i in items)!=list(range(len(batch))):
                raise ValueError('Provider embedding index/count mismatch')
            record = {'at':datetime.now(timezone.utc).isoformat(),'model_requested':MODEL,
                'model_returned':payload.get('model'),'dimensions':768,'inputs':len(batch),
                'input_hashes':batch,'usage':payload.get('usage'),'seconds':time.perf_counter()-started,
                'request_id':payload.get('id'),'estimated_price_usd_per_million':0.20,'pricing_checked_date':'2026-11-13'}
            with self.ledger.open('a',encoding='utf-8') as f:
                f.write(json.dumps(record)+'\n')
            if payload.get('model') not in (MODEL,'gemini-embedding-2'):
                raise ValueError('Provider returned an unexpected model identity')
            for item in items:
                validate_vector(item['embedding'])
            for item in items:
                target = self.cache/(batch[item['index']]+'.json')
                temporary = target.with_suffix('.tmp')
                write_json(temporary,item['embedding'])
                temporary.replace(target)
            print(f'Embedded batch {offset+len(batch)}/{len(pending)} new inputs',flush=True)
        vectors = [json.loads((self.cache/(k+'.json')).read_text(encoding='utf-8')) for k in keys]
        for vector in vectors:
            validate_vector(vector)
        return vectors

    def embed_query(self,question):
        return self.embed_documents([question])[0]
