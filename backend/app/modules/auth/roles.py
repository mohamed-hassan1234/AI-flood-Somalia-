ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "Platform Super Admin": frozenset(
        {
            "users.manage",
            "organizations.manage",
            "data_sources.manage",
            "early_actions.playbooks.manage",
            "early_actions.read",
            "data_sources.read",
            "geography.read",
            "geography.manage",
            "indicators.manage",
            "seasons.manage",
            "seasons.approve",
            "audit.read",
        }
    ),
    "National Analyst": frozenset(
        {
            "geography.read",
            "data_sources.read",
            "indicators.read",
            "predictions.read",
            "predictions.generate",
            "alerts.create",
            "alerts.read",
            "alerts.review",
            "alerts.approve",
            "alerts.publish",
            "alerts.resolve",
            "field_tasks.create",
            "field_tasks.read",
            "field_reports.verify",
            "exposure.calculate",
            "exposure.read",
            "early_actions.approve",
            "early_actions.read",
            "notifications.send",
            "notifications.read",
            "notifications.manage",
            "notifications.escalate",
            "models.infer",
            "models.read",
            "outcomes.manage",
            "scenarios.run",
            "scenarios.read",
            "reports.generate",
            "reports.publish",
            "reports.read",
        }
    ),
    "Regional Analyst": frozenset(
        {
            "geography.read",
            "indicators.read",
            "predictions.read",
            "field_tasks.create",
            "field_tasks.read",
            "field_reports.verify",
            "alerts.read",
            "alerts.review",
            "notifications.read",
        }
    ),
    "District Officer / Field Reporter": frozenset(
        {"geography.read", "field_tasks.read", "field_reports.submit", "early_actions.read", "early_actions.update"}
    ),
    "Early Action / Response Coordinator": frozenset(
        {
            "geography.read",
            "early_actions.create",
            "early_actions.read",
            "early_actions.assign",
            "early_actions.update",
            "early_actions.complete",
            "notifications.send",
            "notifications.read",
            "notifications.escalate",
        }
    ),
    "Decision Maker": frozenset(
        {"geography.read", "predictions.read", "exposure.read", "early_actions.approve", "early_actions.read"}
    ),
    "Data / ML Scientist": frozenset(
        {
            "geography.read",
            "data_sources.read",
            "models.train",
            "models.read",
            "predictions.generate",
            "models.evaluate",
            "models.promote",
            "models.rollback",
            "models.infer",
            "outcomes.manage",
            "scenarios.read",
            "scenarios.run",
        }
    ),
    "Partner / Read-only Viewer": frozenset(
        {"geography.read", "indicators.read", "alerts.read", "reports.read"}
    ),
}

# Super administrators receive the complete declared capability vocabulary. This is still
# constrained by their membership geography and classification ceiling at authorization time.
ROLE_CAPABILITIES["Platform Super Admin"] = frozenset().union(*ROLE_CAPABILITIES.values())
