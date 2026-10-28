---
id: TEC-7
title: Platform Incident Response Runbook
domain: technical
kind: runbook
version: 1
effective_date: 2025-12-01
classification: internal
owner: Platform Engineering
---
# Platform Incident Response Runbook

Use this runbook when the automation platform, or a workflow running on it,
is down or produces wrong results.

## Severity

| Severity | Meaning | First response |
|---|---|---|
| SEV1 | Platform down, or customer data exposed | 15 minutes, day and night |
| SEV2 | One critical workflow down or wrong | 30 minutes in working hours, 1 hour at night |
| SEV3 | Degraded, with a workaround | next working day |

## Who to call

1. Page the on-call engineer of Platform Engineering through the paging
   tool. The rota covers every day of the year, including nights.
2. For a workflow problem, also page the on-call engineer of the team that
   owns the workflow.
3. If customer data may have been exposed, notify the Data Protection
   Office within **1 hour**, whatever the time of day.

## Steps

1. The first responder becomes the incident commander until someone else
   takes over explicitly.
2. Open an incident channel and post the severity, the symptoms and the
   correlation ids of failed requests.
3. Stop the damage first: pause the workflow, roll back the last release
   or disable the connector. Investigation comes after.
4. Post an update in the channel every 30 minutes for SEV1 and every hour
   for SEV2.
5. Close the incident when the service works and the cause is understood
   or contained.

## Pausing a workflow

The incident commander can pause any workflow from the platform console.
A paused workflow keeps its queued runs and resumes them when unpaused. The
process owner is informed automatically.

## After the incident

1. A post-incident review takes place within 5 working days for SEV1 and
   SEV2.
2. The review is blameless and produces actions with owners and dates.
3. A data incident also gets an incident report for the Data Protection
   Office.
