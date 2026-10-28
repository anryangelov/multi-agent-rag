---
id: BUS-3
title: Template and Connector Tiers
domain: business
kind: policy
version: 1
effective_date: 2025-11-01
classification: internal
owner: Process Excellence Office
---
# Template and Connector Tiers

Templates and connectors on the automation platform belong to one of three
tiers. The tier says who may use them and where they may run.

## The tiers

| Tier | Who can use it | Where it runs | Reviewed by |
|---|---|---|---|
| Certified | every employee, from the catalog | production | Platform Engineering and Information Security |
| Team | the team that built it | production, for that team's workflows | the owning team |
| Experimental | its authors | sandbox only | nobody yet |

## Rules

1. **Experimental templates and connectors never run in production.** There
   are no exceptions to this rule.
2. An experimental item that is not promoted within 90 days is removed
   from the sandbox.
3. Business users see only certified items in the catalog.
4. A team item that another team wants to use must first become certified.

## Promotion

### Experimental to team

1. The owning team writes contract tests and documentation.
2. If the item handles confidential data, it passes a four-eyes review
   (CMP-6).
3. The team lead records the promotion in the registry.

### Team to certified

1. Platform Engineering reviews reliability, observability (TEC-6) and
   support.
2. Information Security reviews access, secrets and data handling (CMP-5).
3. The item gets a named owner who answers support requests.

## Why the tiers exist

Business users build workflows without reading code. The tiers let them
trust what they pick from the catalog: everything they can see has been
reviewed for reliability and security. Developers keep the freedom to try
new things in the sandbox without asking anyone first.

## Demotion

A certified item whose owner leaves without a successor, or that fails a
review, goes back to the team tier. Workflows that use it keep running, but
no new workflows can select it.
