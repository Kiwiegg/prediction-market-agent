from decimal import Decimal
import unittest
from scripts.select_markets import classify


class SelectionTests(unittest.TestCase):
    def history(self, value):
        return {'complete': True, 'points': [{'price':value, 'resolution_seconds':300,
                'forecasting_candidate':True}], 'granular':[]}

    def test_cutoff_is_strict_and_decimal(self):
        self.assertEqual(classify(self.history('0.05'), Decimal('0.05'))['status'],'drop')
        self.assertEqual(classify(self.history('0.050000000000000001'), Decimal('0.05'))['status'],'keep')

    def test_settlement_spike_does_not_keep_low_market(self):
        h=self.history('0.01')
        h['points'].append({'price':'1','resolution_seconds':0,'forecasting_candidate':False})
        self.assertEqual(classify(h,Decimal('0.05'))['status'],'drop')

    def test_missing_or_incomplete_history_is_unknown(self):
        h=self.history('0.01');h['complete']=False
        self.assertEqual(classify(h,Decimal('0.05'))['status'],'unknown')
        h=self.history('0.01');h['granular']=[{'complete':False,'points':[]}]
        self.assertEqual(classify(h,Decimal('0.05'))['status'],'unknown')
        h=self.history('0.1');h['granular']=[{'complete':False,'points':[]}]
        self.assertEqual(classify(h,Decimal('0.05'))['status'],'keep')
