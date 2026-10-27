---
id: TEC-2
title: Production Release Standard
domain: technical
kind: standard
version: 1
effective_date: 2025-01-15
status: superseded
classification: internal
owner: Platform Engineering
---
# Production Release Standard (version 1)

This standard defines what a release to the production environment of the
automation platform must satisfy.

## Scope

Every change that reaches production: new services, new versions of
existing services, connector updates and configuration changes that alter
behaviour.

## Approvals

A production release needs **one approver**: a senior engineer from the
team that owns the service. The approver checks that:

1. the pipeline passed in full, including the security scans;
2. the change was deployed to staging and tested there;
3. a rollback plan exists.

The approver must not be the author of the change.

## Release windows

Releases happen from Monday to Thursday, 09:00 to 16:00. Friday releases
are not allowed. A release outside the window is an emergency change and
needs the approval of the Platform Engineering lead in addition to the
normal approver.

## Responsibilities of the approver

The approver is responsible for the decision to release, not for the code.
If the release causes an incident, the approver takes part in the
post-incident review and explains what was checked. An approver who is
unsure asks for a second opinion before approving; a release is never
approved just to meet a deadline.

## Emergency changes

An emergency change fixes a production incident that cannot wait for the
next window. It follows the same checks, but the pipeline may skip the
staging deployment if the Platform Engineering lead agrees.

## Rollback

Every release must be reversible within 15 minutes. If a database migration
cannot be reversed, the release request must say so and describe the
recovery steps.

## Records

The release request, the approval and the result are recorded in the
change log of the platform. Records are kept according to the Data
Retention Policy.

## Exceptions

Exceptions to this standard are granted by the Platform Engineering lead
and recorded in the change log with a reason and an expiry date.
