---
id: CMP-5
title: Secure API Standard
domain: compliance
kind: standard
version: 1
effective_date: 2025-08-01
status: current
classification: internal
owner: Information Security
---
# Secure API Standard

Every API on the automation platform, internal or exposed to other bank
systems, follows this standard.

## Authentication

1. Service-to-service calls use mutual TLS inside the platform and OAuth 2
   client credentials for calls from other bank systems.
2. Access tokens expire after **15 minutes**. Refresh tokens are not used
   between services.
3. Every API checks the caller's permissions on every request; a valid
   token alone is not enough.

## Secrets

1. Secrets live only in the vault and are read at start-up.
2. Secrets are rotated at least every 90 days, and at once after anyone
   who knew them leaves the team.
3. A secret found in code, an image or a ticket is treated as leaked and
   rotated immediately.

## Rate limits

Every API has a rate limit per caller. The default is 100 requests per
second; owners may set a lower one. A caller over the limit receives `429`
and must back off.

## Personal data in logs

1. Personal data is **masked before it is written** to any log, trace or
   error message: names, IBANs, card numbers, personal identification
   numbers, phone numbers and e-mail addresses.
2. Masking stays on at every log level, including debug.
3. Request and response bodies are not logged in full; log the fields you
   need, masked.

## Troubleshooting production

1. Production logs are read in the log viewer, which enforces access
   rights. They are never copied to laptops, tickets or chat.
2. Access to production logs of a service that handles confidential data
   requires an open incident or a support ticket.
3. Real customer data is never copied to test environments; use the masked
   copies provided by the platform.

## Exceptions

Exceptions are granted by Information Security, in writing, with an expiry
date. An expired exception is treated as a finding.
