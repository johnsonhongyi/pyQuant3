import requests
import json

url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
params = {
    "reportName": "RPT_LIFT_STAGE",
    "pageSize": "10",
    "filter": '(SECURITY_CODE="920038")',
    "sortColumns": "FREE_DATE",
    "sortTypes": "1",
    "columns": "ALL",
}
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, params=params, headers=headers, timeout=5)
resp.encoding = "utf-8"
data = resp.json()
for it in data.get("result", {}).get("data", []):
    print(f"Date: {it.get('FREE_DATE')} | Shares: {it.get('CURRENT_FREE_SHARES')}万股 | Ratio: {float(it.get('TOTAL_RATIO') or 0)*100:.2f}% | Type: {it.get('FREE_SHARES_TYPE')}")
