#!/usr/bin/env python
"""
Health check script for serverless deployments
Can be used as a standalone script or imported
"""
import os
import sys
from datetime import datetime

import django
import requests

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings

from config.database_retry import DatabaseHealthCheck


def check_database():
    """Check database connectivity with retries"""
    try:
        return DatabaseHealthCheck.is_healthy(use_cache=False)
    except Exception as e:
        print(f"Database check failed: {e}")
        return False


def check_redis():
    """Check Redis connectivity if configured"""
    try:
        from django.core.cache import cache

        cache.set("health_check", "test", 10)
        result = cache.get("health_check")
        return result == "test"
    except Exception as e:
        print(f"Redis check failed: {e}")
        return False


def check_external_services():
    """Check external service dependencies"""
    checks = []

    # Check GitHub OAuth if configured
    if settings.GITHUB_CLIENT_ID:
        try:
            response = requests.get("https://api.github.com", timeout=5)
            checks.append(("GitHub API", response.status_code == 200))
        except Exception:
            checks.append(("GitHub API", False))

    return checks


def run_health_check():
    """Run complete health check"""
    results = {}

    print(f"🏥 Health Check - {datetime.now().isoformat()}")
    print("=" * 50)

    # Database check
    print("🗄️  Checking database...")
    db_healthy = check_database()
    results["database"] = db_healthy
    print(f"   {'✅' if db_healthy else '❌'} Database: {'Healthy' if db_healthy else 'Unhealthy'}")

    # Redis check
    print("🔴 Checking Redis...")
    redis_healthy = check_redis()
    results["redis"] = redis_healthy
    print(f"   {'✅' if redis_healthy else '❌'} Redis: {'Healthy' if redis_healthy else 'Unhealthy'}")

    # External services
    print("🌐 Checking external services...")
    external_checks = check_external_services()
    for service, healthy in external_checks:
        results[service.lower().replace(" ", "_")] = healthy
        print(f"   {'✅' if healthy else '❌'} {service}: {'Healthy' if healthy else 'Unhealthy'}")

    # Overall status
    all_healthy = all(results.values())
    print("=" * 50)
    print(f"🎯 Overall Status: {'✅ HEALTHY' if all_healthy else '❌ UNHEALTHY'}")

    return all_healthy, results


def main():
    """Main entry point for standalone usage"""
    try:
        healthy, results = run_health_check()

        # Exit with appropriate code
        sys.exit(0 if healthy else 1)

    except Exception as e:
        print(f"❌ Health check failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
