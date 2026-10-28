---
id: CMP-3
title: Data Retention Policy
domain: compliance
kind: policy
version: 1
effective_date: 2025-06-01
classification: internal
owner: Compliance
---
# Data Retention Policy

This policy defines how long Orla Bank keeps operational records of its IT
systems, including the automation platform. Customer records (accounts,
contracts) follow the separate customer records schedule.

## Retention periods

| Record | Kept for | Then |
|---|---|---|
| API request logs, **including debug logs** | **90 days** | deleted |
| Application logs | 90 days | deleted |
| Prompts and responses of the cloud language model | 90 days | deleted |
| Audit store records of automation runs | 10 years | archived, then deleted |
| Change log (releases and approvals) | 5 years | deleted |
| Sandbox data | 14 days | deleted |

## Why these periods

- **90 days** for logs covers the longest regular investigation: monthly
  reconciliation plus the time to open and close a case.
- **10 years** for the audit store follows the record-keeping obligations
  that apply to banks.

## Rules

1. Teams may not keep records **shorter** or **longer** than this policy
   says. A shorter period destroys evidence; a longer one keeps personal
   data without a reason.
2. Deletion is automatic. Platform Engineering configures the log and
   audit stores; teams do not run their own deletion jobs.
3. Records under a legal hold are not deleted until the hold is lifted.
   Compliance places and lifts holds.

## Exceptions

An exception is granted only by Compliance, in writing, for a named record
type and a limited time. Team runbooks and guides cannot set retention
periods; where they mention one, this policy prevails.

## Review

Compliance reviews this policy once a year, and earlier when a new type of
record appears on the platform. Questions about a record type that is not
in the table go to Compliance; until they answer, keep the record for 90
days.
