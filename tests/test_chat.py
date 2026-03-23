import json
import requests

url = "http://127.0.0.1:5000/chat"

payload = {
    "message": "查一下台北今天天氣"
}

response = requests.post(url, json=payload, timeout=30)

print("STATUS:", response.status_code)
print(json.dumps(response.json(), ensure_ascii=False, indent=2))