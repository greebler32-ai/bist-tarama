"""Terminaldeki motorlarin etkileşimsiz web islerini calistirir."""
import argparse,json,os,signal,sys
from pathlib import Path
import pandas as pd

def run(scan,tf='15m',start='2026-04-01',end='2026-08-31',symbol='',mode='both'):
    from web_catalog import ALL_SCANS
    if scan not in ALL_SCANS:raise ValueError('Bu eski tarama sade surumden kaldirildi.')
    import web_engines as m
    import candidate_memory as memory
    import web_cache
    web_cache.install(Path(__file__).parent/'web_data'/'cache')
    result=None;engine=f'WEB_{scan}'
    if scan==9:result=m.v33_eod.main();engine='V33_TOP10'
    elif scan==10:result=m.live.momentum_main('15m')
    elif scan==11:result=m.live.tavan_main('15m')
    elif scan==13:result=m.radar.main('15m')
    elif scan==12:result=m.live.reversal_main()
    elif scan==16:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now=datetime.now(ZoneInfo('Europe/Istanbul'))
        if mode in ('both','live'):m.v20_auto.run_live_slot('WEB')
        if mode in ('both','eod'):m.v20_auto.run_eod_once('WEB')
        if mode=='close':
            m.v20_auto.evaluate_ledger(now);m.v20_auto.evaluate_eod_ledger(now);m.v20_auto.run_eod_once('WEB_KAPANIS')
        return
    elif scan==17:
        if not os.environ.get('ITICK_KEY'):raise ValueError('Sunucuda ITICK_KEY tanimli degil.')
        result=m.itick_live.main()
    elif scan==18:result=m.patlama_havuz.main();engine='PATLAMA_ONCESI'
    elif scan==19:m.v33_sep_test.main(start,end);return
    elif scan==20:result=m.erken3g.main();engine='ERKEN3G_TOP10'
    elif scan==21:m.erken3g_test.main(start,end);return
    elif scan==24:
        if symbol:result=memory.search_symbol(symbol)
        else:result=memory.recent(200)
        return result
    elif scan==25:
        import memory_results
        memory_results.main();return
    elif scan==26:
        import balina_izi
        result=balina_izi.main();engine='BALINA_IZI'
    elif scan==27:
        import performance_summary
        result=performance_summary.main();return result
    elif scan==28:
        import balina_erken_kesisim
        result=balina_erken_kesisim.main();engine='BALINA_ERKEN3G_KESISIM'
        if not result.empty:
            signals=result[result.GIRIS_DURUMU=='GIRIS_TETIKLENDI']
            if not signals.empty:memory.record_scan('BALINA_ERKEN3G_CANLI_TETIK',signals,source='WEB')
            memory.record_scan(engine,result.drop(columns=['TETIK_GIRIS','CANLI_GIRIS'],errors='ignore'),source='WEB')
        return result
    else:raise ValueError('Gecersiz tarama')
    memory.record_scan(engine,result,source='WEB')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--params',required=True);parser.add_argument('--output',required=True)
    a=parser.parse_args();params=json.loads(a.params)
    # SIGTERM iTick ozetini kaydedebilsin diye KeyboardInterrupt'a donusturulur.
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        value=run(**params)
        if value is not None:
            df=value if isinstance(value,pd.DataFrame) else pd.DataFrame(value)
            df.to_csv(a.output,index=False,encoding='utf-8-sig')
    except KeyboardInterrupt:sys.exit(130)
    except Exception as exc:
        print(f'WEB IS HATASI: {exc}',flush=True);sys.exit(1)
