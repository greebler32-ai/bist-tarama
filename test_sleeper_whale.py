import unittest
from unittest.mock import patch
from sleeper_whale import annotate

class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.c={'HISSE':'TEST','VERI_TARIHI':'2026-10-08','ERKEN3G_SKOR':80,'ASAMA':'UYKU-SONU','ADAY_TIPI':'TABAN_SIKISMA'}
        self.w={'VERI_TARIHI':'2026-10-08','ADAY_TIPI':'BIRIKIM_ADAYI','BALINA_IZI_SKOR':75,'CMF20':.2,'OBV5_ORAN':.3}

    def test_original_preserved(self):
        with patch('sleeper_whale.analyse',return_value=self.w):out=annotate(self.c,None,'TEST.IS')
        for key,value in self.c.items():self.assertEqual(out[key],value)
        self.assertEqual(out['BALINA_DURUMU'],'BIRIKIM_ADAYI')
        self.assertNotIn('BALINA_DURUMU',self.c)

    def test_distribution_separate(self):
        with patch('sleeper_whale.analyse',return_value=dict(self.w,ADAY_TIPI='DAGITIM_IZI')):out=annotate(self.c,None,'TEST.IS')
        self.assertEqual(out['BALINA_DURUMU'],'DAGITIM_IZI')
        self.assertIn('sayilmaz',out['BALINA_NOTU'])

    def test_date_mismatch(self):
        with patch('sleeper_whale.analyse',return_value=dict(self.w,VERI_TARIHI='2026-10-07')):out=annotate(self.c,None,'TEST.IS')
        self.assertEqual(out['BALINA_DURUMU'],'VERI_TARIHI_UYUSMUYOR')

    def test_no_trace(self):
        with patch('sleeper_whale.analyse',return_value=None):out=annotate(self.c,None,'TEST.IS')
        self.assertEqual(out['BALINA_DURUMU'],'BELIRGIN_IZ_YOK')

    def test_error_preserves_candidate(self):
        with patch('sleeper_whale.analyse',side_effect=ValueError('test')):out=annotate(self.c,None,'TEST.IS')
        self.assertEqual(out['ERKEN3G_SKOR'],80)
        self.assertEqual(out['BALINA_DURUMU'],'KONTROL_EDILEMEDI')

if __name__=='__main__':unittest.main()
