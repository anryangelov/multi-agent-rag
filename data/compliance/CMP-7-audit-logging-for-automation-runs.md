---
id: CMP-7
title: Audit Logging for Automation Runs
domain: compliance
kind: standard
version: 1
effective_date: 2025-07-01
status: current
classification: internal
owner: Compliance, Internal Audit
---
# Audit Logging for Automation Runs

Every run of an automated workflow leaves a record that shows what
happened, on whose behalf and with which data. Internal Audit and
regulators read these records; they must be complete and must not change.

## What is recorded for every run

1. Run id and the workflow id with its exact version.
2. Who or what started the run: a user, a schedule or another system.
3. Start time, end time and the result: succeeded, failed or cancelled.
4. Every connector call: the connector, the target system and the outcome.
5. The highest data class the run touched (CMP-1).
6. Every call to the cloud language model: the use case, the data classes
   sent and the prompt size (see CMP-2).
7. Every manual action during the run, such as an approval or a correction,
   with the person who made it.

Audit records contain identifiers and metadata, not the business data
itself: a run that processes a payment records the payment id, not the
account number.

## Where it is stored

1. Records go to the audit store, which is append-only: nobody can edit or
   delete a record before its retention period ends.
2. Records are kept for 10 years (Data Retention Policy, CMP-3).
3. Read access is limited to Compliance, Internal Audit, the Data
   Protection Office and, for their own workflows, process owners.

## Also recorded

- Pauses, resumptions and rollbacks of workflows (TEC-7, BUS-7).
- Four-eyes reviews and their results (CMP-6).
- Changes of a workflow definition: who, when and which version.

## Checks

The audit store is checked every night for gaps: a run without an end
record, or a connector call without a run. Gaps are reported to the
owning team and to Compliance the next morning, and stay open until the
team explains them.
