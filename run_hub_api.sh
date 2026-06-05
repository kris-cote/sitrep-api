#!/usr/bin/env bash
cd /home/cotek/projects/hub-api
source .venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port 8001
