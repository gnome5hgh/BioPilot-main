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
# 启动日志与 pid 留在仓库内的运行数据根下（gitignored，不进版本库）；
# 可用 BIOPILOT_RUN_DIR 覆盖，stop.sh 用同一规则定位 pid。
RUN_DIR="${BIOPILOT_RUN_DIR:-$ROOT/.biopilot/run}"
mkdir -p "$RUN_DIR"

# .env 是部署引导的唯一入口：Python 侧自己会 load_dotenv，但 SpringBoot 与
# 本脚本不会——不在这里导出的话，BIOPILOT_INTERNAL_TOKEN / 数据源口令只对
# Python 生效，Java 侧读到空值（内部调用全部 403）。
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

# Python 解释器：优先 PATH 里的 biopilot，其次当前 conda 安装根下的 biopilot 环境；
# 都找不到就明确失败，绝不静默继续（否则后面会起一个不存在的服务）。
PY_BIN="${BIOPILOT_PY_BIN:-$(command -v biopilot || true)}"
if [ -z "$PY_BIN" ]; then
  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
  if [ -n "$CONDA_BASE" ] && [ -x "$CONDA_BASE/envs/biopilot/bin/biopilot" ]; then
    PY_BIN="$CONDA_BASE/envs/biopilot/bin/biopilot"
  fi
fi
if [ -z "$PY_BIN" ] || [ ! -x "$PY_BIN" ]; then
  printf '\033[2m[start]\033[0m %s\n' \
    "找不到 biopilot 可执行文件：请先激活 conda 环境 biopilot，或设置 BIOPILOT_PY_BIN"
  exit 1
fi
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
  (cd "$ROOT" && nohup "$PY_BIN" >"$RUN_DIR/webapi.log" 2>&1 & echo $! >"$RUN_DIR/webapi.pid")
  log "适配层启动中（日志 $RUN_DIR/webapi.log）"
fi

# ---- 3. SpringBoot（8080；库模块需先 install 一次）----
if alive "$RUN_DIR/server.pid"; then
  log "服务端已在跑（pid $(cat "$RUN_DIR/server.pid")）"
else
  # bio-admin 从本地 Maven 仓库取 bio-gateway 等模块；改了后端不 install 就会
  # spring-boot:run 到旧 jar（新端点表现为 404）。启动前先安装一次。
  log "安装服务端模块（保证 bio-gateway 等为最新）..."
  if ! (cd "$ROOT/server" && mvn -q install -DskipTests >>"$RUN_DIR/server.log" 2>&1); then
    log "服务端模块安装失败，继续用本地仓库已有版本（看 $RUN_DIR/server.log）"
  fi
  (cd "$ROOT/server/bio-admin" && nohup mvn -q spring-boot:run >>"$RUN_DIR/server.log" 2>&1 & echo $! >"$RUN_DIR/server.pid")
  log "服务端启动中（日志 $RUN_DIR/server.log）"
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
# -f：只把 2xx/3xx 当成功。不带 -f 的话 404/405/500 也会被判「就绪」，
# 服务初始化失败时脚本仍会打印「已启动」。
wait_url() {
  local name="$1" url="$2"
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null -m 2 "$url" && { log "$name 就绪：$url"; return 0; }
    sleep 2
  done
  log "$name 60 秒内未就绪，看对应日志排查"; return 1
}
failures=0
wait_url "适配层"  http://127.0.0.1:8300/health || failures=$((failures + 1))
wait_url "服务端"  http://127.0.0.1:8080/health || failures=$((failures + 1))
wait_url "前端"    http://localhost:5173/ || failures=$((failures + 1))

if [ "$failures" -eq 0 ]; then
  cat <<'EOF'

  ✅ BioPilot 已启动：浏览器打开 http://localhost:5173
     停止：./stop.sh（容器与数据保留）

EOF
else
  cat <<EOF

  ❌ 有 $failures 个服务未在 60 秒内就绪，平台可能不可用
     日志目录：$RUN_DIR（webapi.log / server.log / web.log）

EOF
fi

# 跟随各服务日志（Ctrl-C 退出跟随，服务继续在后台跑）
tail -n 20 -f "$RUN_DIR"/webapi.log "$RUN_DIR"/server.log "$RUN_DIR"/web.log 2>/dev/null
