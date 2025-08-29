# Corporate MVP Backend - Docker Deployment Guide

This guide provides comprehensive instructions for containerizing and deploying the Corporate MVP Django backend using Docker.

## 📋 Prerequisites

- Docker Engine 20.10+ and Docker Compose 2.0+
- PostgreSQL 15+ (included in docker-compose)
- 4GB+ RAM available for containers
- Port 8000 (Django), 5432 (PostgreSQL), 6379 (Redis) available

## 🚀 Quick Start

### Development Environment

1. **Clone and navigate to backend directory:**
   ```bash
   cd /path/to/corporate_mvp/backend
   ```

2. **Start all services:**
   ```bash
   docker-compose up -d
   ```

3. **Run migrations and create dummy data:**
   ```bash
   docker-compose exec web python manage.py migrate
   docker-compose exec web python manage.py create_dummy_data
   ```

4. **Access the application:**
   - API: http://localhost:8000/api/v1/
   - Admin: http://localhost:8000/admin/
   - Health Check: http://localhost:8000/health/

### Production Environment

1. **Build production image:**
   ```bash
   docker-compose -f docker-compose.yml --profile production up -d
   ```

2. **Or use production Dockerfile:**
   ```bash
   docker build -f Dockerfile.prod -t corporate-mvp-backend:prod .
   ```

## 🏗️ Container Architecture

### Services Overview

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **web** | corporate_mvp_web | 8000 | Django application server |
| **db** | corporate_mvp_db | 5432 | PostgreSQL database |
| **redis** | corporate_mvp_redis | 6379 | Cache and session store |
| **nginx** | corporate_mvp_nginx | 80/443 | Reverse proxy (production) |

### Container Features

- **Multi-stage builds** for optimized production images
- **Non-root user** for enhanced security
- **Health checks** for all services
- **Volume persistence** for database and media files
- **Network isolation** with custom bridge network

## 🔧 Configuration

### Environment Variables

Key environment variables for the Django container:

```bash
# Database
DATABASE_URL=postgresql://leapllp112:RandomPassword1999@db:5432/corporate_mvp

# Security
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=0
ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# Cache
REDIS_URL=redis://redis:6379/0
```

### Database Configuration

PostgreSQL is configured with:
- **Database:** corporate_mvp
- **User:** leapllp112
- **Password:** RandomPassword1999 (change in production)
- **Extensions:** uuid-ossp, pg_trgm
- **Persistent volume:** postgres_data

## 📊 Health Monitoring

### Health Check Endpoints

- **Application Health:** `GET /health/` or `GET /api/v1/health/`
- **Database Health:** Included in health check response
- **Container Health:** Built-in Docker health checks

### Health Check Response

```json
{
  "status": "healthy",
  "checks": {
    "database": "healthy",
    "application": "healthy"
  }
}
```

## 🛠️ Management Commands

### Database Operations

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Create dummy data
docker-compose exec web python manage.py create_dummy_data

# Clear dummy data
docker-compose exec web python manage.py clear_data
```

### Container Management

```bash
# View logs
docker-compose logs -f web
docker-compose logs -f db

# Execute shell in container
docker-compose exec web bash
docker-compose exec db psql -U leapllp112 -d corporate_mvp

# Restart services
docker-compose restart web
docker-compose restart db

# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## 🔒 Security Features

### Container Security

- **Non-root user:** Django runs as `django` user (UID/GID 1000)
- **Read-only filesystem:** Application files are read-only
- **Network isolation:** Services communicate via internal network
- **Resource limits:** Memory and CPU limits configured

### Application Security

- **CORS protection:** Configured allowed origins
- **Rate limiting:** Nginx rate limiting for API endpoints
- **Security headers:** X-Frame-Options, CSP, etc.
- **Health checks:** Monitor service availability

## 📈 Production Deployment

### Production Checklist

- [ ] Change default passwords and secret keys
- [ ] Configure SSL certificates for HTTPS
- [ ] Set up proper logging and monitoring
- [ ] Configure backup strategy for database
- [ ] Set resource limits for containers
- [ ] Configure firewall rules
- [ ] Set up log rotation

### SSL Configuration

For HTTPS in production, add SSL certificates to `./ssl/` directory:

```bash
./ssl/
├── cert.pem
└── key.pem
```

Update nginx configuration to enable SSL.

### Environment-Specific Overrides

Create environment-specific compose files:

```bash
# docker-compose.prod.yml
version: '3.8'
services:
  web:
    environment:
      - DEBUG=0
      - SECRET_KEY=${SECRET_KEY}
      - ALLOWED_HOSTS=${ALLOWED_HOSTS}
```

Deploy with:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 🐛 Troubleshooting

### Common Issues

1. **Port conflicts:**
   ```bash
   # Check port usage
   lsof -i :8000
   lsof -i :5432
   ```

2. **Database connection errors:**
   ```bash
   # Check database health
   docker-compose exec db pg_isready -U leapllp112 -d corporate_mvp
   
   # View database logs
   docker-compose logs db
   ```

3. **Permission errors:**
   ```bash
   # Fix file permissions
   sudo chown -R $USER:$USER .
   ```

4. **Memory issues:**
   ```bash
   # Check container resource usage
   docker stats
   ```

### Log Analysis

```bash
# Application logs
docker-compose logs -f web

# Database logs
docker-compose logs -f db

# All services logs
docker-compose logs -f

# Filter logs by time
docker-compose logs --since="2024-01-01T00:00:00" web
```

## 📚 API Testing

### Using Docker for API Testing

```bash
# Test health endpoint
curl http://localhost:8000/health/

# Test API endpoints
curl -H "Content-Type: application/json" \
     -X POST \
     -d '{"username":"manager1","password":"password123"}' \
     http://localhost:8000/api/login/

# Test with authentication
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/api/v1/projects/
```

## 🔄 CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Deploy
on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build Docker image
        run: docker build -f Dockerfile.prod -t corporate-mvp:${{ github.sha }} .
      - name: Run tests
        run: docker run corporate-mvp:${{ github.sha }} python manage.py test
```

## 📞 Support

For deployment issues or questions:

1. Check container logs: `docker-compose logs -f`
2. Verify health endpoints: `curl http://localhost:8000/health/`
3. Review this documentation
4. Check Django and PostgreSQL documentation

---

**Corporate MVP Backend v1.0** - Containerized with Docker for scalable deployment
