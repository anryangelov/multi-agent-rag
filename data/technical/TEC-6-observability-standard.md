---
id: TEC-6
title: "Observability Standard: Metrics, Traces and Logs"
domain: technical
kind: standard
version: 1
effective_date: 2025-11-01
status: current
classification: internal
owner: Platform Engineering
---
# Observability Standard: Metrics, Traces and Logs

Every service and connector on the automation platform must be observable
in the same way, so that anyone on call can read any dashboard. The
platform service template (see TEC-1) implements this standard; teams that
use the template comply by default.

## Metrics

Every service exposes these metrics:

1. request rate per endpoint;
2. error rate per endpoint, where an error is a 5xx response or a failed
   workflow step;
3. latency per endpoint as p50, p95 and p99.

Connectors also expose the length of their request queue. For RPA
connectors this is the most useful signal of trouble.

## Alerts

| Alert | Condition |
|---|---|
| High error rate | error rate above 2% for 5 minutes |
| Slow API | p95 latency above 800 ms for 10 minutes |
| Connector queue | queue longer than 50 requests for 10 minutes |

Alerts page the on-call engineer of the owning team. Platform Engineering
is paged only for platform components.

## Traces

1. Every incoming request gets a correlation id, or keeps the one it
   arrives with.
2. The correlation id is passed to every connector call and written to
   every log line.
3. Traces are sampled at 10% in production and 100% in staging.

## Logs

1. Logs are structured JSON with at least: timestamp, service, level,
   correlation id and message.
2. Personal data is masked before it is written (Secure API Standard,
   CMP-5).
3. The default level in production is `info`. Debug level is temporary and
   follows the API Performance Troubleshooting Runbook (TEC-4).
4. Log retention follows the Data Retention Policy (CMP-3).

## Dashboards

Each service has one dashboard generated from the template: request rate,
error rate, latency and, for connectors, queue length. Custom panels are
added below the standard ones, never instead of them.
