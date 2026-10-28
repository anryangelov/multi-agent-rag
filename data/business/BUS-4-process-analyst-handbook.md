---
id: BUS-4
title: Process Analyst Handbook
domain: business
kind: guide
version: 1
effective_date: 2026-01-20
classification: internal
owner: Process Excellence Office
---
# Process Analyst Handbook

This handbook is for process analysts: the people who turn a request from a
department into a workflow on the automation platform. It describes good
practice; the binding rules are in the policies it links to.

## 1. Understand the process end to end

1. Sit with the people who do the work today. Watch at least three real
   cases, including one that goes wrong.
2. Draw the process from the first trigger to the last output, with every
   system and every hand-over.
3. Count the volume: cases per month and minutes per case. The business
   case (BUS-5) needs these numbers.

## 2. Decide whether to automate

Automate when the process is stable, frequent and rule-based. Do not
automate a process that the department is about to change; fix the process
first.

## 3. Assemble, do not build

1. Start from the template catalog. Most requests fit an existing
   certified template with a few changed parameters.
2. If a block is missing, ask the developers for it. Describe the inputs,
   outputs and the systems involved.
3. Check the data classification of every system the workflow touches
   (CMP-1).

## 4. Connectors

Prefer certified connectors. In urgent cases, an experimental connector
can be used in production **with the approval of your team lead**, as long
as it is replaced by a certified one within three months.

## 5. Hand-over to the approvers

Write the assessment for the request: the process map, the volume, the
proposed templates and connectors, and the risks. Attach it to the process
request; the approvals are described in the New Process Approval Policy.

## 6. After go-live

1. Check the first 20 runs with the process owner, including any run that
   needed a manual correction.
2. Compare the real volume and time saved with the business case after
   three months.
3. If a new version of the workflow misbehaves, do not switch back to the
   previous version on your own: a rollback needs the approval of your
   team lead first.
