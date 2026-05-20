# Local Tracing Setup

## Background

This application uses OpenTelemetry (OTel) to export traces to DataRobot's observability platform. When deployed, traces flow automatically. During local development, you point your telemetry at the same Use Case that backs your Pulumi stack so local and deployed traces appear in the same place.

> [!IMPORTANT]
> Tracing is entirely optional. If no backend is configured, the app silently ignores telemetry and runs normally.

---

## How It Works

All services share the same Use Case as their OTel entity. The entity header uses the `experiment_container` type — DataRobot's internal name for Use Cases in the authorization and storage layers (`use_case` is the user-facing alias accepted only by the read APIs).

The DataRobot OTel collector overwrites `service.name` with the entity ID, so all spans from all local services appear under the same entity in the tracing UI. Individual services are still distinguishable by their span names.

> [!TIP]
> The Taskfile reads from `.env` automatically (`dotenv: [".env"]`). Add your OTel credentials there once — no per-terminal exporting needed.

---

## Setup

### 1. Run `task start`

```bash
task start
```

At the end of `task start`, the Use Case is created in your active Pulumi stack and the two `.env` lines are printed automatically:

```
Add these to your .env for local tracing:

  OTEL_EXPORTER_OTLP_ENDPOINT=https://app.datarobot.com/otel
  OTEL_EXPORTER_OTLP_HEADERS=x-datarobot-entity-id=experiment_container-<id>,x-datarobot-api-key=<token>

View traces: https://app.datarobot.com/usecases/<id>/tracing
```

To see these values again at any time without re-deploying:

```bash
task infra:local-experimentation-otel-setup
```

### 2. Add them to your `.env`

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://app.datarobot.com/otel
OTEL_EXPORTER_OTLP_HEADERS=x-datarobot-entity-id=experiment_container-<id>,x-datarobot-api-key=<token>
```

### 3. Start local dev

```bash
task dev
```

### 4. View traces

**Option A — DataRobot UI:** Open the URL printed in step 1 and navigate to the **Tracing** tab. Use the app, then refresh — traces arrive within a few seconds.

**Option B — Local dashboard** (no browser login required, great for dev): use `task infra:tracing:start`, or manually:

```bash
dr experimentation --entity-type experiment_container --entity-id <use-case-id>
```

Runs in the foreground (Ctrl+C to stop). Opens http://127.0.0.1:8090 — traces appear in real time.

---

## Multiple stacks

`task start` uses whichever Pulumi stack is currently selected. To switch stacks:

```bash
task infra:select -- <stack-name>
```

Then re-run `task infra:local-experimentation-otel-setup` to get the correct entity ID for that stack.

---

## Disabling tracing

Add to your `.env`:

```bash
OTEL_SDK_DISABLED=true
```

Or simply omit `OTEL_EXPORTER_OTLP_ENDPOINT` — the app detects this and skips telemetry automatically.

---

## Troubleshooting

**I don't see any traces.**
- Check that `.env` contains both `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`.
- Traces are sent in batches — wait ~5 seconds after your request finishes, then refresh.

**The app logs an error about missing `OTEL_EXPORTER_OTLP_HEADERS`.**
- `OTEL_EXPORTER_OTLP_ENDPOINT` is set but `OTEL_EXPORTER_OTLP_HEADERS` is missing. Without auth headers, every request is rejected. Either add `OTEL_EXPORTER_OTLP_HEADERS` to `.env`, or remove `OTEL_EXPORTER_OTLP_ENDPOINT` to disable tracing entirely.

**`task infra:local-experimentation-otel-setup` prints "Could not read DATAROBOT_USE_CASE_ID".**
- The Pulumi stack hasn't been deployed yet. Run `task start` to create the backing infrastructure first.

**I get HTTP 401 when using `use_case-<id>` as the entity header.**
- The DataRobot OTel collector's authorization API stores use cases under the internal type `experiment_container`. Use `experiment_container-<id>` in `OTEL_EXPORTER_OTLP_HEADERS` — this is what `task start` prints. The read APIs (dashboard, Tracing tab) accept `use_case` as the entity type; only the write header requires `experiment_container`.
