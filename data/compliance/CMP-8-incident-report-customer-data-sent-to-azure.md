---
id: CMP-8
title: "Incident Report: Customer Data Sent to Azure, 2026-03"
domain: compliance
kind: report
version: 1
effective_date: 2026-03-27
status: current
classification: confidential
owner: Data Protection Office
---
# Incident Report: Customer Data Sent to Azure, March 2026

Severity: SEV1 (customer data exposed). Status: closed, one action open.

## What happened

From 12 to 15 March 2026, the workflow **Complaint summarisation** of
Customer Care sent the full text of about **1,200 customer complaints** to
Azure OpenAI. The texts included customer names, IBANs and phone numbers.
Nothing was pseudonymised.

## Timeline

1. **12 March:** the workflow went live using an experimental connector
   that called Azure OpenAI directly, instead of the certified AI
   connector. The team lead had approved this, following section 4 of the
   Process Analyst Handbook (BUS-4).
2. **15 March, 08:40:** the nightly audit check (CMP-7) flagged language
   model calls without a registered use case.
3. **15 March, 09:05:** the on-call engineer paused the workflow (TEC-7).
4. **15 March, 09:30:** the Data Protection Office was notified.

## Impact

- About 1,200 complaints, from about 1,100 customers.
- The data went only to the bank's own Azure OpenAI deployment in the EU.
  The contract excludes the use of prompts for training.
- The Data Protection Office assessed the risk to customers as low.

## Root cause

1. The experimental connector skipped the data checks of the certified AI
   connector.
2. The outbound gateway allowed any platform component to call the
   approved Azure endpoint.
3. The Process Analyst Handbook (BUS-4) allows experimental connectors in
   production with a team lead's approval. This contradicts Template and
   Connector Tiers (BUS-3), which forbids it without exception.

## Actions

| Action | Owner | Status |
|---|---|---|
| Remove the experimental connector | Platform Engineering | done |
| Gateway accepts language model calls only from the certified AI connector | Platform Engineering | done |
| Publish the Cloud LLM Data Rules (CMP-2) | Data Protection Office | done, 1 April 2026 |
| Correct section 4 of the Process Analyst Handbook (BUS-4) | Process Excellence Office | **open** |
