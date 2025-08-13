# SyncScope Auth Service

JWT-based authentication and user management service with serverless database retry capabilities.

## Features

- 🔐 JWT Authentication with refresh tokens
- 👥 User management with company associations
- 🔗 GitHub OAuth integration
- 🛡️ Security headers and rate limiting
- 🗄️ PostgreSQL with auth schema
- 🔄 **Database retry logic for serverless environments**
- 📊 Health checks and monitoring
- 🐳 Docker support
- 🧪 Comprehensive testing

## Serverless Database Features

This service is optimized for serverless environments with autoscaling databases:

- **Automatic Retry Logic**: 3 retries with exponential backoff for database operations
- **Connection Management**: Automatic connection cleanup and health checks
- **Resilient Models**: All models include retry decorators for database operations
- **Health Monitoring**: Real-time database health checks with caching

## Quick Start

### 1. Environment Setup

```bash
# Clone and setup
git clone <repo-url>
cd syncscope-auth-service

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials
```

### 2. Database Setup

For Railway PostgreSQL (recommended for serverless):

```bash
# Create auth schema and run migrations
python manage_db.py setup

# Create superuser
python manage_db.py superuser
```

### 3. Run the Service

```bash
# Development
python manage.py runserver

# Production with Docker
docker-compose up

# Health check
python healthcheck.py
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
- `POST /auth/register` - User registration
- `POST /auth/login` - User login  
- `POST /auth/logout` - User logout
- `POST /auth/refresh-token` - Refresh JWT token
- `POST /auth/verify-token` - Verify token (for other services)

### Profile Management
- `GET /auth/profile` - Get user profile
- `PUT /auth/profile` - Update user profile
- `POST /auth/change-password` - Change password

### Session Management
- `GET /auth/sessions` - Get active sessions
- `DELETE /auth/sessions` - Terminate sessions

### OAuth
- `GET /auth/github/url` - Get GitHub OAuth URL
- `POST /auth/github/callback` - GitHub OAuth callback

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

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/test_models.py
pytest tests/test_auth_api.py
pytest tests/test_oauth.py

# With coverage
pytest --cov=apps
```

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

## Development

### Adding New Endpoints

1. Create view with `ServerlessViewMixin` for retry logic
2. Add URL pattern
3. Include appropriate rate limiting
4. Add tests

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

## Troubleshooting

### Database Connection Issues

1. Check health: `python healthcheck.py`
2. Verify environment variables
3. Test direct connection: `python manage_db.py schema`
4. Check Railway dashboard for database status

### Common Issues

- **Connection timeouts**: Service automatically retries
- **Schema not found**: Run `python manage_db.py schema`
- **Migration errors**: Ensure auth schema exists first

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request
