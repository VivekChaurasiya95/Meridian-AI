"""Security preflight worker package (V1: Semgrep + Gitleaks).

Pure scanner-output handling lives here: wrappers parse fixed-format
scanner stdout, the normalizer maps findings onto Meridian's schema,
and the risk policy interprets them. Container execution stays in
``security.orchestrator`` on top of the existing sandbox primitives.
Nothing here touches the network, Docker, or credentials directly.
"""
