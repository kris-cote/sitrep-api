# Space Hub – Architecture (TRL-4)

## Objective
Provide a deterministic, reproducible “situation awareness + decision support” backbone that ingests external data (weather, NOTAM, satellite imagery metadata), normalizes it, and produces machine-readable operational status (e.g., GO / HOLD / NO-GO) suitable for launch-range and corridor operations.

## Components
1. **hub-api (FastAPI)**  
   - Serves: health endpoints, normalized data views, and decision outputs.
   - No polling/scraping. Pure read + compute over stored/available inputs.

2. **hub-pollers (polling container)**  
   - Fetches external sources on a schedule.
   - Normalizes and stores into Postgres and/or a shared cache volume (/data).
   - Never makes operational decisions.

3. **Postgres**
   - Stores normalized caches (weather, NOTAM, derived statuses).

4. **Shared Volume (/data)**
   - Optional “artifact cache” for latest satellite image and metadata, etc.

## Data Flow (High-level)
External Sources → Pollers → Postgres / /data → hub-api → Consumers (dashboard, automations, clients)

## TRL-4 Note
This system is a laboratory/bench validation environment:
- deterministic build + boot
- stable endpoint contracts
- evidence logs and reproducible outputs
