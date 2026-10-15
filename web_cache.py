"""Ortak fiyat onbellegi ve gercek veri alma durum raporu."""
import hashlib,pickle,time,json,os,threading
from pathlib import Path
import pandas as pd

class DownloadReport:
    def __init__(self,path=None):
        self.path=Path(path) if path else None
        self.lock=threading.Lock();self.rows=[]
    def add(self,symbol,ok,cached=False,reason=''):
        with self.lock:
            self.rows.append({'HISSE':str(symbol),'DURUM':'VERI_ALINDI' if ok else 'VERI_ALINAMADI','ONBELLEK':cached,'HATA':str(reason)[:300]})
            if self.path:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                temp=self.path.with_suffix('.tmp')
                temp.write_text(json.dumps(self.summary(),ensure_ascii=False),encoding='utf-8');temp.replace(self.path)
                errors=pd.DataFrame([r for r in self.rows if r['DURUM']=='VERI_ALINAMADI'],columns=['HISSE','DURUM','ONBELLEK','HATA'])
                p=self.path.parent/'WEB_VERI_HATALARI.csv';tmp=p.with_suffix('.tmp')
                errors.to_csv(tmp,index=False,encoding='utf-8-sig');tmp.replace(p)
    def summary(self):
        success=sum(r['DURUM']=='VERI_ALINDI' for r in self.rows)
        return {'istek':len(self.rows),'basarili':success,'basarisiz':len(self.rows)-success,'onbellek':sum(r['ONBELLEK'] for r in self.rows)}

def usable(frame):
    if frame is None or frame.empty:return False
    columns=[c for c in frame if ('close' in [str(v).lower() for v in c] if isinstance(c,tuple) else str(c).lower()=='close')]
    return any((pd.to_numeric(frame[c],errors='coerce')>0).any() for c in columns)

def finish_state(rc,report):
    if rc==124:return 'Sure doldu'
    if rc:return 'Hata'
    if report.get('istek',0) and not report.get('basarili',0):return 'Veri alinamadi'
    if report.get('basarisiz',0):return 'Kismi'
    return 'Tamamlandi'

def install(root):
    import yfinance as yf
    original=yf.download
    if getattr(original,'_bist_cache_wrapper',False) is True:original=original._bist_original
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    report=DownloadReport(os.environ.get('BIST_JOB_REPORT'))
    def cached(*args,**kwargs):
        symbol=kwargs.get('tickers',args[0] if args else '?')
        key=hashlib.sha256(json.dumps([args,kwargs],sort_keys=True,default=str).encode()).hexdigest()
        path=root/(key+'.pkl');interval=kwargs.get('interval','1d');ttl=900 if interval=='1d' else 60
        if path.exists() and time.time()-path.stat().st_mtime<ttl:
            try:
                with path.open('rb') as f:value=pickle.load(f)
                if usable(value):report.add(symbol,True,True);return value
            except (OSError,pickle.UnpicklingError,EOFError):pass
        try:result=original(*args,**kwargs)
        except Exception as exc:
            report.add(symbol,False,reason=f'{type(exc).__name__}: {exc}');raise
        valid=usable(result)
        report.add(symbol,valid,reason='' if valid else 'Kullanilabilir kapanis verisi donmedi; saglayici siniri veya sembol/veri sorunu olabilir.')
        if valid:
            temp=path.with_suffix('.tmp')
            with temp.open('wb') as f:pickle.dump(result,f)
            temp.replace(path)
        return result
    cached._bist_cache_wrapper=True;cached._bist_original=original
    yf.download=cached
    return report
