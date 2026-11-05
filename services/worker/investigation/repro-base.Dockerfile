# Trusted browser-repro base image (one-time maintainer build, NOT per-execution).
#
# The upstream mcr.microsoft.com/playwright/python image ships browsers and OS
# deps but NOT the playwright Python package, so per-execution repro images
# (whose fixed Dockerfile is RUN-free by design) cannot import it. This base
# adds the pinned package once; per-execution builds stay hermetic.
#
# Build (from the repo root):
#   docker build -f services/worker/investigation/repro-base.Dockerfile \
#     -t meridian/repro-base:1.49.0 services/worker/investigation/
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy
RUN pip install --no-cache-dir 'playwright==1.49.0'
