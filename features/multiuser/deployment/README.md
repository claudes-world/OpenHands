# OpenHands Multi-User Deployment Guide

This directory contains everything needed to deploy OpenHands with multi-user support using Docker Compose.

## Quick Start

1. **Copy environment configuration:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the configuration:**
   ```bash
   nano .env
   ```

   **IMPORTANT:** Change all the security-related variables:
   - `JWT_SECRET`
   - `SECRET_KEY`
   - `POSTGRES_PASSWORD`
   - `MINIO_ROOT_PASSWORD`
   - `GRAFANA_PASSWORD`

3. **Generate secure secrets:**
   ```bash
   # Generate JWT secret
   python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(32))"

   # Generate app secret
   python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
   ```

4. **Start the services:**
   ```bash
   docker compose up -d
   ```

5. **Check service health:**
   ```bash
   docker compose ps
   docker compose logs openhands
   ```

6. **Access the application:**
   - OpenHands: http://localhost:3000
   - MinIO Console: http://localhost:9001
   - Grafana: http://localhost:3001 (admin/[your-password])
   - Prometheus: http://localhost:9090

## Architecture Overview

The deployment includes:

- **OpenHands Application**: The main multi-user OpenHands service
- **PostgreSQL**: Database for user data, conversations, and metadata
- **Redis**: Caching and rate limiting
- **MinIO**: S3-compatible object storage for workspaces
- **Nginx**: Reverse proxy with rate limiting and SSL termination
- **Prometheus**: Metrics collection (optional)
- **Grafana**: Monitoring dashboards (optional)

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `JWT_SECRET` | Secret for JWT token signing | `your_secure_32_char_secret` |
| `SECRET_KEY` | Application secret key | `your_secure_32_char_secret` |
| `POSTGRES_PASSWORD` | Database password | `secure_db_password` |

### OAuth Configuration

To enable OAuth login, configure these variables:

```bash
# GitHub OAuth
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
```

#### Setting up OAuth:

**GitHub:**
1. Go to GitHub Settings → Developer settings → OAuth Apps
2. Create a new OAuth App
3. Set Authorization callback URL to: `http://your-domain/api/auth/oauth/callback`

**Google:**
1. Go to Google Cloud Console → APIs & Credentials
2. Create OAuth 2.0 Client ID
3. Set Authorized redirect URIs to: `http://your-domain/api/auth/oauth/callback`

### Rate Limiting and Quotas

```bash
# Rate limits
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000

# User quotas
MAX_CONVERSATIONS_PER_USER=10
MAX_STORAGE_MB_PER_USER=1000
```

## Database Setup

The database is automatically initialized with:
- Required tables and indexes
- Default admin user (email: `admin@localhost`, password: `admin123!`)

**Change the default admin password after first login!**

## Storage Configuration

### File Storage (Default)
- Suitable for single-node deployments
- User data stored in Docker volumes
- Easy backup and restore

### S3/MinIO Storage (Recommended for Production)
- Scalable object storage
- Built-in redundancy
- Suitable for multi-node deployments

Configure S3 storage:
```bash
STORAGE_BACKEND=s3
S3_ENDPOINT=http://minio:9000
S3_BUCKET=openhands-workspaces
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
```

## Security Considerations

### Production Checklist

- [ ] Change all default passwords and secrets
- [ ] Enable HTTPS with valid SSL certificates
- [ ] Configure firewall rules
- [ ] Set up backup strategy
- [ ] Enable monitoring and alerting
- [ ] Review user quotas and rate limits
- [ ] Configure email notifications
- [ ] Set up log aggregation

### SSL/TLS Setup

1. **Obtain SSL certificates** (Let's Encrypt recommended):
   ```bash
   certbot certonly --standalone -d your-domain.com
   ```

2. **Update nginx configuration:**
   - Uncomment HTTPS server block in `nginx/nginx.conf`
   - Update certificate paths
   - Update domain name

3. **Restart nginx:**
   ```bash
   docker compose restart nginx
   ```

## Monitoring

### Metrics Available

- User registration and login rates
- Conversation creation and completion
- Storage usage per user
- API response times
- Error rates
- Resource utilization

### Grafana Dashboards

Access Grafana at http://localhost:3001:
- Default login: `admin` / `[your-password]`
- Pre-configured dashboards for OpenHands metrics
- PostgreSQL and Redis monitoring
- System resource monitoring

### Prometheus Alerts

Configure alerting rules in `prometheus/alerting_rules.yml`:
- High error rates
- Database connection issues
- Storage quota exceeded
- Unusual user activity

## Backup and Recovery

### Database Backup

```bash
# Create backup
docker compose exec postgres pg_dump -U openhands openhands_multiuser > backup.sql

# Restore backup
docker compose exec -i postgres psql -U openhands openhands_multiuser < backup.sql
```

### Volume Backup

```bash
# Backup all volumes
docker run --rm -v openhands_postgres_data:/source -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz -C /source .
docker run --rm -v openhands_workspaces:/source -v $(pwd):/backup alpine tar czf /backup/workspaces_backup.tar.gz -C /source .
```

### Automated Backups

Configure automated backups in `.env`:
```bash
BACKUP_SCHEDULE=0 2 * * *  # Daily at 2 AM
BACKUP_RETENTION_DAYS=30
```

## Scaling

### Horizontal Scaling

For high-traffic deployments:

1. **Load Balancer**: Add multiple OpenHands instances behind a load balancer
2. **Database**: Use PostgreSQL with read replicas
3. **Redis Cluster**: Set up Redis cluster for high availability
4. **Object Storage**: Use external S3-compatible storage

### Resource Requirements

**Minimum (Development):**
- CPU: 2 cores
- RAM: 4 GB
- Storage: 20 GB

**Recommended (Production):**
- CPU: 4+ cores
- RAM: 8+ GB
- Storage: 100+ GB SSD

## Troubleshooting

### Common Issues

**Service won't start:**
```bash
# Check logs
docker compose logs [service-name]

# Check service health
docker compose ps
```

**Database connection issues:**
```bash
# Check PostgreSQL logs
docker compose logs postgres

# Test connection
docker compose exec postgres psql -U openhands -d openhands_multiuser -c "SELECT 1;"
```

**Storage issues:**
```bash
# Check disk space
df -h

# Check volume usage
docker system df
```

### Debug Mode

Enable debug mode in `.env`:
```bash
DEBUG=true
LOG_LEVEL=DEBUG
```

### Health Checks

All services include health checks:
```bash
# Check all service health
docker compose ps

# Get detailed health status
docker inspect $(docker compose ps -q) --format='{{.Name}}: {{.State.Health.Status}}'
```

## Maintenance

### Updates

1. **Backup data** before updating
2. **Pull latest images:**
   ```bash
   docker compose pull
   ```
3. **Restart services:**
   ```bash
   docker compose up -d
   ```

### Log Rotation

Configure log rotation for Docker containers:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

### Clean Up

```bash
# Remove unused containers and images
docker system prune -a

# Remove unused volumes (CAUTION: This will delete data!)
docker volume prune
```

## Support

For issues and questions:

1. Check the [troubleshooting section](#troubleshooting)
2. Review service logs: `docker compose logs [service]`
3. Check the main OpenHands documentation
4. Open an issue on the OpenHands repository

## License

This deployment configuration follows the same license as OpenHands.
