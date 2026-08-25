# Dependency audit evidence

Audit date: 2026-08-23.

- `npm audit --audit-level=high`: **0 vulnerabilities**.
- Initial `pip-audit`: found advisories affecting Cryptography 45.0.7, pip 25.1.1, and
  Pytest 8.4.2.
- Remediation applied: Cryptography 50.0.0, pip 26.2.1, and Pytest 9.0.3. Project constraints and
  CI setup now require those fixed lines.
- The immediate post-upgrade advisory query could not run because the execution environment's
  external approval quota was exhausted. CI runs `pip-audit` from a current advisory database and
  remains the authoritative recheck; no clean backend-audit claim is made here until that job runs.

Audit output is time-sensitive. A clean scan does not replace authorization, upload, public-data,
or secrets tests.
