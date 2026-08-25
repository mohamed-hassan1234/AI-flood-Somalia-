# Partner and administration projections

## Partner Portal

`GET /api/v1/alerts/partner-warnings` requires `alerts.read` and returns only warnings whose
workflow status is `published`, further filtered through a single effective membership's
classification ceiling and geography. Draft, review, verification, and approval records are not
transmitted to the Partner Portal. The portal combines this least-data projection with published
reports returned by `GET /api/v1/reports`; the reports endpoint applies its own `reports.read`,
classification, and geography checks.

## Administration inventory

`GET /api/v1/administration/memberships` requires national `users.manage`. It returns membership
identity links, active state, classification ceiling, and either national or explicit unit scope.
Together with the existing organization, user, and role list endpoints, it powers the national
Administration dashboard. Password hashes and refresh credentials are never in any response.

Create operations remain separate API calls. They retain national capability enforcement,
classification non-escalation, role-capability non-escalation, validated geographic references,
and audit events; rendering inventory in the browser does not grant mutation authority.
