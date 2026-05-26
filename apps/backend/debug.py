import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Pulling the exact variables your orchestrator uses
MORPHEUS_URL = os.getenv("MORPHEUS_URL", "https://api.mor.org/api/v1")
MORPHEUS_API_KEY = os.getenv("MORPHEUS_API_KEY")

# Let's test the stable model you used earlier
MODEL_NAME = "qwen3-5-9b" 

# Clean up endpoint path just like we did in the orchestrator
target_url = MORPHEUS_URL
if not target_url.endswith("/chat/completions"):
    target_url = f"{target_url.rstrip('/')}/chat/completions"

print("📡 Testing Morpheus Connection...")
print(f"🔗 Target Endpoint: {target_url}")
print(f"🤖 Model: {MODEL_NAME}")
print(f"🔑 Token snippet: ...{MORPHEUS_API_KEY[-6:] if MORPHEUS_API_KEY else 'MISSING'}")

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {MORPHEUS_API_KEY}",
}

payload = {
    "model": MODEL_NAME,
    "messages": [{"role": "user", "content": "ping"}],
    "stream": False,
}

try:
    print("\n⏳ Sending request... (Timing out after 20 seconds to see if it hangs)")
    response = httpx.post(target_url, json=payload, headers=headers, timeout=20.0)
    
    print(f"⚡ Status Code Received: {response.status_code}")
    print("\n💬 Morpheus Response:")
    print(response.text)

except httpx.ReadTimeout:
    print("\n❌ CRITICAL: The server accepted the connection but completely HUNG UP (ReadTimeout).")
    print("👉 Meaning: The network node or model cluster is currently locked up or dead.")
except Exception as e:
    print(f"\n❌ Request failed due to standard error: {str(e)}")