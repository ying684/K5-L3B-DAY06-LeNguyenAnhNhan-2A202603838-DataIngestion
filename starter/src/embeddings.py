"""OpenRouter embeddings with a content-addressed cache and no automatic retry."""
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


MODEL_RESPONSE_ALIASES={
    'baai/bge-m3':{'parasail-bge-m3'}
}


class MyEmbedder:
    def __init__(self, model_name: str, cache_dir: Path, allow_api: bool = False,
                 dimensions: int = 1024) -> None:
        self.model_name=model_name; self.dimensions=dimensions
        self.cache_dir=cache_dir; self.allow_api=allow_api
        self.usage=[]; self.cache_hits=0

    def _path(self,text: str) -> Path:
        key=hashlib.sha256((self.model_name+'|'+str(self.dimensions)+'|'+text).encode()).hexdigest()
        return self.cache_dir/(key+'.json')

    def _validate(self,vector):
        if len(vector)!=self.dimensions or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector):
            raise ValueError('Invalid embedding dimensions/values')
        if not any(vector): raise ValueError('Zero embedding is not permitted')
        return vector

    def missing(self,texts: list[str]) -> int:
        return len({text for text in texts if not self._path(text).exists()})

    def embed_documents(self,texts: list[str]) -> list[list[float]]:
        missing=list(dict.fromkeys(t for t in texts if not self._path(t).exists()))
        if missing and not self.allow_api:
            raise RuntimeError(f'{len(missing)} uncached inputs; API disabled. Explicitly pass --allow-api.')
        for start in range(0,len(missing),16):
            batch=missing[start:start+16]
            key=os.getenv('OPENROUTER_API_KEY')
            if not key: raise RuntimeError('OPENROUTER_API_KEY missing in local .env')
            payload={'model':self.model_name,'input':batch,'encoding_format':'float',
                     'provider':{'allow_fallbacks':False}}
            request=Request('https://openrouter.ai/api/v1/embeddings',data=json.dumps(payload).encode(),
                            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
            try:
                with urlopen(request,timeout=90) as response: data=json.load(response)
            except HTTPError as error:
                raise RuntimeError(f'OpenRouter HTTP {error.code}; no retry performed') from None
            except URLError:
                raise RuntimeError('OpenRouter network error; no retry performed') from None
            rows=sorted(data.get('data',[]),key=lambda row:row['index'])
            if len(rows)!=len(batch) or [row['index'] for row in rows]!=list(range(len(batch))):
                raise ValueError('Incomplete or duplicate embedding indices')
            returned_model=data.get('model')
            accepted_models={self.model_name.casefold()}|MODEL_RESPONSE_ALIASES.get(
                self.model_name.casefold(),set())
            if returned_model and (not isinstance(returned_model,str) or
                                   returned_model.casefold() not in accepted_models):
                raise ValueError(f'OpenRouter returned model {returned_model!r}, requested {self.model_name!r}')
            vectors=[self._validate(row['embedding']) for row in rows]
            self.usage.append({'model':self.model_name,'returned_model':returned_model,
                               'provider':data.get('provider'),
                               'inputs':len(batch),'usage':data.get('usage',{}),'request_id':data.get('id')})
            self.cache_dir.mkdir(parents=True,exist_ok=True)
            for text,vector in zip(batch,vectors):
                self._path(text).write_text(json.dumps(vector),encoding='utf-8')
        self.cache_hits += len(texts)-len(missing)
        return [self._validate(json.loads(self._path(t).read_text(encoding='utf-8'))) for t in texts]

    def embed_query(self,question: str) -> list[float]:
        return self.embed_documents([question])[0]
