#!/bin/bash
# DevOps Pilot - Bootstrap Script
set -euo pipefail

CUSTOMER="${customer_name}"
ENVIRONMENT="${environment}"
EBS_DEVICE="${ebs_device_name}"
EBS_MOUNT="${ebs_mount_point}"
APP_PORT="${app_port}"
CUSTOMER_DOMAIN="${customer_domain}"
DB_PASSWORD="${db_password}"

BOOTSTRAP_LOG="/var/log/bootstrap.log"
COMPOSE_DIR="$EBS_MOUNT/app"
PG_DATA_DIR="$EBS_MOUNT/postgres"
BACKEND_DATA_DIR="$EBS_MOUNT/backend-data"

exec > >(tee -a "$BOOTSTRAP_LOG") 2>&1

echo "[bootstrap] Starting deployment for $CUSTOMER / $ENVIRONMENT"
echo "[bootstrap] Domain: $CUSTOMER_DOMAIN"
echo "[bootstrap] EBS device: $EBS_DEVICE mount: $EBS_MOUNT"

if [ -z "$DB_PASSWORD" ]; then
  DB_PASSWORD=$(openssl rand -base64 24)
  echo "[bootstrap] Generated random database password"
fi

retry() {
  local n=0 max=5 delay=10
  until "$@"; do
    n=$((n+1))
    if [ "$n" -ge "$max" ]; then
      echo "[bootstrap] ERROR: Command failed after $max retries: $*"
      return 1
    fi
    echo "[bootstrap] Retrying ($n/$max)..."
    sleep "$delay"
  done
}

echo "[bootstrap] Installing Docker..."
retry yum install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

echo "[bootstrap] Installing Docker Compose v2..."
mkdir -p /usr/local/lib/docker/cli-plugins
COMPOSE_VERSION="v2.32.0"
retry curl -sL \
  "https://github.com/docker/compose/releases/download/$COMPOSE_VERSION/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
ln -sf /usr/local/lib/docker/cli-plugins/docker-compose /usr/bin/docker-compose
docker compose version

echo "[bootstrap] Preparing EBS volume $EBS_DEVICE..."
if [ -b "$EBS_DEVICE" ]; then
  if ! blkid "$EBS_DEVICE" > /dev/null 2>&1; then
    echo "[bootstrap] Formatting $EBS_DEVICE as xfs..."
    mkfs -t xfs "$EBS_DEVICE"
  else
    echo "[bootstrap] $EBS_DEVICE already formatted"
  fi

  mkdir -p "$EBS_MOUNT"
  if ! mountpoint -q "$EBS_MOUNT"; then
    mount "$EBS_DEVICE" "$EBS_MOUNT"
    echo "[bootstrap] Mounted $EBS_DEVICE at $EBS_MOUNT"
  else
    echo "[bootstrap] $EBS_MOUNT already mounted"
  fi

  if ! grep -q "$EBS_DEVICE" /etc/fstab; then
    echo "$EBS_DEVICE $EBS_MOUNT xfs defaults,nofail 0 2" >> /etc/fstab
    echo "[bootstrap] Added $EBS_DEVICE to /etc/fstab"
  fi
else
  echo "[bootstrap] WARNING: $EBS_DEVICE not found. EBS may not be attached yet."
fi

mkdir -p "$COMPOSE_DIR" "$PG_DATA_DIR" "$BACKEND_DATA_DIR"

echo "[bootstrap] Writing docker-compose.yml..."
cat > "$COMPOSE_DIR/docker-compose.yml" << COMPOSE_EOF
services:
  postgres:
    image: postgres:16-alpine
    container_name: ${customer_name}-${environment}-postgres
    restart: always
    environment:
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: $DB_PASSWORD
      POSTGRES_DB: app_db
    volumes:
      - $PG_DATA_DIR:/var/lib/postgresql/data
    networks:
      - app-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_user -d app_db"]
      interval: 10s
      timeout: 5s
      retries: 5
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  backend:
    image: nginx:alpine
    container_name: ${customer_name}-${environment}-backend
    restart: always
    ports:
      - "${app_port}:80"
    volumes:
      - $BACKEND_DATA_DIR:/usr/share/nginx/html
      - $COMPOSE_DIR/backend.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - app-net
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  frontend:
    image: nginx:alpine
    container_name: ${customer_name}-${environment}-frontend
    restart: always
    ports:
      - "80:80"
    volumes:
      - $COMPOSE_DIR/frontend.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - backend
    networks:
      - app-net
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  app-net:
    driver: bridge
COMPOSE_EOF

echo "[bootstrap] Writing nginx configs..."

cat > "$COMPOSE_DIR/backend.conf" << 'NGINX_CONF'
server {
    listen 80;
    server_name backend;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
        add_header X-Backend "${customer_name}-${environment}" always;
    }

    location /health {
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
NGINX_CONF

cat > "$COMPOSE_DIR/frontend.conf" << 'NGINX_CONF'
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /health {
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }

    location /api/ {
        proxy_pass http://backend:${app_port}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX_CONF

echo "[bootstrap] Validating nginx configs..."
if docker run --rm -v "$COMPOSE_DIR/backend.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t > /dev/null 2>&1; then
    echo "[bootstrap] Backend nginx config: VALID"
else
    echo "[bootstrap] ERROR: Backend nginx config is invalid!"
    docker run --rm -v "$COMPOSE_DIR/backend.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t
    exit 1
fi
sed -e 's|proxy_pass http://backend:\([0-9]*\)/|proxy_pass http://127.0.0.1:\1/|' \
    "$COMPOSE_DIR/frontend.conf" > /tmp/frontend-validate.conf
if docker run --rm -v /tmp/frontend-validate.conf:/etc/nginx/conf.d/default.conf:ro nginx:alpine nginx -t > /dev/null 2>&1; then
    echo "[bootstrap] Frontend nginx config: VALID"
    rm -f /tmp/frontend-validate.conf
else
    echo "[bootstrap] ERROR: Frontend nginx config is invalid!"
    docker run --rm -v "$COMPOSE_DIR/frontend.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t
    rm -f /tmp/frontend-validate.conf
    exit 1
fi

echo "{ \"customer\": \"${customer_name}\", \"environment\": \"${environment}\", \"status\": \"healthy\" }" > "$BACKEND_DATA_DIR/index.html"

cat > "$COMPOSE_DIR/index.html" << HTML_EOF
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${customer_name} - ${environment}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, system-ui, sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh;
      background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
      color: #fff;
    }
    .card { background: rgba(255,255,255,0.08); backdrop-filter: blur(12px); padding: 3rem; border-radius: 1rem; text-align: center; }
    h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
    .badge { display: inline-block; padding: 0.25rem 1rem; border-radius: 999px; background: #e94560; margin-bottom: 1.5rem; text-transform: uppercase; font-size: 0.875rem; }
    .info { color: rgba(255,255,255,0.6); }
    a { color: #e94560; }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">${environment}</div>
    <h1>Welcome, ${customer_name}</h1>
    <p>Your application is running.</p>
    <p class="info"><a href="https://${customer_domain}">${customer_domain}</a></p>
  </div>
</body>
</html>
HTML_EOF

echo "[bootstrap] Starting Docker Compose stack..."
cd "$COMPOSE_DIR"
docker compose up -d

echo "[bootstrap] Verifying containers..."
sleep 5
docker compose ps

echo "[bootstrap] Testing frontend (port 80)..."
if curl -sf http://localhost:80/health > /dev/null 2>&1; then
  echo "[bootstrap] Frontend: OK"
else
  echo "[bootstrap] Frontend: FAIL (may still be starting)"
fi

echo "[bootstrap] Testing backend (port ${app_port})..."
if curl -sf http://localhost:${app_port}/health > /dev/null 2>&1; then
  echo "[bootstrap] Backend: OK"
else
  echo "[bootstrap] Backend: FAIL (may still be starting)"
fi

echo "[bootstrap] Bootstrap complete for $CUSTOMER / $ENVIRONMENT"
echo "[bootstrap] URL: https://$CUSTOMER_DOMAIN"
echo "[bootstrap] DB password: $DB_PASSWORD"
