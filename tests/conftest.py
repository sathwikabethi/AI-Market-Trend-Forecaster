import os
import sys


# Keep test runs deterministic and avoid leaving behind noisy artifacts.
sys.dont_write_bytecode = True

# Disable background threads in the FastAPI lifespan during tests.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("INGESTION_SCHEDULER_ENABLED", "0")
os.environ.setdefault("JOB_WORKER_ENABLED", "0")

