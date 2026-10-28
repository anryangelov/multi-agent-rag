---
id: TEC-3
title: Production Release Standard
domain: technical
kind: standard
version: 2
effective_date: 2026-02-01
status: current
supersedes: TEC-2
classification: internal
owner: Platform Engineering
---
# Production Release Standard (version 2)

This standard defines what a release to the production environment of the
automation platform must satisfy. It replaces version 1 (TEC-2) from
1 February 2026.

## What changed from version 1

- Two approvers instead of one.
- The release window is shorter and excludes Mondays.
- The Pre-Production Compliance Checklist (CMP-4) is mandatory for the
  first release of a service.

## Scope

Every change that reaches production: new services, new versions of
existing services, connector updates and configuration changes that alter
behaviour.

## Approvals

A production release needs **two approvers**:

1. a senior engineer from the team that owns the service;
2. an engineer from Platform Engineering.

Neither approver may be the author of the change. Together they check that:

1. the pipeline passed in full, including the security scans;
2. the change was deployed to staging and tested there;
3. a rollback plan exists;
4. for the first release of a service, the Pre-Production Compliance
   Checklist (CMP-4) is complete and attached.

A change that touches confidential data also needs a four-eyes review under
CMP-6. That review is separate from the release approvals.

## Release windows

Releases happen from Tuesday to Thursday, 09:00 to 15:00. A release outside
the window is an emergency change and needs the approval of the Platform
Engineering lead in addition to the two normal approvers.

## Emergency changes

An emergency change fixes a production incident that cannot wait for the
next window. It needs the same two approvers; the on-call Platform
Engineering engineer may act as the second one.

## Rollback

Every release must be reversible within 15 minutes. If a database migration
cannot be reversed, the release request must say so and describe the
recovery steps.

A workflow is rolled back by switching to its previous version in the
platform console, as described in Changing a Running Automation (BUS-7).

## Records

The release request, both approvals and the result are recorded in the
change log of the platform and kept according to the Data Retention Policy
(CMP-3).
