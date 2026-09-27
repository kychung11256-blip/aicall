# Dograh + LiveKit outbound bridge (prototype)

This is an isolated integration prototype. Dograh owns the workflow and admin UI; LiveKit owns the actual call and voice agent. **It does not turn a Dograh graph into LiveKit code.** Export an approved, versioned prompt/config into the bridge first. The Dograh workflow export adapter and call-result ingestion must be implemented against the Dograh version you deploy.

## Safe default

The API starts in dry-run mode and accepts only numbers listed in `ALLOW_NUMBERS`. No call is placed until `ENABLE_LIVE_CALLS=true`, a LiveKit URL/key/secret, outbound SIP trunk ID, and a deployed agent are configured. Use consented test numbers.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn bridge.app:app --host 127.0.0.1 --port 8088
```

Example dry run:

```bash
curl -sS -X POST http://127.0.0.1:8088/calls \
  -H 'Content-Type: application/json' -H 'X-Bridge-Key: local-dev-only' \
  -d '{"lead_id":"test-001","phone":"+85212345678","workflow_version":"sales-v1","idempotency_key":"test-001-v1"}'
```

Before enabling live calls, test the SIP trunk against a Hong Kong number and verify answer, latency, Cantonese transcription, interruption and transfer. `LIVEKIT_AGENT_NAME` refers to an independently deployed LiveKit Agent. It must read dispatch metadata, load the pinned workflow version and emit call outcomes to your backend. This project currently dispatches and dials; it does not include that production agent, a Dograh importer, contact-list scheduler, recording, or CRM ingestion.

## Integration contract

* Dograh admin exports an approved workflow snapshot, with immutable `workflow_version` and prompt revision.
* Bridge accepts an authorized call request and dispatches that version in LiveKit metadata.
* LiveKit Agent uses that snapshot for the conversation and emits a signed outcome event.
* An adapter writes transcript, consent and disposition to Dograh (endpoint mapping depends on deployed version).

Do not rely on a hardcoded Dograh API endpoint until confirmed against your deployment. This prototype is a boundary and dialer, not a completed Dograh plugin.
