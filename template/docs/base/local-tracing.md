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
> After `dr start`, OTel credentials are written to `pulumi_config.json` and loaded automatically by `DataRobotAppFrameworkBaseSettings` — no `.env` editing needed for most setups.

---

## Setup

### 1. Run `dr start`

```bash
dr start
```

This deploys the backing infrastructure and writes the OTel credentials to `pulumi_config.json`:

- `OTEL_EXPORTER_OTLP_ENDPOINT` — the DataRobot OTel collector URL
- `OTEL_EXPORTER_OTLP_HEADERS` — auth header with your entity ID and API token

`DataRobotAppFrameworkBaseSettings` reads `pulumi_config.json` automatically, so OTel is configured for local dev without any further steps.

To print the current values without re-deploying:

```bash
dr task run infra:local-experimentation-otel-setup
```

### 2. Start local dev

```bash
task dev
```

### 3. View traces

**Option A — DataRobot UI:** Navigate to your Use Case in DataRobot and open the **Tracing** tab. Use the app, then refresh — traces arrive within a few seconds.

**Option B — Local dashboard** (no browser login required, great for dev): use `task infra:tracing:start`, or manually:

```bash
dr experimentation --entity-type experiment_container --entity-id <use-case-id>
```

Runs in the foreground (Ctrl+C to stop). Opens http://127.0.0.1:8090 — traces appear in real time.

---

## Multiple stacks

`dr start` uses whichever Pulumi stack is currently selected. To switch stacks:

```bash
task infra:select -- <stack-name>
```

Then re-run `dr task run infra:local-experimentation-otel-setup` to refresh `pulumi_config.json` with the correct entity ID for that stack.

---

## Disabling tracing

Set in your `.env`:

```bash
OTEL_SDK_DISABLED=true
```

Or simply omit `OTEL_EXPORTER_OTLP_ENDPOINT` from `pulumi_config.json`/`.env` — the app detects this and skips telemetry automatically.

---

## Troubleshooting

**I don't see any traces.**
- Check that `pulumi_config.json` (or `.env`) contains both `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`.
- Traces are sent in batches — wait ~5 seconds after your request finishes, then refresh.

**The app logs an error about missing `OTEL_EXPORTER_OTLP_HEADERS`.**
- `OTEL_EXPORTER_OTLP_ENDPOINT` is set but `OTEL_EXPORTER_OTLP_HEADERS` is missing. Without auth headers, every request is rejected. Re-run `dr start` to refresh `pulumi_config.json`, or add `OTEL_EXPORTER_OTLP_HEADERS` to `.env` manually.

**`dr task run infra:local-experimentation-otel-setup` prints "Could not read DATAROBOT_USE_CASE_ID".**
- The Pulumi stack hasn't been deployed yet. Run `dr start` to create the backing infrastructure first.

**I get HTTP 401 when using `use_case-<id>` as the entity header.**
- The DataRobot OTel collector's authorization API stores use cases under the internal type `experiment_container`. Use `experiment_container-<id>` in `OTEL_EXPORTER_OTLP_HEADERS` — this is what `dr start` writes automatically. The read APIs (dashboard, Tracing tab) accept `use_case` as the entity type; only the write header requires `experiment_container`.
