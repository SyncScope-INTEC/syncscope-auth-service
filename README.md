# SyncScope Auth Service

[![Build Status](https://github.com/AlejandroBeltre/syncscope-auth-service/workflows/CI/badge.svg)](https://github.com/AlejandroBeltre/syncscope-auth-service/actions)
[![Coverage Status](https://coveralls.io/repos/github/AlejandroBeltre/syncscope-auth-service/badge.svg?branch=main)](https://coveralls.io/github/AlejandroBeltre/syncscope-auth-service?branch=main)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Django Version](https://img.shields.io/badge/django-4.2+-green.svg)](https://djangoproject.com)

Central authentication and user management service for the SyncScope developer productivity monitoring platform.

## Overview

The Auth Service is the foundational component of SyncScope, providing JWT-based authentication, user management, and company organization capabilities. It serves as the primary authentication provider for all other SyncScope services and maintains the core user and company data that powers the entire platform.

## Features

- 🔐 JWT Authentication with refresh tokens and session management
- 👥 Multi-tenant user management with company associations
- 🔗 GitHub OAuth integration for developer accounts
- 🛡️ Enterprise-grade security with rate limiting and validation
- 🗄️ PostgreSQL with comprehensive schema (auth, management, analytics, monitoring, alerts)
- 🔄 **Serverless-optimized with database retry logic**
- 📊 Health checks and monitoring endpoints
- 🐳 Docker support for containerized deployment
- 🧪 Comprehensive test suite (31+ model tests, API integration tests)

## Architecture & Service Integration

SyncScope Auth Service is designed to work seamlessly with the following microservices:

### **Core Integration Points**

#### **→ syncscope-api-gateway**
- **Purpose**: Kong API gateway for routing, authentication, and rate limiting
- **Integration**: Auth Service provides JWT token validation endpoints for the gateway
- **Authentication Flow**: Gateway validates all requests using Auth Service token verification API

#### **→ syncscope-management-service** 
- **Purpose**: Manages teams, projects, and integrations configuration
- **Integration**: Shares user and company data; Management Service calls Auth Service for user permissions
- **Data Flow**: Auth Service provides user/company context for team and project management

#### **→ syncscope-monitoring-service**
- **Purpose**: Collects and processes developer activity data in real-time
- **Integration**: Uses Auth Service for user authentication and session tracking
- **Data Flow**: Monitoring Service associates activity data with authenticated users

#### **→ syncscope-analytics-service**
- **Purpose**: Generates insights, KPIs, and performance metrics from collected data
- **Integration**: Queries Auth Service for user context when generating reports
- **Data Flow**: Analytics Service filters and aggregates data based on company/user permissions

#### **→ syncscope-alerts-service**
- **Purpose**: Handles alert rules, notifications, and communication channels
- **Integration**: Uses Auth Service for user preferences and notification targeting
- **Data Flow**: Alerts Service sends notifications based on user/company configurations

#### **→ syncscope-frontend**
- **Purpose**: Next.js web dashboard for monitoring team productivity and code metrics
- **Integration**: Primary consumer of Auth Service APIs for login, registration, and profile management
- **User Flow**: Frontend handles all user authentication flows through Auth Service

### **Database Schema Integration**

The Auth Service maintains the master database with schemas that support all services:

- **`auth` schema**: Users, companies, sessions (owned by Auth Service)
- **`management` schema**: Teams, projects, integrations (used by Management Service)
- **`monitoring` schema**: Activity logs, sessions, code metrics (used by Monitoring Service)
- **`analytics` schema**: Performance metrics, reports (used by Analytics Service)
- **`alerts` schema**: Alert rules, notifications (used by Alerts Service)

## Quick Start

### 1. Environment Setup

```bash
# Clone and setup
git clone <repo-url>
cd syncscope-auth-service

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials and service URLs
```

### 2. Database Setup

```bash
# Create auth schema and run migrations
python manage_db.py setup

# Create superuser for admin access
python manage_db.py superuser

# Verify schema setup
python manage_db.py schema
```

### 3. Run the Service

```bash
# Development
python manage.py runserver 0.0.0.0:8000

# Production with Gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000

# Docker deployment
docker-compose up --build

# Health check
curl http://localhost:8000/health/
```

### 4. Integration with Other Services

Once Auth Service is running, configure other SyncScope services:

```bash
# Set Auth Service URL in other services
export AUTH_SERVICE_URL=http://localhost:8000
export JWT_VERIFICATION_URL=http://localhost:8000/auth/verify-token
```

## Serverless Configuration

### Environment Variables for Serverless

```env
# Database (Railway PostgreSQL URL format)
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Enable serverless optimizations
SERVERLESS_ENV=true

# Shorter connection timeouts
DB_CONNECT_TIMEOUT=10

# Redis for caching (recommended)
REDIS_URL=redis://your-redis-url

# Security
SECRET_KEY=your-secret-key
DEBUG=False

# Service Integration URLs
MANAGEMENT_SERVICE_URL=http://syncscope-management-service:8001
MONITORING_SERVICE_URL=http://syncscope-monitoring-service:8002
ANALYTICS_SERVICE_URL=http://syncscope-analytics-service:8003
ALERTS_SERVICE_URL=http://syncscope-alerts-service:8004
API_GATEWAY_URL=http://syncscope-api-gateway:8080

# OAuth Configuration
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
GITHUB_REDIRECT_URI=http://localhost:3000/auth/github/callback
```

### Database Retry Configuration

The service automatically retries failed database operations:

- **Max Retries**: 3 attempts
- **Backoff**: Exponential (0.5s, 1s, 2s, 5s max)
- **Retryable Errors**: Connection timeouts, interface errors, etc.

All models and views include retry logic:

```python
# Automatic retries on all model operations
user = User.objects.get(email='test@example.com')  # Auto-retries
user.save()  # Auto-retries

# Views include health checks
class MyView(ServerlessViewMixin, APIView):
    # Automatically checks DB health before processing
    pass
```

## API Endpoints

### Authentication
- `POST /auth/register` - User registration with company creation
- `POST /auth/login` - User login with session creation
- `POST /auth/logout` - User logout and session cleanup
- `POST /auth/refresh-token` - Refresh JWT access token
- `POST /auth/verify-token` - **Token verification for service-to-service communication**

### Profile Management
- `GET /auth/profile` - Get user profile with company info
- `PUT /auth/profile` - Update user profile (name, timezone)
- `POST /auth/change-password` - Change password with validation

### Session Management
- `GET /auth/sessions` - Get all active user sessions
- `DELETE /auth/sessions` - Terminate specific or all sessions

### OAuth Integration
- `GET /auth/github/url` - Get GitHub OAuth authorization URL
- `POST /auth/github/callback` - Handle GitHub OAuth callback

### Health & Monitoring
- `GET /health/` - Basic health check
- `GET /health/ready/` - Readiness probe for Kubernetes
- `GET /health/live/` - Liveness probe for Kubernetes

### **Service-to-Service Endpoints**

These endpoints are used by other SyncScope services:

- `POST /auth/verify-token` - **Primary endpoint for API Gateway token validation**
- `GET /auth/user/{user_id}` - Get user details for other services
- `GET /auth/company/{company_id}/users` - Get company users for management service

## Health Checks

The service includes comprehensive health monitoring:

```bash
# Database health check
python manage.py check_db_health

# Full health check
python healthcheck.py

# Cleanup expired sessions
python manage.py cleanup_sessions
```

## Database Schema

Uses PostgreSQL with dedicated `auth` schema:

### Tables
- `auth.companies` - Company information
- `auth.users` - User accounts with roles
- `auth.user_sessions` - Session management

### Relationships
- Users belong to companies
- Domain validation ensures email matches company domain
- Sessions track user authentication state

## Deployment

### Railway Deployment

1. Connect your Railway PostgreSQL database
2. Set `DATABASE_URL` environment variable
3. The auth schema is created automatically
4. Deploy with health checks enabled

### Docker Deployment

```bash
# Build and run
docker-compose up --build

# With production settings
docker-compose -f docker-compose.prod.yml up
```

## Testing

The service includes a comprehensive test suite covering all database models and API endpoints:

```bash
# Run all tests with virtual environment
.venv/Scripts/python -m pytest tests/ -v --ds=config.settings

# Run specific test categories
.venv/Scripts/python -m pytest tests/test_models.py -v --ds=config.settings
.venv/Scripts/python -m pytest tests/test_auth_api.py -v --ds=config.settings
.venv/Scripts/python -m pytest tests/test_oauth.py -v --ds=config.settings

# With coverage reporting
.venv/Scripts/python -m pytest tests/ --cov=apps --cov-report=html --ds=config.settings

# Run quick health tests
.venv/Scripts/python -m pytest tests/test_health.py -v --ds=config.settings
```

### Test Coverage

- **31+ Model Tests**: Complete coverage of Company, User, and UserSession models
- **API Integration Tests**: Authentication, profile management, session handling
- **Security Tests**: Token validation, unauthorized access protection
- **Database Tests**: Field validation, constraints, relationships
- **OAuth Tests**: GitHub integration workflows

## Monitoring

The service provides metrics and monitoring:

- Request/response logging
- Database connection health
- Redis cache performance
- External service availability

## Security Features

- Password validation and hashing
- JWT with rotation and blacklisting
- Rate limiting by IP
- Security headers (HSTS, XSS protection, etc.)
- CORS configuration
- Session management with expiration

## Development & Customization

### Adding New Endpoints

1. Create view with `ServerlessViewMixin` for retry logic
2. Add URL pattern to `apps/authentication/urls.py`
3. Include appropriate rate limiting and authentication
4. Add comprehensive tests following existing patterns
5. Update API documentation

### Database Operations

All database operations should use the retry-enabled managers:

```python
# Models automatically include retry logic
user = User.objects.get(email='test@example.com')

# For custom operations, use decorators
from config.database_retry import database_retry, atomic_with_retry

@database_retry()
def my_database_operation():
    # Your code here
    pass

@atomic_with_retry()
def my_transaction():
    # Your transactional code here
    pass
```

### Service Integration Guidelines

When integrating with other SyncScope services:

1. **Use JWT token verification** for all authenticated requests
2. **Implement proper error handling** for service-to-service calls
3. **Follow the shared database schema** structure
4. **Use health checks** to verify service dependencies
5. **Implement rate limiting** for external API calls

## Troubleshooting

### Database Connection Issues

1. Check health: `python healthcheck.py`
2. Verify environment variables: `python manage_db.py schema`
3. Test database connectivity: `python manage.py check --database default`
4. Review logs for connection retry attempts

### Service Integration Issues

1. **Token verification failures**: Check `JWT_SECRET_KEY` consistency across services
2. **Service discovery**: Verify service URLs in environment variables
3. **Database schema access**: Ensure proper permissions for shared schemas
4. **Rate limiting**: Check if requests are being throttled

### Common Issues

- **Connection timeouts**: Service automatically retries with exponential backoff
- **Schema not found**: Run `python manage_db.py setup` to create all schemas
- **Migration errors**: Ensure database connection and auth schema exist
- **OAuth issues**: Verify GitHub client ID/secret and redirect URI configuration

## Production Deployment

### Environment Configuration

Ensure the following for production deployment:

```bash
# Security
DEBUG=False
SECRET_KEY=<secure-random-key>
ALLOWED_HOSTS=your-domain.com,api-gateway-url

# Database
DATABASE_URL=postgresql://production-db-url
DB_CONNECT_TIMEOUT=10

# Service URLs (adjust for your infrastructure)
MANAGEMENT_SERVICE_URL=https://management.syncscope.internal
MONITORING_SERVICE_URL=https://monitoring.syncscope.internal
# ... other service URLs

# GitHub OAuth (production values)
GITHUB_CLIENT_ID=production-client-id
GITHUB_CLIENT_SECRET=production-client-secret
GITHUB_REDIRECT_URI=https://your-domain.com/auth/github/callback
```

### Monitoring & Observability

- Set up log aggregation for all authentication events
- Monitor database retry patterns and failures
- Track token verification request volumes
- Set up alerts for service health check failures
- Monitor session cleanup job performance
