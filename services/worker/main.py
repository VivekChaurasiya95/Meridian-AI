"""Meridian AI Isolated Worker / Sandbox Execution Daemon (Milestone 5 stub)."""
import os
import signal
import sys
import time


def handle_exit(signum, frame):
    print("[meridian-worker] Shutdown signal received. Exiting cleanly.")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    env = os.getenv("MERIDIAN_ENV", "dev")
    storage_endpoint = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
    print(f"[meridian-worker] Starting isolated execution sandbox runner (env={env})...")
    print(f"[meridian-worker] Object storage target: {storage_endpoint}")
    print("[meridian-worker] Ready to execute isolated reproduction & verification tasks.")

    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
