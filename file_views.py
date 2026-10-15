"""Aday, hata raporu ve istatistik ayni gorunume zorlanmaz."""
from pathlib import Path
from result_view import trade_view

def is_error_file(path):
    name=Path(path).name.upper()
    return any(k in name for k in ('HATA','EKSIK','DIAGNOSTIK'))

def result_kind(frame,path=''):
    if is_error_file(path) or 'HATA' in frame.columns:return 'error'
    # Hafiza/ileri test tablolarinin tarihi ve sonucu korunur.
    if any(k in frame for k in ('SINYAL_GUNU','HEDEF_GUN','MFE_%','D3_BASARI','OLAY','BENZERSIZ_ADAY_GUN')):return 'report'
    if any(k in frame for k in ('GIRIS','FIYAT','KAPANIS','CANLI_GIRIS','entry')) and any(k in frame for k in ('HISSE','symbol')):return 'candidates'
    return 'report'

def show_frame(frame,path=''):
    return trade_view(frame) if result_kind(frame,path)=='candidates' else frame

def sort_files(files):
    return sorted(files,key=lambda p:(is_error_file(p),Path(p).name!='sonuc.csv',Path(p).name))
