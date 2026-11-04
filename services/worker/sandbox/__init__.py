"""Isolated execution sandbox (M5.2): trusted orchestrator components.

The worker process uses this package to run approved commands inside
disposable Docker containers. Repository code NEVER executes in the
worker or API processes — only inside the untrusted container, which
receives source bytes and nothing else (no credentials, no socket, no
network).
"""
