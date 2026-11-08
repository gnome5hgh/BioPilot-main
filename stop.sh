#!/usr/bin/env bash
# 停掉 start.sh 拉起的三层：应用进程（前端 / SpringBoot / 适配层）与依赖容器。
# 容器用 stop 而不是 down：容器与网络保留（数据卷本来就不随容器删除），
# 下次 ./start.sh 秒起；要连容器一起删再用 docker compose --profile full down。
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 与 start.sh 同一默认值：pid/日志在仓库内运行数据根下，可用 BIOPILOT_RUN_DIR 覆盖。
RUN_DIR="${BIOPILOT_RUN_DIR:-$ROOT/.biopilot/run}"

# ---- 1. 应用进程（先停应用，再停容器：反序会让应用对着已停的 MySQL 刷重连报错）----
for name in web server webapi; do
  pid_file="$RUN_DIR/$name.pid"
  if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    # mvn 起的是进程树：连子进程（java/node）一起收
    pkill -P "$(cat "$pid_file")" 2>/dev/null
    kill "$(cat "$pid_file")" 2>/dev/null
    rm -f "$pid_file"
    echo "[stop] $name 已停止"
  else
    echo "[stop] $name 未在运行"
  fi
done

# 兜底：按端口清残留（mvn 包装层有时不等子进程退出）
for port in 8300 8080 5173; do
  pids=$(lsof -ti ":$port" -sTCP:LISTEN 2>/dev/null)
  [ -n "$pids" ] && kill $pids 2>/dev/null && echo "[stop] 端口 $port 残留进程已清理"
done

# ---- 2. 依赖容器（Milvus / etcd / MinIO / MySQL / paper-search-mcp）----
# 带 full profile：部署形态（webapi/server/web 容器）在跑时也一并停掉；
# 没起过的服务不会被 stop 动到。
if ! docker info >/dev/null 2>&1; then
  echo "[stop] Docker 守护进程未运行，跳过容器停止"
elif docker compose --profile full stop; then
  echo "[stop] 依赖容器已停止"
else
  echo "[stop] 依赖容器停止失败（看上面的 docker 报错）"
fi

echo "[stop] 完成（数据卷在 .biopilot/infra/ 保留；连容器一起删用 docker compose --profile full down）"
