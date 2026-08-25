# National dashboard summary API

`GET /api/v1/dashboard/national-summary` is an authenticated internal analytical projection. A
request without parameters requires a membership grant containing `predictions.read`, national
geography, and an Internal classification ceiling. Passing an authorized `admin_unit_id` returns
the same projection for that region or district and its descendants. Unauthorized scope IDs are
returned as not found. Grants are never combined to manufacture classification access.

`GET /api/v1/dashboard/scopes` lists only the administrative units available through the caller's
Internal `predictions.read` grants. A region grant expands to its descendant districts so both the
selector and aggregation follow the governed hierarchy.

For each separate risk domain, the response uses only the latest signal for each administrative
unit. It reports the highest current level, evaluated-unit count, target periods, contributing
source IDs, observation time, and a configured stale flag. A domain without evidence is returned
with `level: null` and `stale: true`; it is never converted to Normal. Published warning counts are
independently filtered through `alerts.read`, classification, and the selected hierarchy. Scope
name, level, administrative-unit ID, and boundary version are explicit response metadata.

The response is a decision-support summary, not an official IPC classification and not permission
to publish a warning.
