"""Tek sunucuda paylasilan sira: motorlar birbirinin dosyalarini ezmez."""
import json,os,queue,subprocess,sys,threading,time,uuid,hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

class Jobs:
    def __init__(self,root=None):
        self.root=Path(root or Path(__file__).parent/'web_data');self.root.mkdir(parents=True,exist_ok=True)
        self.items={};self.lock=threading.RLock();self.queue=queue.Queue(maxsize=12)
        self.auto=False;self.auto_days=set();self.auto_done=set()
        threading.Thread(target=self._loop,daemon=True).start()
        threading.Thread(target=self._schedule,daemon=True).start()

    def submit(self,params,owner,secret_env=None):
        with self.lock:
            for job in self.items.values():
                if job['params']==params and job['state'] in ('Sirada','Calisiyor'):
                    job['owners'].add(owner);return job['id']
            if self.queue.full():raise ValueError('Tarama sirasi dolu. Biraz sonra tekrar deneyin.')
            if sum(owner in j['owners'] and j['state'] in ('Sirada','Calisiyor') for j in self.items.values())>=2:
                raise ValueError('En fazla iki aktif is baslatabilirsiniz.')
            if len(self.items)>=60:
                for jid in list(self.items):
                    if self.items[jid]['state'] not in ('Sirada','Calisiyor'):
                        expired=self.items.pop(jid)
                        import shutil
                        shutil.rmtree(expired['folder'],ignore_errors=True);break
            jid=uuid.uuid4().hex;folder=self.root/'jobs'/jid;folder.mkdir(parents=True)
            job={'id':jid,'params':dict(params),'owners':{owner},'state':'Sirada','folder':folder,'created':time.time(),'proc':None,'env':secret_env or {},'redactions':list((secret_env or {}).values()),'files':[]}
            self.items[jid]=job;self.queue.put(jid);return jid

    def get(self,jid):
        with self.lock:
            j=self.items.get(jid)
            return dict(j) if j else None

    def cancel(self,jid,owner,admin=False):
        with self.lock:
            j=self.items.get(jid)
            if not j or (owner not in j['owners'] and not admin):return False
            if len(j['owners'])>1 and not admin:
                j['owners'].discard(owner);return True
            j['state']='Durduruldu'
            if j['proc'] and j['proc'].poll() is None:j['proc'].terminate()
            return True

    def log(self,jid):
        j=self.get(jid)
        if not j:return ''
        p=j['folder']/'output.log'
        if not p.exists():return ''
        with p.open('rb') as f:
            f.seek(max(0,p.stat().st_size-24000));text=f.read().decode('utf-8',errors='replace')
        for value in j['redactions']:
            if value:text=text.replace(str(value),'[gizli]')
        return text

    def _loop(self):
        while True:
            jid=self.queue.get();j=self.items.get(jid)
            if not j or j['state']=='Durduruldu':self.queue.task_done();continue
            try:
                results=self.root/'results';results.mkdir(exist_ok=True)
                before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in results.glob('*.csv')}
                env=os.environ.copy();env.update(j['env']);env['BIST_RESULTS_DIR']=str(results.resolve());env['PYTHONUNBUFFERED']='1'
                with (j['folder']/'output.log').open('wb') as out:
                    cmd=[sys.executable,str(Path(__file__).parent/'web_worker.py'),'--params',json.dumps(j['params']),'--output',str(j['folder']/'sonuc.csv')]
                    with self.lock:
                        if j['state']=='Durduruldu':continue
                        j['proc']=subprocess.Popen(cmd,stdout=out,stderr=subprocess.STDOUT,env=env,cwd=Path(__file__).parent)
                        j['state']='Calisiyor';j['started']=time.time()
                    timeout=1800 if j['params']['scan'] in (17,23) else 10800
                    try:rc=j['proc'].wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        j['proc'].terminate()
                        try:j['proc'].wait(timeout=10)
                        except subprocess.TimeoutExpired:j['proc'].kill();j['proc'].wait()
                        rc=124
                    for p in results.glob('*.csv'):
                        if before.get(p.name)!=hashlib.sha256(p.read_bytes()).hexdigest():
                            dest=j['folder']/p.name;dest.write_bytes(p.read_bytes())
                    with self.lock:
                        j['files']=list(j['folder'].glob('*.csv'))
                        if j['state']!='Durduruldu':j['state']='Tamamlandi' if rc==0 else 'Sure doldu' if rc==124 else 'Hata'
                        j['finished']=time.time();j['env']={}
            except Exception as exc:
                with self.lock:j['state']='Hata';j['error']=str(exc)
            finally:self.queue.task_done()

    def _schedule(self):
        while True:
            try:
                now=datetime.now(ZoneInfo('Europe/Istanbul'))
                if self.auto and now.weekday()<5:
                    day=now.strftime('%Y-%m-%d');hour=now.strftime('%H:%M')
                    slots={'10:05':'eod','10:30':'live','12:00':'live','14:30':'live','16:45':'live','18:15':'close'}
                    for at,mode in slots.items():
                        key=(day,at)
                        elapsed=(now.hour*60+now.minute)-(int(at[:2])*60+int(at[3:]))
                        if 0<=elapsed<20 and key not in self.auto_done:
                            jid=self.submit({'scan':16,'mode':mode},'AUTO')
                            self.auto_done.add(key)
                    # 20 gun kapaniş isi tamamlandiginda otomatik plan durur.
                    with self.lock:
                        for j in self.items.values():
                            if 'AUTO' in j['owners'] and j['params'].get('mode')=='close' and j['state']=='Tamamlandi':
                                self.auto_days.add(datetime.fromtimestamp(j['created'],ZoneInfo('Europe/Istanbul')).date().isoformat())
                    if len(self.auto_days)>=20:self.auto=False
            except Exception:pass
            time.sleep(10)
