---
id: BUS-9
title: Process Board Minutes, 16 September 2026
domain: business
kind: report
version: 1
effective_date: 2026-09-16
status: current
classification: internal
owner: Process Board secretary
---
Minutes of the Process Board meeting held on Wednesday 16 September 2026,
from 14:00 to 15:40, in the board room on the fourth floor and online.
Present were the Chief Operating Officer, who chaired the meeting, the
head of the Process Excellence Office, the lead of Platform Engineering, a
representative of the Data Protection Office, a representative of
Information Security, a representative of Finance and the board secretary,
who took these minutes. The head of Retail Operations and the process owner
of Customer Care joined for the items that concerned their departments.
The chair opened the meeting by noting that a quorum was present and that
every request on the agenda had reached the secretary at least five
working days before the meeting, as the New Process Approval Policy
requires.

The minutes of the previous meeting, held on 2 September, were approved
without changes. The secretary reported that all actions from that meeting
were closed except one, the correction of the Process Analyst Handbook,
which is discussed further below.

The board then turned to the follow-up of the portfolio review for the
second quarter. The head of the Process Excellence Office reminded the
board that the review had shown one process saving clearly less than its
business case, the pre-screening of sanctions alerts, and that the reason
was the capacity of the RPA connector to the screening system, which
handles one session at a time. The lead of Platform Engineering added that
the problem had become visible in production on 31 August, when month-end
volumes met a slowdown of the connector, and referred the board to the
post-incident review published on 7 September. The slowdown itself had a
separate cause that has been fixed, but the review confirmed that a single
robot leaves no spare capacity at month end. Finance confirmed that the
cost of a second robot, including the licence and the virtual machine,
fits within this year's operations budget and does not need a separate
request. After a short discussion about whether an API to the screening
system could replace the robot, which the lead of Platform Engineering
said is not expected from the vendor before 2028, the board approved the
funding of a second RPA robot for the screening system. Platform Engineering
will install and test it so that it is available before the month-end run
of November. The process owner of Compliance Operations will be informed by
the secretary.

The next item was the use of the cloud language model. The board had been
asked, in the portfolio review, to make the certified AI connector
mandatory for every workflow that uses the language model. The
representative of the Data Protection Office pointed out that the Cloud LLM
Data Rules, in force since 1 April, already make the certified AI connector
the only permitted path, and that the outbound gateway enforces it since
the March incident. The board therefore did not need to adopt a new rule.
It confirmed the existing one and asked the Data Protection Office to
report to the board once a quarter on the registered use cases: how many
there are, which data classes they send and whether any call was refused by
the connector. The first report is expected at the meeting in December.

The process owner of Customer Care then asked the board to restart the
complaint summarisation workflow, which has been paused since 15 March. The
representative of the Data Protection Office confirmed that the office had
signed off the use case on 9 September for the new version of the workflow,
in which customer names, IBANs and phone numbers are replaced by tokens
before any text is sent to the model. The representative of Information
Security confirmed that the four-eyes review of the new version was done
and recorded, and that the workflow now uses the certified AI connector.
The board approved the restart. It asked the process owner to check the
first 20 runs personally together with the process analyst, and to report
any run that needed a manual correction at the next meeting. The chair
noted that this is the first workflow to send pseudonymised confidential
data to the model and that the board expects the quarterly report of the
Data Protection Office to show how it behaves.

The board then considered new process requests. The head of Retail
Operations presented the request to automate the verification of customer
address changes. Today an employee compares the new address with the
customer's identity document and the postal register by hand, for about
900 changes a month. The process handles customer data, which is
confidential under the Data Classification Policy, and therefore needs the
approval of this board in addition to the department head, who had already
approved it. The process analyst's assessment proposed a certified template
for document checks and the existing API connector to the customer master
system; no new connector is needed and the language model is not used. The
board approved the request. It entered the build queue on the same day.

A second request, the extension of supplier invoice matching to a second
group of suppliers, had been placed on the agenda by mistake. The secretary
explained that the process uses only internal data, so under the New
Process Approval Policy it needs only the approval of the head of Finance.
The item was removed from the agenda and returned to Finance.

Under the item on open actions, the head of the Process Excellence Office
reported that section 4 of the Process Analyst Handbook has still not been
corrected. That section says that an experimental connector may be used in
production with the approval of a team lead, which Template and Connector
Tiers does not allow, and which played a part in the March incident. The
head of the office explained that the correction had been delayed because
the office wanted to rewrite the whole chapter on connectors at the same
time. The board did not accept the delay. It asked the office to publish
the corrected section on its own by 31 October 2026 and to leave the
rewrite of the chapter for later. Until then, the head of the office will
remind all analysts in writing that the tier policy applies.

Under any other business, the head of Retail Operations suggested that the
board meet every week instead of every two weeks, because requests that
miss the agenda deadline wait almost a month. The chair answered that a
weekly meeting would be hard to staff and that the problem is the deadline,
not the rhythm. The board decided to keep meeting every two weeks and to
allow the chair to approve urgent requests between meetings, by written
procedure, when the department head and the Data Protection Office have
already agreed. Such approvals are reported at the next meeting.

The lead of Platform Engineering informed the board that the platform's
release window rules had not changed and that the two-approver rule for
production releases has been applied since February without exceptions.
The representative of Information Security added that the yearly review of
the Secure API Standard will start in October and invited process owners
to send their experience with it.

There being no further business, the chair closed the meeting at 15:40.
The next meeting will take place on Wednesday 30 September 2026 at 14:00.
Requests for that meeting must reach the secretary by 23 September.

Actions from this meeting: Platform Engineering installs the second RPA
robot for the screening system before the November month-end run; the Data
Protection Office reports on registered language model use cases every
quarter, starting in December; the process owner of Customer Care reports
on the first 20 runs of the restarted complaint summarisation; the Process
Excellence Office publishes the corrected section 4 of the Process Analyst
Handbook by 31 October 2026; the secretary informs Compliance Operations
and Retail Operations of the decisions that concern them.
