# Season configuration governance

Season dates are data, not application constants. Authorized administrators create versioned draft
windows through `POST /api/v1/seasons`; a separately capability-checked approval action publishes
the window. Approval rejects any overlap with another active approved window. Every approved
definition records its authority, version, approving user, and audit events.

Observation and regional-aggregation APIs annotate reference dates with the matching approved
season name, authority, and version. Dates outside configured windows remain explicitly
unclassified. Draft windows never affect evidence responses.

No production Somalia season dates are included by default. Institutions must supply and approve
the authoritative windows for each relevant period. Synthetic tests use clearly labelled dates
solely to prove the workflow and overlap controls.
