---
id: CMP-1
title: Data Classification Policy
domain: compliance
kind: policy
version: 1
effective_date: 2025-03-01
classification: public
owner: Data Protection Office
---
# Data Classification Policy

Every piece of information at Orla Bank belongs to one of three classes.
The class decides who may see it, where it may be stored and whether it may
leave the bank.

## The classes

| Class | Meaning | Examples |
|---|---|---|
| Public | Meant for anyone, inside or outside the bank | published product terms, this policy, the platform architecture overview |
| Internal | For employees only; harm is limited if it leaks | internal standards and guides, runbooks, team procedures |
| Confidential | Serious harm to customers or the bank if it leaks | customer personal data, account and card numbers, complaint texts, incident reports, financial results before publication |

**Customer data is always confidential**, including names, addresses,
IBANs, personal identification numbers and the content of customer
messages.

## Who may see what

1. Every employee may see public and internal information.
2. Confidential information is available only to employees whose role
   needs it. Access is granted per role and reviewed every six months.
3. A document or dataset that mixes classes takes the highest class it
   contains.

## Labelling

1. Every document carries its class in its metadata.
2. Every system and every workflow on the automation platform declares the
   highest class of data it handles.
3. Unlabelled information is treated as confidential until labelled.

## Handling rules

| Rule | Public | Internal | Confidential |
|---|---|---|---|
| Store on-premise | yes | yes | yes, encrypted |
| Send by e-mail inside the bank | yes | yes | only encrypted |
| Send to the cloud language model | yes | yes | no, except as allowed by CMP-2 |
| Use in test environments | yes | yes | only masked |

## Responsibilities

The owner of a document or dataset assigns its class. The Data Protection
Office answers questions about classification and decides disputes.
