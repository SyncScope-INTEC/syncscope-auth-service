import os

import django
import pytest
from django.conf import settings

# Configure Django settings before importing anything else
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

from apps.authentication.plan_limits import (
    PLAN_LIMITS,
    can_add_integration,
    can_add_user,
    get_max_integrations,
    get_max_users,
    get_plan_limits,
    has_feature,
)


class TestPlanLimits:
    """Test plan limits configuration and functions."""

    def test_plan_limits_structure(self):
        """Test that all required plans are defined."""
        assert "starter" in PLAN_LIMITS
        assert "growth" in PLAN_LIMITS
        assert "enterprise" in PLAN_LIMITS

    def test_starter_plan_limits(self):
        """Test Starter plan limits."""
        starter = PLAN_LIMITS["starter"]
        assert starter["display_name"] == "Starter"
        assert starter["price"] == 19
        assert starter["max_users"] == 5
        assert starter["max_integrations"] == 1
        assert "automatic_time_monitoring" in starter["features"]
        assert "weekly_reports" in starter["features"]
        assert "basic_dashboard" in starter["features"]

    def test_growth_plan_limits(self):
        """Test Growth plan limits."""
        growth = PLAN_LIMITS["growth"]
        assert growth["display_name"] == "Growth"
        assert growth["price"] == 149
        assert growth["max_users"] == 25
        assert growth["max_integrations"] == 3
        assert "automated_code_audit" in growth["features"]
        assert "performance_alerts" in growth["features"]

    def test_enterprise_plan_limits(self):
        """Test Enterprise plan limits (unlimited)."""
        enterprise = PLAN_LIMITS["enterprise"]
        assert enterprise["display_name"] == "Enterprise"
        assert enterprise["price"] == 69
        assert enterprise["max_users"] is None  # Unlimited
        assert enterprise["max_integrations"] is None  # Unlimited
        assert "admin_control_panel" in enterprise["features"]
        assert "premium_support" in enterprise["features"]
        assert "assisted_onboarding" in enterprise["features"]

    def test_get_plan_limits_valid(self):
        """Test getting plan limits for valid plan."""
        starter = get_plan_limits("starter")
        assert starter["display_name"] == "Starter"
        assert starter["max_users"] == 5

    def test_get_plan_limits_invalid(self):
        """Test getting plan limits for invalid plan raises error."""
        with pytest.raises(ValueError, match="Invalid plan"):
            get_plan_limits("invalid_plan")

    def test_get_max_users_starter(self):
        """Test getting max users for Starter plan."""
        assert get_max_users("starter") == 5

    def test_get_max_users_growth(self):
        """Test getting max users for Growth plan."""
        assert get_max_users("growth") == 25

    def test_get_max_users_enterprise(self):
        """Test getting max users for Enterprise plan (unlimited)."""
        assert get_max_users("enterprise") is None

    def test_get_max_integrations_starter(self):
        """Test getting max integrations for Starter plan."""
        assert get_max_integrations("starter") == 1

    def test_get_max_integrations_growth(self):
        """Test getting max integrations for Growth plan."""
        assert get_max_integrations("growth") == 3

    def test_get_max_integrations_enterprise(self):
        """Test getting max integrations for Enterprise plan (unlimited)."""
        assert get_max_integrations("enterprise") is None

    def test_has_feature_starter(self):
        """Test checking features for Starter plan."""
        assert has_feature("starter", "automatic_time_monitoring") is True
        assert has_feature("starter", "weekly_reports") is True
        assert has_feature("starter", "automated_code_audit") is False
        assert has_feature("starter", "admin_control_panel") is False

    def test_has_feature_growth(self):
        """Test checking features for Growth plan."""
        assert has_feature("growth", "automatic_time_monitoring") is True
        assert has_feature("growth", "automated_code_audit") is True
        assert has_feature("growth", "performance_alerts") is True
        assert has_feature("growth", "admin_control_panel") is False

    def test_has_feature_enterprise(self):
        """Test checking features for Enterprise plan."""
        assert has_feature("enterprise", "automatic_time_monitoring") is True
        assert has_feature("enterprise", "automated_code_audit") is True
        assert has_feature("enterprise", "admin_control_panel") is True
        assert has_feature("enterprise", "premium_support") is True

    def test_can_add_user_starter_under_limit(self):
        """Test can add user to Starter plan when under limit."""
        assert can_add_user("starter", 3) is True
        assert can_add_user("starter", 4) is True

    def test_can_add_user_starter_at_limit(self):
        """Test cannot add user to Starter plan when at limit."""
        assert can_add_user("starter", 5) is False
        assert can_add_user("starter", 10) is False

    def test_can_add_user_growth_under_limit(self):
        """Test can add user to Growth plan when under limit."""
        assert can_add_user("growth", 10) is True
        assert can_add_user("growth", 24) is True

    def test_can_add_user_growth_at_limit(self):
        """Test cannot add user to Growth plan when at limit."""
        assert can_add_user("growth", 25) is False
        assert can_add_user("growth", 30) is False

    def test_can_add_user_enterprise_unlimited(self):
        """Test can always add user to Enterprise plan (unlimited)."""
        assert can_add_user("enterprise", 100) is True
        assert can_add_user("enterprise", 1000) is True
        assert can_add_user("enterprise", 10000) is True

    def test_can_add_integration_starter_under_limit(self):
        """Test can add integration to Starter plan when under limit."""
        assert can_add_integration("starter", 0) is True

    def test_can_add_integration_starter_at_limit(self):
        """Test cannot add integration to Starter plan when at limit."""
        assert can_add_integration("starter", 1) is False
        assert can_add_integration("starter", 5) is False

    def test_can_add_integration_growth_under_limit(self):
        """Test can add integration to Growth plan when under limit."""
        assert can_add_integration("growth", 0) is True
        assert can_add_integration("growth", 1) is True
        assert can_add_integration("growth", 2) is True

    def test_can_add_integration_growth_at_limit(self):
        """Test cannot add integration to Growth plan when at limit."""
        assert can_add_integration("growth", 3) is False
        assert can_add_integration("growth", 10) is False

    def test_can_add_integration_enterprise_unlimited(self):
        """Test can always add integration to Enterprise plan (unlimited)."""
        assert can_add_integration("enterprise", 100) is True
        assert can_add_integration("enterprise", 1000) is True
