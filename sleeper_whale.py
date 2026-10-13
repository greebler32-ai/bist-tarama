"""ERKEN-3G secimini degistirmeden ayni veride balina izi aciklamasi."""
from balina_izi import analyse


def annotate(candidate, bars, symbol):
    out=dict(candidate)
    defaults={'BALINA_DURUMU':'BELIRGIN_IZ_YOK','BALINA_IZI_SKOR':0,'BALINA_NOTU':'Fiyat-hacimde belirgin birikim/dagitim izi yok','KURUM_TEYIDI':'YOK'}
    out.update(defaults)
    try:
        whale=analyse(bars,symbol)
        if not whale:return out
        if str(whale['VERI_TARIHI'])!=str(candidate.get('VERI_TARIHI')):
            out.update(BALINA_DURUMU='VERI_TARIHI_UYUSMUYOR',BALINA_NOTU='Iki katman farkli tarihli; teyit kullanilmadi')
            return out
        state=whale['ADAY_TIPI']
        notes={'BIRIKIM_ADAYI':'Hazirlik yapisina birikim izi eslik ediyor','GUCLU_ALIM_IZI':'Hazirlik yapisina guclu alim izi eslik ediyor','DAGITIM_IZI':'Dagitim izi var; olumlu alim teyidi sayilmaz'}
        out.update(BALINA_DURUMU=state,BALINA_IZI_SKOR=whale['BALINA_IZI_SKOR'],BALINA_NOTU=notes[state],CMF20=whale['CMF20'],OBV5_ORAN=whale['OBV5_ORAN'])
    except Exception as exc:
        out.update(BALINA_DURUMU='KONTROL_EDILEMEDI',BALINA_NOTU='Balina katmani hesaplanamadi: '+str(exc))
    return out
