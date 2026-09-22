#!/usr/bin/env bash
set -euo pipefail

npm install
playwright install --with-deps chromium
