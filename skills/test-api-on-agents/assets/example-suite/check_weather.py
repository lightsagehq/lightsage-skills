"""Pass if weather.py prints a number within 1.5 C of Open-Meteo's own forecast."""
import json
import subprocess
import sys
import urllib.request

try:
    out = subprocess.run([sys.executable, "weather.py"], capture_output=True, text=True, timeout=60)
except FileNotFoundError:
    sys.exit("weather.py missing")
try:
    got = float(out.stdout.strip().split()[-1])
except (ValueError, IndexError):
    sys.exit(f"not a bare number: {out.stdout!r} {out.stderr[-300:]!r}")
url = ("https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41"
       "&daily=temperature_2m_max&timezone=Europe%2FBerlin&forecast_days=2")
with urllib.request.urlopen(url, timeout=30) as r:
    want = json.load(r)["daily"]["temperature_2m_max"][1]
print(f"weather.py={got} open-meteo={want}")
sys.exit(0 if abs(got - want) <= 1.5 else 1)
