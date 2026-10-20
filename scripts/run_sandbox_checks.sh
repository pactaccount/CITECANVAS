#!/usr/bin/env sh
set -eu

# This script deliberately runs only offline tests. It never sends documents
# to NVIDIA or calls R2, Neon, or Qdrant.
pytest tests/test_upload_api.py tests/test_runtime.py -q -p no:cacheprovider
python -m py_compile scripts/serve.py
