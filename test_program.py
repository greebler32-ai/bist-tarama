"""Ag ve kullanici hesabina baglanmadan tum menu yollarini ve hesaplari dogrular."""
import unittest
from unittest.mock import patch
from contextlib import ExitStack,redirect_stdout
import io
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import master_scanner as menu
import erken3g_havuz as e3
import erken3g_kor_test as e3test
import v33_eod_combined as v33
import v33_eylul_kor_test as v33test
from data_quality import completed_daily,valid_long
from memory_results import evaluate
from target_tracking import evaluate_targets

class Calculations(unittest.TestCase):
    def bars(self):
        idx=pd.bdate_range('2025-01-01',periods=260)
        rng=np.random.default_rng(7);c=100+np.cumsum(rng.normal(.1,.4,len(idx)))
        return pd.DataFrame({'Open':c-.2,'High':c+1,'Low':c-1,'Close':c,'Volume':rng.integers(1000,3000,len(idx))},index=idx)

    def test_historical_live_parity(self):
        x=self.bars()
        for live,hist in [(e3,e3test),(v33,v33test)]:
            pd.testing.assert_frame_equal(live._features(x,completed=True),hist._features_hist(x))

    def test_no_future_features(self):
        x=self.bars()
        for mod in (e3,v33):
            full=mod._features(x,completed=True)
            partial=mod._features(x.iloc[:230],completed=True)
            pd.testing.assert_series_equal(full.loc[partial.index[-1]],partial.iloc[-1])

    def test_completed_daily_retains_previous(self):
        x=self.bars();now=datetime(2026,10,9,14,tzinfo=ZoneInfo('Europe/Istanbul'))
        self.assertEqual(len(completed_daily(x,now)),len(x))
        recent=x.tail(2).copy();recent.index=pd.to_datetime(['2026-10-08','2026-10-09'])
        self.assertEqual(len(completed_daily(recent,now)),1)
        self.assertEqual(len(completed_daily(recent,now.replace(hour=19))),2)

    def test_invalid_long(self):
        self.assertTrue(valid_long(100,95,105))
        for v in [(100,102,110),(100,90,99),(100,np.nan,110),(0,0,1)]:self.assertFalse(valid_long(*v))

    def test_missing_sessions_and_nan(self):
        days=list(pd.bdate_range('2026-10-01',periods=4))
        bars=pd.DataFrame({'High':[101,106,107,108],'Low':[99]*4,'Close':[100]*4},index=days)
        row={'TARAMA_ZAMANI':'2026-10-01 12:00','FIYAT':100,'H1':105,'H2':110,'H3':115,'YAPI_BOZULMA':95}
        self.assertEqual(evaluate(row,bars,days)['SONUC_DURUMU'],'TAMAMLANDI')
        bad=bars.drop(days[2])
        self.assertEqual(evaluate(row,bad,days)['SONUC_DURUMU'],'VERI_EKSIK')
        self.assertEqual(evaluate_targets(row,bad,days)['HEDEF_DURUMU'],'VERI_EKSIK')
        bars.loc[days[1],'High']=np.nan
        self.assertEqual(evaluate(row,bars,days)['SONUC_DURUMU'],'VERI_EKSIK')

class MenuConnections(unittest.TestCase):
    def test_all_28_menu_paths(self):
        import balina_erken_kesisim,balina_izi,memory_results,performance_summary
        targets=[(menu.v33_eod,'main'),(menu.live,'momentum_main'),(menu.live,'tavan_main'),(menu.live,'reversal_main'),(menu.radar,'main'),(menu.v32_eod,'main'),(menu.v32_live,'main'),(menu.v20_auto,'main'),(menu.itick_live,'main'),(menu.patlama_havuz,'main'),(menu.v33_sep_test,'main'),(menu.erken3g,'main'),(menu.erken3g_test,'main'),(menu.erken3g_live,'main'),(menu.hafiza,'main'),(balina_erken_kesisim,'main'),(balina_izi,'main'),(memory_results,'main'),(performance_summary,'main')]
        sample=pd.DataFrame([{'HISSE':'TEST','FIYAT':100,'GIRIS_DURUMU':'GIRIS_TETIKLENDI'}])
        for choice in range(1,29):
            with self.subTest(menu=choice),ExitStack() as stack:
                stack.enter_context(patch.object(menu,'show_menu'))
                stack.enter_context(patch.object(menu,'choose_timeframe',return_value=('15 DAKIKA','15m')))
                stack.enter_context(patch.object(menu,'run_single',return_value=sample))
                stack.enter_context(patch.object(menu,'run_master',return_value=sample))
                recorder=stack.enter_context(patch.object(menu.hafiza,'record_scan'))
                stack.enter_context(patch.object(menu.itick_live,'itick_external'))
                for mod,name in targets:stack.enter_context(patch.object(mod,name,return_value=sample))
                stack.enter_context(patch('builtins.input',side_effect=[str(choice),'','0']))
                out=stack.enter_context(redirect_stdout(io.StringIO()))
                menu.main()
                self.assertNotIn('HATASI:',out.getvalue())
                self.assertNotIn('HATA:',out.getvalue())
                if choice not in (24,25,27):self.assertTrue(recorder.called)

class EngineSmokeTests(Calculations):
    def test_seven_real_strategy_engines(self):
        import tempfile
        from pathlib import Path
        import v19_report
        bars=self.bars()
        for name,mod,fn in menu.STRATEGIES:
            with self.subTest(engine=name),tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
                if hasattr(mod,'get_bist_symbols'):stack.enter_context(patch.object(mod,'get_bist_symbols',return_value=['TEST.IS']))
                else:stack.enter_context(patch('symbols.get_bist_symbols',return_value=['TEST.IS']))
                stack.enter_context(patch('yfinance.download',side_effect=lambda *a,**k:bars.copy()))
                stack.enter_context(patch.object(v19_report,'results_dir',return_value=Path(tmp)))
                if hasattr(mod,'send_telegram'):stack.enter_context(patch.object(mod,'send_telegram'))
                if hasattr(mod,'set_timeframe'):mod.set_timeframe('1d')
                stack.enter_context(redirect_stdout(io.StringIO()))
                result=getattr(mod,fn)()
                self.assertIsInstance(result,list)

class DailyPipelineTests(Calculations):
    def test_real_daily_engines_and_exports(self):
        import tempfile
        from pathlib import Path
        import balina_izi,sleeper_pool
        bars=self.bars()
        engines=[menu.v33_eod,menu.v32_eod,menu.patlama_havuz,menu.erken3g,balina_izi]
        for mod in engines:
            with self.subTest(engine=mod.__name__),tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
                root=Path(tmp)
                if hasattr(mod,'get_bist_symbols'):stack.enter_context(patch.object(mod,'get_bist_symbols',return_value=['TEST.IS']))
                else:stack.enter_context(patch('symbols.get_bist_symbols',return_value=['TEST.IS']))
                stack.enter_context(patch('yfinance.download',side_effect=lambda *a,**k:bars.copy()))
                stack.enter_context(patch.object(mod,'result_file',side_effect=lambda n:root/n))
                stack.enter_context(patch.object(sleeper_pool,'result_file',side_effect=lambda n:root/n))
                stack.enter_context(redirect_stdout(io.StringIO()))
                result=mod.main()
                self.assertIsInstance(result,(list,pd.DataFrame))
                if mod is menu.erken3g:
                    errors=pd.read_csv(root/'ERKEN3G_VERI_EKSIK.csv')
                    self.assertTrue(errors.empty)
                    self.assertTrue((root/'UYUYAN_HISSE_KALICI_HAVUZ.csv').exists())

if __name__=='__main__':unittest.main()
