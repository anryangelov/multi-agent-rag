---
id: CMP-2
title: "Cloud LLM Data Rules: What May Be Sent to Azure OpenAI"
domain: compliance
kind: policy
version: 1
effective_date: 2026-04-01
status: current
classification: internal
owner: Data Protection Office
---
# Cloud LLM Data Rules: What May Be Sent to Azure OpenAI

Azure OpenAI is the only external service the automation platform uses.
This policy defines what data may be sent to it and how.

## The one path

1. Data reaches the language model **only through the certified AI
   connector** maintained by Platform Engineering (TEC-5).
2. No team builds its own connection to Azure OpenAI. The outbound gateway
   rejects calls that do not come from the certified AI connector.

## What may be sent

| Data class (CMP-1) | May be sent? |
|---|---|
| Public | yes |
| Internal | yes |
| Confidential | no, unless all conditions below are met |

Confidential data may be sent only when:

1. the use case is registered and has a written sign-off from the Data
   Protection Office;
2. customer identifiers are pseudonymised before sending: names, IBANs,
   card numbers and personal identification numbers are replaced by
   tokens that the AI connector maps back after the answer returns;
3. the workflow has passed a four-eyes review (CMP-6).

## Registering a use case

The process owner registers the use case with:

1. the purpose and the workflow that uses the model;
2. the data classes sent and the fields that are pseudonymised;
3. the expected number of calls per month.

The Data Protection Office answers within 10 working days. A new
process that needs this sign-off also follows the New Process Approval
Policy (BUS-2).

## Records

1. The AI connector writes every call to the audit store (CMP-7): the
   workflow, the use case, the data classes and the size of the prompt.
2. Prompts and responses are kept for 90 days for investigation and then
   deleted (CMP-3).

## Breaches

Sending confidential data outside these rules is a data incident. Follow
the Platform Incident Response Runbook (TEC-7) and notify the Data
Protection Office within one hour.
