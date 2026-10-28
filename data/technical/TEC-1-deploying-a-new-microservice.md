---
id: TEC-1
title: Deploying a New Microservice to the Automation Platform
domain: technical
kind: guide
version: 1
effective_date: 2026-02-15
classification: internal
owner: Platform Engineering
---
# Deploying a New Microservice to the Automation Platform

This guide walks a development team through the first deployment of a new
microservice on the automation platform. It describes the recommended path;
the binding rules are in the Production Release Standard (TEC-3) and the
Pre-Production Compliance Checklist (CMP-4).

## Before you write code

1. Register the service in the service catalog. Give it an owning team, a
   short description and the highest data classification it will handle
   (see the Data Classification Policy, CMP-1).
2. Create the repository from the platform service template. The template
   already contains the CI pipeline, a health endpoint, structured logging
   and the metrics required by the Observability Standard (TEC-6).
3. If the service calls a core banking system, do not call it directly.
   Use an existing connector from the connector registry, or build one as
   described in Building Connectors (TEC-5).

## The pipeline

Every push runs the same pipeline:

1. Unit tests.
2. Static code analysis (SAST) and a dependency vulnerability scan. A
   finding rated high or critical stops the pipeline.
3. Container image build and signing.
4. Automatic deployment to the `dev` environment.

Promotion to `test` and `staging` is a button in the pipeline. Staging runs
on masked copies of production data; real customer data never leaves
production (Secure API Standard, CMP-5).

## Going to production

1. Complete the Pre-Production Compliance Checklist (CMP-4) and attach it
   to the release request.
2. Prepare a rollback plan: the previous image tag and any database
   migration that must be reversed.
3. Get the approvals required by the Production Release Standard (TEC-3).
4. Release inside a release window: Tuesday to Thursday, 09:00 to 15:00.
   Releases outside the window need an emergency change.
5. Watch the service dashboard for 30 minutes after the release. If the
   error rate rises above 2%, roll back first and investigate later.

## Typical first-release timeline

| Step | Usual duration |
|---|---|
| Catalog entry and repository | half a day |
| Compliance checklist | 1 to 3 days |
| Approvals | 1 to 2 days |

Ask in the Platform Engineering channel if the template does not fit your
case; do not fork the pipeline.
