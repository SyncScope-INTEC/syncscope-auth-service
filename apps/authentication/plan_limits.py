"""
Plan limits and features configuration.
Based on the pricing structure from the frontend.
"""

PLAN_LIMITS = {
    "starter": {
        "display_name": "Starter",
        "price": 19,
        "max_users": 5,
        "max_integrations": 1,
        "features": [
            "automatic_time_monitoring",
            "weekly_reports",
            "basic_dashboard",
        ],
        "description": "Ideal para equipos pequeños o en fase de validación",
    },
    "growth": {
        "display_name": "Growth",
        "price": 149,
        "max_users": 25,
        "max_integrations": 3,
        "features": [
            "automatic_time_monitoring",
            "weekly_reports",
            "basic_dashboard",
            "automated_code_audit",
            "performance_alerts",
        ],
        "description": "Pensado para equipos en expansión y gestión más exigente",
    },
    "enterprise": {
        "display_name": "Enterprise",
        "price": 69,
        "max_users": None,  # Unlimited
        "max_integrations": None,  # Unlimited
        "features": [
            "automatic_time_monitoring",
            "weekly_reports",
            "basic_dashboard",
            "automated_code_audit",
            "performance_alerts",
            "complete_integrations",
            "admin_control_panel",
            "premium_support",
            "assisted_onboarding",
        ],
        "description": "Para organizaciones que necesitan control total y escalabilidad",
    },
}


def get_plan_limits(plan_name):
    """
    Get the limits and features for a specific plan.

    Args:
        plan_name (str): The plan name (starter, growth, enterprise)

    Returns:
        dict: Plan configuration with limits and features

    Raises:
        ValueError: If plan_name is invalid
    """
    if plan_name not in PLAN_LIMITS:
        raise ValueError(f"Invalid plan: {plan_name}. Must be one of {list(PLAN_LIMITS.keys())}")

    return PLAN_LIMITS[plan_name]


def get_max_users(plan_name):
    """
    Get the maximum number of users allowed for a plan.

    Args:
        plan_name (str): The plan name

    Returns:
        int or None: Maximum users (None means unlimited)
    """
    return get_plan_limits(plan_name)["max_users"]


def get_max_integrations(plan_name):
    """
    Get the maximum number of integrations allowed for a plan.

    Args:
        plan_name (str): The plan name

    Returns:
        int or None: Maximum integrations (None means unlimited)
    """
    return get_plan_limits(plan_name)["max_integrations"]


def has_feature(plan_name, feature_name):
    """
    Check if a plan has a specific feature.

    Args:
        plan_name (str): The plan name
        feature_name (str): The feature to check

    Returns:
        bool: True if the plan has the feature
    """
    return feature_name in get_plan_limits(plan_name)["features"]


def can_add_user(plan_name, current_user_count):
    """
    Check if a user can be added to a company based on plan limits.

    Args:
        plan_name (str): The plan name
        current_user_count (int): Current number of users in the company

    Returns:
        bool: True if user can be added
    """
    max_users = get_max_users(plan_name)

    # None means unlimited
    if max_users is None:
        return True

    return current_user_count < max_users


def can_add_integration(plan_name, current_integration_count):
    """
    Check if an integration can be added based on plan limits.

    Args:
        plan_name (str): The plan name
        current_integration_count (int): Current number of integrations

    Returns:
        bool: True if integration can be added
    """
    max_integrations = get_max_integrations(plan_name)

    # None means unlimited
    if max_integrations is None:
        return True

    return current_integration_count < max_integrations
