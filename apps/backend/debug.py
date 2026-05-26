import httpx
resp = httpx.get("https://api.frankfurter.dev/v2/rates?date=2025-05-14&base=USD&quotes=MYR")
print(resp.json())