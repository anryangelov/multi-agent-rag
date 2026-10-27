---
id: CMP-6
title: Four-Eyes Review for Sensitive Changes
domain: compliance
kind: policy
version: 1
effective_date: 2025-07-01
status: current
classification: internal
owner: Compliance
---
# Four-Eyes Review for Sensitive Changes

A sensitive change on the automation platform is checked by a second
qualified person before it reaches production. One person can make a
mistake; two independent people rarely make the same one.

## When a four-eyes review is required

1. A workflow, connector or template that reads or writes **confidential
   data** (CMP-1) is created or changed.
2. A workflow step starts using the **cloud language model**.
3. A connector to a **new system** is created.
4. Access rights to confidential data are granted or changed.

## Who may review

The reviewer:

1. is not the author of the change;
2. does not report to the author;
3. has completed the platform review training;
4. for changes to connectors or code, is a developer; for changes to
   workflow definitions, may be a developer or a process analyst.

## What the reviewer checks

1. The change does what the request says and nothing more.
2. Data of each class goes only where the Data Classification Policy and
   the Cloud LLM Data Rules (CMP-2) allow.
3. Personal data is masked in logs (CMP-5).
4. The audit events are written (CMP-7).

## How it is recorded

The review happens in the platform console. The reviewer approves or
rejects the change version with a comment; the platform stores the
reviewer, the time and the version reviewed in the audit store. A change
cannot be released while its review is open.

## Timing

Reviews are answered within 3 working days. An urgent change can be
reviewed by the on-call Platform Engineering engineer, if that person
meets the conditions above.

## Relation to release approvals

The four-eyes review is separate from the release approvals in the
Production Release Standard (TEC-3). Both are needed; one person may not
be the reviewer and a release approver of the same change.
