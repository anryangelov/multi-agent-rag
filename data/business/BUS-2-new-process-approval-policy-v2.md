---
id: BUS-2
title: New Process Approval Policy
domain: business
kind: policy
version: 2
effective_date: 2026-04-01
supersedes: BUS-1
classification: internal
owner: Process Excellence Office
---
# New Process Approval Policy (version 2)

This policy defines who approves a new automated process on the automation
platform before work on it starts. It replaces version 1 (BUS-1) from
1 April 2026.

## What changed from version 1

The department head is no longer the only approver. Processes that handle
customer data, or that use the cloud language model, need further
approvals.

## Who approves

| The process... | Approvals needed |
|---|---|
| uses only public or internal data | head of the requesting department |
| handles customer data (confidential under CMP-1) | head of the requesting department **and** the Process Board |
| sends any data to the cloud language model | the approvals above **and** a sign-off from the Data Protection Office (CMP-2) |

For example, a workflow that matches supplier invoices uses internal data
and needs only the department head; a workflow that checks customer
complaints handles confidential data and also goes to the Process Board.

The Process Board meets every two weeks. A request must reach the board
secretary five working days before a meeting to be on its agenda.

## The request

The requesting department submits a process request with:

1. the process today, step by step, and who does each step;
2. a business case following Business Case and ROI Rules (BUS-5);
3. the systems the process touches and the highest data classification it
   handles;
4. the process owner, who is accountable for the automated process.

## Assessment

A process analyst reviews the request within 10 working days, as described
in the Process Analyst Handbook (BUS-4), and attaches the assessment.

## After approval

1. The process is built and goes through a four-eyes review if it touches
   confidential data (CMP-6).
2. Releases follow the Production Release Standard (TEC-3).
3. Later changes follow Changing a Running Automation (BUS-7).
