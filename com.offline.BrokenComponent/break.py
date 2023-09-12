import time
import sys

wait = int(float(sys.argv[1]))

time.sleep(wait)
raise SystemExit(f"Throw error after {wait} seconds")
