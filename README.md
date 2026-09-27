# Dograh + LiveKit outbound bridge (prototype)

This is an isolated integration prototype. Dograh owns the workflow and admin UI; LiveKit owns the actual call and voice agent. **It does not execute an arbitrary Dograh graph.** This trial reads a published, two-node `startCall -> endCall` workflow via Dograh's authenticated API and passes its start prompt to a LiveKit voice Agent. Multi-node workflows are rejected.

## Safe default

The API starts in dry-run mode and accepts only numbers listed in `ALLOW_NUMBERS`. No call is placed until `ENABLE_LIVE_CALLS=true`, a Dograh URL/API key/published workflow, LiveKit URL/key/secret, outbound SIP trunk ID, a running Agent worker, and an OpenAI API key are configured. Use consented test numbers.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn bridge.app:app --host 127.0.0.1 --port 8088
```

In a separate process, after configuring `.env` as environment variables:

```bash
python agent.py dev
```

Example dry run:

```bash
curl -sS -X POST http://127.0.0.1:8088/calls \
  -H 'Content-Type: application/json' -H 'X-Bridge-Key: local-dev-only' \
  -d '{"lead_id":"test-001","phone":"+85212345678","workflow_version":"1","idempotency_key":"test-001-v1"}'
```

Before enabling live calls, test the SIP trunk against a Hong Kong number and verify answer, latency, Cantonese transcription and interruption. `agent.py` is a trial worker which uses OpenAI's realtime model. This does not yet implement transfer, call-result ingestion, recording, contact-list scheduling, or CRM reporting. The bridge's idempotency state is in memory only; run a single worker and do not use it for batch campaigns.

## Integration contract

* Dograh admin publishes a simple workflow.
* Bridge fetches that version via `GET /workflow/fetch/{id}` and requires the request to pin the same version.
* LiveKit Agent uses the prompt snapshot passed in dispatch metadata.
* Call outcomes and transcripts still need an adapter before this is production-ready.

Dograh endpoint and `X-API-Key` authentication were checked against current Dograh source; confirm compatibility with the deployed version. This is a trial bridge, not a complete Dograh plugin.
