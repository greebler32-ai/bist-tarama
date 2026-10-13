"""Ag gerektirmeyen havuz gecis ve kalici kayit testleri."""
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import sleeper_pool as p

class PoolHistoryTests(unittest.TestCase):
    def candidate(self, stage='UYKU-SONU'):
        return pd.DataFrame([{'HISSE':'TEST','ASAMA':stage,'GIRIS':100,'ERKEN3G_SKOR':80,'ADAY_TIPI':'TABAN_SIKISMA'}])

    def first(self):
        return p.update_pool(pd.DataFrame(),self.candidate(),{'TEST':'2026-10-08'},[],'2026-10-09 12:00')

    def test_first_and_stage(self):
        a=self.first()
        self.assertEqual(p.build_events(pd.DataFrame(),a,'t').iloc[0].OLAY,'ILK_ADAY')
        b=p.update_pool(a,self.candidate('UYANIS'),{'TEST':'2026-10-09'},[],'t')
        self.assertEqual(p.build_events(a,b,'t').iloc[0].OLAY,'ASAMA_DEGISIMI')

    def test_repeat_no_event(self):
        a=self.first();b=p.update_pool(a,self.candidate(),{'TEST':'2026-10-08'},[],'t')
        self.assertTrue(p.build_events(a,b,'t').empty)

    def test_missing_and_recovery(self):
        a=self.first();b=p.update_pool(a,pd.DataFrame(),{},['TEST'],'t')
        self.assertEqual(p.build_events(a,b,'t').iloc[0].OLAY,'VERI_EKSIK')
        c=p.update_pool(b,self.candidate(),{'TEST':'2026-10-08'},[],'t')
        self.assertEqual(p.build_events(b,c,'t').iloc[0].OLAY,'HAVUZA_DONDU')

    def test_outside_and_return(self):
        a=self.first();b=p.update_pool(a,pd.DataFrame(),{'TEST':'2026-10-09'},[],'t')
        self.assertEqual(p.build_events(a,b,'t').iloc[0].OLAY,'KRITER_DISI')
        c=p.update_pool(b,self.candidate('UYANIS'),{'TEST':'2026-10-10'},[],'t')
        self.assertEqual(p.build_events(b,c,'t').iloc[0].YENI_ASAMA,'UYANIS')

    def test_disk_deduplication(self):
        a=self.first();events=p.build_events(pd.DataFrame(),a,'2026-10-09 12:00')
        with TemporaryDirectory() as t,patch.object(p,'result_file',lambda n:Path(t)/n):
            p.append_events(events)
            self.assertEqual(len(p.append_events(events)),1)
            self.assertTrue((Path(t)/'UYUYAN_HISSE_GECIS_GECMISI.csv').exists())

if __name__=='__main__':unittest.main()
