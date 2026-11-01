#!/usr/bin/env bash
# 停掉 start.sh 拉起的三个应用进程（依赖容器与数据保留）。
set -uo pipefail
RUN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.biopilot/run"

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
echo "[stop] 完成（MySQL/Milvus/MinIO 容器仍在跑，数据保留；docker compose down 可全停）"
