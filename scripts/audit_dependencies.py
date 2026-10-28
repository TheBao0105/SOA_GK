"""Đối chiếu các gói đã cài với cơ sở dữ liệu lỗ hổng công khai OSV, không cần cài công cụ audit."""
import importlib.metadata
import json
from pathlib import Path
import sys
import requests

packages=[{"package":{"name":d.metadata["Name"],"ecosystem":"PyPI"},"version":d.version} for d in importlib.metadata.distributions()]
response=requests.post("https://api.osv.dev/v1/querybatch",json={"queries":packages},timeout=30)
response.raise_for_status()
results=response.json()["results"]
if len(results)!=len(packages):
    raise RuntimeError("Incomplete OSV response")
report={"source":"https://api.osv.dev/v1/querybatch","packages_checked":len(packages),"findings":[{"package":p["package"]["name"],"version":p["version"],"vulnerabilities":result["vulns"]} for p,result in zip(packages,results) if result.get("vulns")]}
output=Path(__file__).resolve().parents[1]/"work"/"dependency-audit.json"
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
sys.exit(bool(report["findings"]))
