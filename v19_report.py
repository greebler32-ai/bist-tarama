from pathlib import Path
from datetime import datetime
import sys
from v19_paths import results_dir

class Tee:
    def __init__(self, *streams):
        self.streams=streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()
        return len(data)
    def flush(self):
        for s in self.streams:
            s.flush()

def start_txt_report(prefix):
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    path=results_dir()/f"{prefix}_{stamp}.txt"
    fh=open(path,"w",encoding="utf-8")
    old=sys.stdout
    sys.stdout=Tee(old,fh)
    return old,fh,path

def stop_txt_report(old,fh,path):
    sys.stdout=old
    fh.close()
    print(f"Ekran raporu kaydedildi: {path}")
