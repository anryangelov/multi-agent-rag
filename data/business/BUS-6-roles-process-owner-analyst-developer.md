---
id: BUS-6
title: "Roles: Process Owner, Process Analyst, Developer"
domain: business
kind: standard
version: 1
effective_date: 2025-06-01
status: current
classification: public
owner: Process Excellence Office
---
# Roles: Process Owner, Process Analyst, Developer

Three roles work together on every automated process on the automation
platform. One person can hold more than one role, but every role must be
filled.

## Process owner

A person in the business department that runs the process.

- Accountable for the process and its results, before and after
  automation.
- Requests the automation and signs the business case.
- Decides on changes to a running automation (BUS-7).
- Is informed automatically when the workflow is paused.

## Process analyst

A person from the Process Excellence Office, or a trained analyst inside a
department.

- Maps the process end to end and checks whether it should be automated.
- Assembles the workflow from certified templates and blocks.
- Writes the assessment that goes to the approvers (BUS-2).
- Works on the canvas and the wizard; does not need to write code.

## Developer

An engineer in Platform Engineering or in a department's engineering team.

- Builds the blocks, connectors and custom logic that templates do not
  cover (TEC-5).
- Works with the same workflow definitions as code, through the API and
  the command line.
- Owns the reliability of what they build: tests, observability (TEC-6)
  and on-call support.

## Moving between roles

Analysts who want to write code can take the platform developer training;
developers who want to understand the business side can shadow an analyst
for a request. The platform supports both paths, because the same workflow
definition is used on the canvas and in code.

## Who does what

| Task | Process owner | Process analyst | Developer |
|---|---|---|---|
| Request the automation | does | supports | |
| Map the process | reviews | does | |
| Build from templates | reviews | does | supports |
| Build a new connector | | specifies | does |
| Approve go-live | approves | | |
| Fix a failed run | is informed | analyses | fixes |
