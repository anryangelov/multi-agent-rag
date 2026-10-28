---
id: TEC-9
title: "Post-Incident Review: Screening Connector Slowdown, 31 August 2026"
domain: technical
kind: report
version: 1
effective_date: 2026-09-07
classification: internal
owner: Platform Engineering
---
This review describes the slowdown of the RPA connector to the sanctions
screening system on Monday 31 August 2026, what we did about it and what
we will change. It was written by the incident commander with the owner of
the connector and discussed in a blameless review meeting on 4 September,
as the Platform Incident Response Runbook asks for every SEV1 and SEV2
incident. The incident was classified as SEV2: one critical workflow, the
pre-screening of sanctions alerts, was degraded for several hours, there
was a workaround, and no customer data was exposed.

The day started like every month end. At 08:10 the month-end batch of
sanctions alerts arrived from the screening system and the pre-screening
workflow began to process it. On a normal month end the queue of the
screening connector grows to about 40 requests and drains within two
hours, because the connector drives the screens of the screening system
with a single robot that handles one session at a time. At 08:35 the
connector queue alert fired: the queue had been longer than 50 requests
for 10 minutes, the threshold set in the Observability Standard. The alert
paged the on-call engineer of Platform Engineering, who acknowledged it at
08:38 and became the incident commander.

The first look at the dashboard showed a queue of about 180 requests and
still growing. The p95 latency of the screening API, which other workflows
call to read the status of an alert, had risen to 6.2 seconds against an
objective of 800 milliseconds. The error rate was normal, below one
percent, which told us that requests were slow rather than failing. The
incident commander followed the API Performance Troubleshooting Runbook.
The change log showed no release of the connector or the workflow in the
previous week, so a rollback was not an option. The trace view, sorted by
span duration, was more helpful: almost every robot session spent about 30
seconds in one step, the opening of the alert detail screen, while the
same step had taken under two seconds in July.

To see what the robot was doing in that step, the incident commander
turned on debug logging for the connector at 09:15. The runbook allows
this for at most 24 hours; we turned it off again at 15:10. Masking stayed
on, as the Secure API Standard requires, and the logs were read only in
the log viewer. They showed that the robot looked for the alert reference
field on the detail screen, did not find it, waited for its 30-second
timeout and then fell back to a slower navigation path that happened to
work. Every session therefore took about 30 seconds longer than before,
which at month-end volume was enough to make the queue grow faster than
the single robot could empty it.

The owner of the connector found the reason at 10:05. On Friday 28 August
the vendor of the screening system had installed a patch that moved the
alert reference field from the top of the detail screen into a new panel
on the right. The screen looked almost the same to a person, but the
selector that the robot uses to find the field no longer matched. Nobody on
the platform side knew about the patch. The Building Connectors guide asks
connector owners to record the screens their robot depends on so that the
owning team is warned before a change, and the connector owner had done so,
but the team that runs the screening system was not on the notification
list for this connector. The list had been copied from an older connector
before the screening system moved to its current team.

At 10:20, to win time, the incident commander paused two low-priority
workflows that also use the screening connector: a weekly report and a
data quality check. Pausing is allowed to the incident commander from the
platform console, and paused workflows keep their queued runs. This freed
some robot capacity for the pre-screening of alerts, and the queue stopped
growing at about 230 requests. The process owners of the two paused
workflows were informed automatically by the console and by a message in
the incident channel.

The owner of the connector changed the selector to find the field in its
new place and tested the change in staging against a copy of the patched
screen. Because the fix could not wait for the next release window, it was
released at 11:45 as an emergency change, with the two approvers that the
Production Release Standard requires and the approval of the Platform
Engineering lead. The sessions went back to under two seconds for the
detail screen within minutes. The queue drained by 14:00, the two paused
workflows were resumed at 14:10, and the incident was closed at 15:30
after the debug logging had been turned off and the dashboard had stayed
normal for an hour.

The impact was a delay, not a loss. The pre-screening of the month-end
alerts finished about five hours later than usual. Compliance Operations
confirmed that no regulatory deadline was missed, because the screening
analysts start their manual review of month-end alerts on the second
working day. No data was exposed and no alert was lost: every queued
request was processed once.

In the review meeting we agreed on three causes. The direct cause was the
screen change that broke the robot's selector. The reason it reached
production unnoticed was the incomplete notification list, together with
the absence of any automatic check of the screens after a change on the
vendor side. The reason it hurt so much was capacity: with one robot, any
slowdown at month end turns into a long queue, as the portfolio review for
the second quarter had already pointed out.

We agreed on these actions. First, the team that runs the screening system
is added to the notification list of the connector, and Platform
Engineering checks the notification lists of all RPA connectors against
the current owners of their target systems by the end of September.
Second, the connector gets a nightly contract test that opens each screen
the robot depends on in the test instance of the screening system and
checks that every field is found; the vendor installs patches in the test
instance a week before production, so the test will warn us in time.
Third, the robot's timeout for finding a field is lowered from 30 seconds
to 5 seconds, and a field that is not found raises an alert instead of
falling back silently. Fourth, Platform Engineering asks the Process Board
to fund a second robot for the screening system, so that month-end volume
no longer depends on a single session.

One point came up that is not an action for this team. The pre-screening
workflow has no way to tell the screening analysts that it is running
late. In this incident the analysts heard about the delay from the incident
channel by chance. The process owner of Compliance Operations will look at
adding a notification step to the workflow and will bring it to the
process analyst as a change request.

The incident commander thanks the owner of the connector and the
screening system team, who answered within minutes once they were
contacted, and the process owners of the two paused workflows for their
patience.
