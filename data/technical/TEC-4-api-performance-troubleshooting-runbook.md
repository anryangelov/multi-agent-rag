---
id: TEC-4
title: API Performance Troubleshooting Runbook
domain: technical
kind: runbook
version: 1
effective_date: 2026-05-20
classification: internal
owner: Platform Engineering, API team
---
# API Performance Troubleshooting Runbook

Use this runbook when a platform API is slower than its objective. The
objective for platform APIs is a p95 latency below 800 ms. The alert fires
when p95 stays above 800 ms for 10 minutes.

## Step 1: confirm and scope

1. Open the latency dashboard of the API and check p95 and p99 for the last
   hour.
2. Check whether all endpoints are slow or only some. One slow endpoint
   usually means one slow dependency.
3. Check the error rate. If it is above 2%, treat the case as an incident
   and follow the Platform Incident Response Runbook (TEC-7).

## Step 2: look for a recent change

1. Open the change log and list the releases of the last 24 hours for the
   API and its dependencies.
2. If a release matches the start of the slowdown, roll it back and watch
   the dashboard for 15 minutes.

## Step 3: check the dependencies

1. Open the trace view and sort the spans of slow requests by duration.
2. Calls to core banking through RPA connectors are the most common cause.
   RPA connectors drive old screens and handle one session at a time; when
   the queue is long, every request waits.
3. Check the database connection pool. A pool at 100% use means requests
   wait for a connection.

## Step 4: debug logging

If the traces do not explain the slowdown, turn on debug logging for the
API for at most 24 hours.

- Debug logs are kept for **30 days** and then deleted.
- Debug logs must be masked like all other logs (Secure API Standard,
  CMP-5). Never turn off masking to see the raw payload.
- Do not copy production logs to a laptop or a ticket. Read them in the log
  viewer, which enforces access rights.

## Step 5: escalate

If the cause is still unknown after one hour, page the on-call engineer of
Platform Engineering and attach the dashboard links, the traces you looked
at and the list of recent changes.
