"""Sunucuda ortak fiyat verisi onbellegi; bos/hata verisi saklanmaz."""
import hashlib,pickle,time,json
from pathlib import Path

def install(root):
    import yfinance as yf
    original=yf.download
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    def cached(*args,**kwargs):
        key=hashlib.sha256(json.dumps([args,kwargs],sort_keys=True,default=str).encode()).hexdigest()
        path=root/(key+'.pkl')
        interval=kwargs.get('interval','1d');ttl=900 if interval=='1d' else 60
        if path.exists() and time.time()-path.stat().st_mtime<ttl:
            try:
                with path.open('rb') as f:return pickle.load(f)
            except (OSError,pickle.UnpicklingError,EOFError):pass
        result=original(*args,**kwargs)
        if result is not None and not result.empty:
            temp=path.with_suffix('.tmp')
            with temp.open('wb') as f:pickle.dump(result,f)
            temp.replace(path)
        return result
    yf.download=cached
