---
id: CMP-4
title: Pre-Production Compliance Checklist for Services
domain: compliance
kind: standard
version: 1
effective_date: 2025-10-01
status: current
classification: internal
owner: Compliance, Information Security
---
# Pre-Production Compliance Checklist for Services

A new service or connector on the automation platform must pass this
checklist before its first production release. The completed checklist is
attached to the release request (Production Release Standard, TEC-3).

## The checklist

### Data

1. The highest data classification the service handles is declared in the
   service catalog (CMP-1).
2. If the service processes confidential customer data, a data protection
   impact assessment (DPIA) is completed and signed by the Data Protection
   Office.
3. If the service sends anything to the cloud language model, it does so
   only through the certified AI connector, and the use case is registered
   (CMP-2).
4. Retention of the service's logs and records is configured as in the Data
   Retention Policy (CMP-3).

### Security

5. The security scans of the pipeline (SAST and dependency scan) show no
   open finding rated high or critical.
6. Secrets are stored in the vault; none are in the code, the image or the
   configuration files.
7. APIs follow the Secure API Standard (CMP-5): authentication, token
   lifetime, rate limits and masking of personal data in logs.

### Traceability

8. The service writes the audit events required by Audit Logging for
   Automation Runs (CMP-7).
9. Logs, metrics and traces follow the Observability Standard (TEC-6).

### Review

10. If the service touches confidential data, the four-eyes review under
    CMP-6 is done and recorded.

## Who signs

The checklist is signed by the service owner and checked by a compliance
officer. The compliance officer answers within 3 working days.

An incomplete checklist is returned to the service owner with the missing
items listed; the release cannot be approved until it comes back complete.

## When to repeat

Repeat the checklist when a service starts handling a higher data class,
adds a new external destination or starts using the cloud language model.
