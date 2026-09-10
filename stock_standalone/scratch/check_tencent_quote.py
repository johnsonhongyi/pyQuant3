# -*- coding: utf-8 -*-
import requests

r = requests.get('http://qt.gtimg.cn/q=sh688808')
txt = r.text.strip()
if '=' in txt:
    val_part = txt.split('=')[1].strip('"; \n')
    vals = val_part.split('~')
    for i, v in enumerate(vals):
        print(f"{i}: {repr(v)}")
