---
id: TEC-5
title: "Building Connectors: API and RPA"
domain: technical
kind: guide
version: 1
effective_date: 2025-10-01
classification: internal
owner: Platform Engineering
---
# Building Connectors: API and RPA

A connector is the only way a workflow on the automation platform talks to
another system. Workflows never call systems directly. This guide explains
which kind of connector to build and how it moves from a first version to
something business users can pick from the catalog.

## Three kinds of connectors

| Kind | When | Example |
|---|---|---|
| API connector | The target system has an API | Card management system with a REST API |
| RPA connector | The target system has no API, only screens | A core banking module from before the mergers |
| AI connector | The step calls the cloud language model | Summarising a customer complaint |

### API connector

Wrap the API in the connector SDK. The SDK handles authentication (Secure
API Standard, CMP-5), retries, timeouts and the audit events required by
Audit Logging for Automation Runs (CMP-7).

### RPA connector

An RPA connector drives the screens of a legacy system with a robot user.
It is slow and fragile: one robot handles one session at a time and a
screen change breaks it. Build one only when no API exists, and record the
screens it depends on so the owning team is warned before a change.

### AI connector

There is one AI connector, maintained by Platform Engineering. It sends
prompts to Azure OpenAI and enforces the Cloud LLM Data Rules (CMP-2):
it refuses input marked confidential unless the use case has a recorded
approval from the Data Protection Office.

## The life of a connector

1. A new connector starts in the **experimental** tier. It runs only in the
   sandbox.
2. When a team uses it in its own workflows, it moves to the **team** tier.
   A team-tier connector may also be used by another team if both team
   leads agree.
3. After a review by Platform Engineering and Information Security it
   becomes **certified** and appears in the catalog for business users.

The rules for each tier are in Template and Connector Tiers (BUS-3). A
connector that reads or writes confidential data needs a four-eyes review
(CMP-6) before it leaves the experimental tier.

## Checklist for a new connector

1. Name the target system and its owner.
2. Declare the highest data classification the connector handles.
3. Write contract tests against a test instance of the target system.
4. Document timeouts and what the connector does when the target is down.
