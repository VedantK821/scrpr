"""Watch enrichment logs live — run this in a separate terminal."""
import time
import os
import sys

LOG_PATH = os.path.expanduser("~/.scrpr/logs/enrichment.log")

# Clear old log
open(LOG_PATH, "w").close()

print("=" * 60)
print("  SCRPR ENRICHMENT MONITOR")
print("  Watching:", LOG_PATH)
print("=" * 60)
print()

try:
    with open(LOG_PATH, "r") as f:
        f.seek(0, 2)  # end of file
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                # Color-code output
                if "FOUND" in line or "EXISTS" in line:
                    print(f"\033[92m  {line}\033[0m")  # green
                elif "FAIL" in line or "ERROR" in line or "SKIP" in line:
                    print(f"\033[91m  {line}\033[0m")  # red
                elif "DOMAIN:" in line:
                    print(f"\033[96m  {line}\033[0m")  # cyan
                elif "EMAIL_PATTERN:" in line:
                    print(f"\033[93m  {line}\033[0m")  # yellow
                else:
                    print(f"  {line}")
            else:
                time.sleep(0.3)
except KeyboardInterrupt:
    print("\nStopped.")
