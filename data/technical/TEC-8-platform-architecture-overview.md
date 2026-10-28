---
id: TEC-8
title: Platform Architecture Overview
domain: technical
kind: guide
version: 1
effective_date: 2025-09-01
classification: public
owner: Architecture Office
---
# Platform Architecture Overview

Orla Bank runs on core systems that are decades old and come from several
banks that merged into Orla over the years. Some of these systems have
APIs; some can only be reached through their screens. The automation
platform sits on top of them and gives employees one place to build and run
automated workflows.

## Where things run

- **On-premise:** everything that stores or processes bank data. The
  platform runs on the bank's own Kubernetes clusters in two data centres.
- **Cloud:** only the language models, through Azure OpenAI. No other cloud
  service is used.

## Main components

| Component | What it does |
|---|---|
| Workflow engine | Runs workflow definitions step by step and keeps their state |
| Template catalog | Ready-made workflows and blocks that business users start from |
| Connector registry | The connectors to other systems (API, RPA and the AI connector) |
| Platform console | Where workflows are built, started, paused and monitored |
| Audit store | Append-only record of every workflow run |

## One definition, several views

A workflow is stored as one definition. Business users edit it on a canvas
or through a wizard; developers edit the same definition as code. The views
change how people work with a workflow, not what is stored.

## Integration with legacy systems

1. A workflow step never calls a core system directly; it calls a
   connector.
2. A connector to a system with an API is an API connector.
3. A connector to a system without an API is an RPA connector: a robot user
   that drives the screens.
4. The AI connector is the only path to the cloud language model and
   applies the data rules of the bank.

## Security boundary

All traffic between the platform and Azure OpenAI goes through one
outbound gateway. The gateway logs every call and blocks any destination
other than the approved Azure endpoints.
