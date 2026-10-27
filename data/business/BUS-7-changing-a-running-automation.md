---
id: BUS-7
title: Changing a Running Automation
domain: business
kind: guide
version: 1
effective_date: 2025-09-15
status: current
classification: internal
owner: Process Excellence Office
---
# Changing a Running Automation

Automated processes change: a form gets a new field, a threshold moves, a
system is replaced. This guide explains how to change a workflow that is
already in production without stopping the business.

## Minor and major changes

| Change | Kind | Who approves |
|---|---|---|
| A parameter, such as a threshold or an e-mail address | minor | process owner |
| A newer version of the same certified template | minor | process owner |
| A new step that uses an already approved connector | minor | process owner |
| A new data source or a new connector | major | as for a new process (BUS-2) |
| Data of a higher classification than before | major | as for a new process (BUS-2) |
| Sending data to the cloud language model for the first time | major | as for a new process (BUS-2) |

When in doubt, treat the change as major.

## How a change is made

1. The process analyst or the developer edits the workflow definition. The
   platform stores every saved definition as a new version; old versions
   are never overwritten.
2. The new version runs in the sandbox against test data.
3. The approver approves the new version in the platform console.
4. The release follows the Production Release Standard (TEC-3).

## Runs in progress

A run that started on the old version finishes on the old version. Only
new runs use the new version. This is why a change never breaks a run that
is half done.

## Rolling back

The process owner can switch a workflow back to its previous version from
the console. A rollback is not a change and needs no approval, but it is
recorded in the audit store (CMP-7).
