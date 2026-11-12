import os
import requests
import json
import pandas as pd

API_KEY = os.getenv("GRIDMIX_API_KEY")
if not API_KEY:
    raise ValueError("Встановіть змінну середовища GRIDMIX_API_KEY")

URL = "https://www." + "gridmix.co.uk" + "/api/mcp"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "User-Agent": "Mozilla/5.0"
}

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "get_current_mix",
        "arguments": {}
    }
}

response = requests.post(URL, headers=headers, json=payload, timeout=15)

for line in response.text.splitlines():
    if line.startswith("data: "):
        rpc_data = json.loads(line[6:])
        inner_text = rpc_data["result"]["content"].pop(0)["text"]
        mix = json.loads(inner_text)["data"]

        df_gen = pd.DataFrame(mix["generationmix"])
        df_gen["perc"] = df_gen["perc"].round(2)
        df_gen.columns = ["Джерело", "Потужність (МВт)", "Частка (%)"]

        df_ic = pd.DataFrame(mix["interconnectors"])
        df_ic.columns = ["Інтерконектор", "Країна", "Потік (МВт)", "Ліміт (МВт)"]

        print(f"\nЧас (UTC): {mix['from']} | Всього генерація: {mix['totalGeneration']} МВт")
        print(f"Імпорт: {mix['totalImports']} МВт | Експорт: {mix['totalExports']} МВт\n")

        print("=== ГЕНЕРАЦІЯ ===")
        print(df_gen.to_string(index=False))

        print("\n=== ІНТЕРКОНЕКТОРИ ===")
        print(df_ic.to_string(index=False))
