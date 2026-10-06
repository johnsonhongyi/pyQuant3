"""Cheap quote prefilter and stable priority ordering before history IO."""
import os
import pandas as pd


def select_candidates(quotes):
    frame = quotes.copy()
    def number(column):
        return pd.to_numeric(frame[column], errors='coerce')
    price, volume = number('new_price'), number('volume')
    change = number('change_rate')
    amplitude = ((number('high_price') - number('low_price')) /
                 number('pre_close_price').where(number('pre_close_price') > 0) * 100)
    valid = (price > 0) & (volume > 0)
    # Activity thresholds are opt-in: quiet stocks may match reversal strategies.
    if os.environ.get('INSTOCK_PREFILTER_ACTIVE_ONLY', '0') == '1':
        valid &= ((change.abs() >= float(os.environ.get('INSTOCK_MIN_CHANGE', '1'))) |
                  (amplitude >= float(os.environ.get('INSTOCK_MIN_AMPLITUDE', '2'))))
        valid &= number('deal_amount') >= float(os.environ.get('INSTOCK_MIN_AMOUNT', '1000000'))
    frame['_priority'] = change.abs().fillna(0) + amplitude.fillna(0)
    frame = frame.loc[valid].sort_values('_priority', ascending=False, kind='stable')
    return frame.drop(columns='_priority')
