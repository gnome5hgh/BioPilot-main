#!/usr/bin/env bash
# BioPilot 本地一键启动：依赖容器 → Python 适配层 → SpringBoot → 前端。
#
# 用法：
#   ./start.sh          # 起全部服务并跟随日志（Ctrl-C 只退出跟随，不停服务）
#   ./stop.sh           # 停掉三个应用进程（容器保留，数据不丢）
#
# 服务与端口：
#   前端      http://localhost:5173
#   服务端    http://127.0.0.1:8080
#   适配层    http://127.0.0.1:8300
#   MySQL     127.0.0.1:3307（root / 空密码 / 库 biopilot；3306 留给本机自装 MySQL）
#
# 常见问题：
#   - SpringBoot 起不来提示缺库模块：先在 server/ 下跑一次 mvn install -DskipTests
#   - 首次跑前端：脚本会自动 npm install
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.biopilot/run"
mkdir -p "$RUN_DIR"

PY_BIN="$(command -v biopilot || echo /opt/miniconda3/envs/biopilot/bin/biopilot)"
# 容器 MySQL 发布到 3307（3306 常被本机自装 MySQL 占用）；适配层 DSN 与
# SpringBoot 的 datasource 都读这个变量，改端口只改一处。
MYSQL_PORT="${BIOPILOT_MYSQL_PORT:-3307}"
export BIOPILOT_MYSQL_PORT="$MYSQL_PORT"
export BIOPILOT_MEMORY_MYSQL_DSN="${BIOPILOT_MEMORY_MYSQL_DSN:-mysql://root@127.0.0.1:${MYSQL_PORT}/biopilot}"

log() { printf '\033[2m[start]\033[0m %s\n' "$*"; }

alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

# ---- 1. 依赖容器（Milvus / MinIO / MySQL）----
if ! docker compose up -d --wait --quiet-pull 2>/dev/null; then
  log "docker compose 未就绪，重试普通拉起..."
  docker compose up -d
fi
log "等待 MySQL 健康..."
for _ in $(seq 1 30); do
  docker exec biopilot-mysql mysqladmin ping -h 127.0.0.1 --silent >/dev/null 2>&1 && break
  sleep 2
done
log "依赖容器就绪"

# ---- 2. Python 适配层（8300）----
if alive "$RUN_DIR/webapi.pid"; then
  log "适配层已在跑（pid $(cat "$RUN_DIR/webapi.pid")）"
else
  (cd "$ROOT" && nohup "$PY_BIN" --web >"$RUN_DIR/webapi.log" 2>&1 & echo $! >"$RUN_DIR/webapi.pid")
  log "适配层启动中（日志 $RUN_DIR/webapi.log）"
fi

# ---- 3. SpringBoot（8080；库模块需先 install 一次）----
if alive "$RUN_DIR/server.pid"; then
  log "服务端已在跑（pid $(cat "$RUN_DIR/server.pid")）"
else
  (cd "$ROOT/server/bio-admin" && nohup mvn -q spring-boot:run >"$RUN_DIR/server.log" 2>&1 & echo $! >"$RUN_DIR/server.pid")
  log "服务端启动中（日志 $RUN_DIR/server.log；库模块缺失时先 cd server && mvn install -DskipTests）"
fi

# ---- 4. 前端 dev server（5173）----
if alive "$RUN_DIR/web.pid"; then
  log "前端已在跑（pid $(cat "$RUN_DIR/web.pid")）"
else
  [ -d "$ROOT/web/node_modules" ] || (cd "$ROOT/web" && npm install --silent)
  (cd "$ROOT/web" && nohup npm run dev >"$RUN_DIR/web.log" 2>&1 & echo $! >"$RUN_DIR/web.pid")
  log "前端启动中（日志 $RUN_DIR/web.log）"
fi

# ---- 5. 就绪探测 ----
wait_url() {
  local name="$1" url="$2"
  for _ in $(seq 1 60); do
    curl -s -o /dev/null -m 2 "$url" && { log "$name 就绪：$url"; return 0; }
    sleep 2
  done
  log "$name 60 秒内未就绪，看对应日志排查"; return 1
}
wait_url "适配层"  http://127.0.0.1:8300/health
wait_url "服务端"  http://127.0.0.1:8080/api/v1/auth/login
wait_url "前端"    http://localhost:5173/

cat <<'EOF'

  ✅ BioPilot 已启动：浏览器打开 http://localhost:5173
     停止：./stop.sh（容器与数据保留）

EOF

# 跟随各服务日志（Ctrl-C 退出跟随，服务继续在后台跑）
tail -n 20 -f "$RUN_DIR"/webapi.log "$RUN_DIR"/server.log "$RUN_DIR"/web.log 2>/dev/null
