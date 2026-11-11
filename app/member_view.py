"""Shared, filtered, whitelisted read model. No broker calls or execution data."""
import math
import threading
import time


FIELDS = ('symbol','name','ltp','percent_change','first_candle_turnover','volume_multiplier',
    'first_candle_open','first_candle_close','first_candle_color','first_candle_high',
    'today_opening_volume','opening_volume_average','possible_candidate','redwala_gira',
    'first_open_equals_low','previous_day_high_cross','previous_day_low_cross',
    'previous_day_low_cross_second_candle','first_candle_high_break','first_candle_low_break',
    'resistance_break','resistance_break_open','resistance_break_open_candle','resistance_level',
    'upper_circuit_limit','lower_circuit_limit','upper_circuit_distance_percent',
    'lower_circuit_distance_percent','circuit_band_percent','is_fno')


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def filtered(rows, settings):
    result=[]
    for row in rows:
        if row.get('confirmation_status') != 'confirmed' or not (row.get('possible_candidate') or row.get('redwala_gira')):
            continue
        setup=settings['setup']
        if setup=='retest' or setup=='possible' and not row.get('possible_candidate') or setup=='redwala' and not row.get('redwala_gira'):
            continue
        if settings['circuit_enabled'] and not (row.get('circuit_band_eligible') is True and row.get('circuit_band_status')=='verified'
                and finite(row.get('circuit_band_percent')) and row['circuit_band_percent']>=20):
            continue
        volume,price=row.get('today_opening_volume'),row.get('ltp')
        if settings['volume_enabled'] and not (finite(volume) and volume>settings['volume_min']):
            continue
        if settings['price_enabled'] and not (finite(price) and 0<price<=settings['price_max']):
            continue
        public={key:row.get(key) for key in FIELDS}
        daily=row.get('daily_filter') or {}
        public['previous_close']=daily.get('previous_close') or row.get('previous_close')
        public['previous_day_multiplier']=daily.get('multiplier')
        public['previous_day_percent']=daily.get('percent_change')
        result.append(public)
    def key(row):
        priority=2 if all(row.get(k) for k in ('possible_candidate','resistance_break','resistance_break_open','first_candle_high_break')) else (
            1 if all(row.get(k) for k in ('redwala_gira','first_candle_low_break','previous_day_low_cross')) else 0)
        turn=row.get('first_candle_turnover')
        return (-priority,-turn if finite(turn) else 1)
    return sorted(result,key=key)


class PublishedDashboard:
    def __init__(self):
        self.lock=threading.Lock()
        self.cached=None
        self.key=None
        self.at=0

    def snapshot(self,engine,display):
        key=(id(engine),display['revision'])
        with self.lock:
            if self.key==key and time.monotonic()-self.at<1:
                return self.cached
            state=engine.snapshot()  # Local memory only. Never touches scanner.algo.
            self.cached={'stocks':filtered(state['stocks'],display['settings']),
                         'connected':bool(state['connected']),'running':bool(state['running']),
                         'updated_at':state['updated_at'],'settings_revision':display['revision']}
            self.key,self.at=key,time.monotonic()
            return self.cached
