import unittest,tempfile,time,io,contextlib,os,json,sys
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from web_catalog import SCANS

class WebTests(unittest.TestCase):
    def test_catalog_complete(self):self.assertEqual(set(SCANS),set(range(1,29)))

    def test_web_app_opens(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).parent/'app.py')).run(timeout=15)
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('Günlük Top10' in s.label or 'Tarama' in s.label for s in at.selectbox))
        self.assertTrue(any(b.label=='Taramayı başlat' for b in at.button))

    def test_worker_routes_without_interactive_input(self):
        from contextlib import ExitStack
        import web_worker as w,master_scanner as m
        import balina_izi,balina_erken_kesisim,memory_results,performance_summary
        sample=pd.DataFrame([{'HISSE':'TEST','FIYAT':100,'GIRIS_DURUMU':'GIRIS_TETIKLENDI'}])
        targets=[(m.v33_eod,'main'),(m.live,'momentum_main'),(m.live,'tavan_main'),(m.live,'reversal_main'),(m.radar,'main'),(m.v32_eod,'main'),(m.v32_live,'main'),(m.v20_auto,'run_live_slot'),(m.v20_auto,'run_eod_once'),(m.itick_live,'main'),(m.itick_live,'itick_external'),(m.patlama_havuz,'main'),(m.v33_sep_test,'main'),(m.erken3g,'main'),(m.erken3g_test,'main'),(m.erken3g_live,'main'),(m.hafiza,'search_symbol'),(m.hafiza,'recent'),(balina_izi,'main'),(balina_erken_kesisim,'main'),(memory_results,'main'),(performance_summary,'main')]
        for n in range(1,29):
            with self.subTest(scan=n),ExitStack() as stack:
                stack.enter_context(patch('web_cache.install'))
                stack.enter_context(patch.dict(os.environ,{'ITICK_KEY':'TEST_KEY'}))
                stack.enter_context(patch.object(m,'run_single',return_value=sample))
                stack.enter_context(patch.object(m,'run_master',return_value=sample))
                stack.enter_context(patch.object(m.hafiza,'record_scan'))
                for mod,name in targets:stack.enter_context(patch.object(mod,name,return_value=sample))
                stack.enter_context(patch('builtins.input',side_effect=AssertionError('Web worker input kullanamaz')))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                w.run(n)

    def test_cache_does_not_save_empty_data(self):
        import yfinance as yf,web_cache
        original=yf.download
        try:
            with tempfile.TemporaryDirectory() as t,patch.object(yf,'download',return_value=pd.DataFrame()) as download:
                web_cache.install(t);yf.download('TEST');yf.download('TEST')
                self.assertEqual(download.call_count,2)
                self.assertEqual(len(list(Path(t).glob('*.pkl'))),0)
        finally:yf.download=original

    def test_cache_reuses_valid_data(self):
        import yfinance as yf,web_cache
        original=yf.download
        try:
            with tempfile.TemporaryDirectory() as t,patch.object(yf,'download',return_value=pd.DataFrame({'Close':[100]})) as download:
                web_cache.install(t);yf.download('TEST');yf.download('TEST')
                self.assertEqual(download.call_count,1)
        finally:yf.download=original

    def test_shared_queue_cancel_ownership(self):
        from web_jobs import Jobs
        with tempfile.TemporaryDirectory() as t,patch.object(Jobs,'_loop'),patch.object(Jobs,'_schedule'):
            manager=Jobs(t)
            jid=manager.submit({'scan':9},'a');same=manager.submit({'scan':9},'b')
            self.assertEqual(jid,same)
            self.assertFalse(manager.cancel(jid,'stranger'))
            self.assertTrue(manager.cancel(jid,'a'))
            self.assertEqual(manager.get(jid)['state'],'Sirada')
            self.assertTrue(manager.cancel(jid,'b'))
            self.assertEqual(manager.get(jid)['state'],'Durduruldu')

if __name__=='__main__':unittest.main()
