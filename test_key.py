import os
import requests
from dotenv import load_dotenv  # ⚠️ Ajoutez cette ligne

load_dotenv()  # ⚠️ Chargez le .env

api_key = os.environ.get('OPENROUTER_API_KEY')

if not api_key:
    print("❌ OPENROUTER_API_KEY non trouvée")
    print("Vérifiez que le fichier .env existe et contient:")
    print("OPENROUTER_API_KEY=sk-or-v1-...")
    exit(1)

print(f"Clé chargée: {api_key[:20]}... (tronquée)")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers=headers,
    json={
        "model": "openai/gpt-oss-20b:free",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10
    },
    timeout=10
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("✅ Clé valide!")
    print(response.json())
elif response.status_code == 401:
    print("❌ Clé invalide - vérifiez sur openrouter.ai/keys")
else:
    print(f"⚠️ Erreur: {response.text[:200]}")
