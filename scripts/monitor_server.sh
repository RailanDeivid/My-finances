#!/bin/sh
# Monitoramento do servidor — versão Linux (roda dentro do container)

DATE=$(date '+%d/%m/%Y %H:%M:%S')

# ── MEMÓRIA (/proc/meminfo do host, visível pelo kernel) ─────────
mem_total=$(awk '/MemTotal/     {print $2}' /proc/meminfo)
mem_available=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
mem_used=$(( mem_total - mem_available ))

total_gb=$(awk "BEGIN {printf \"%.1f\", $mem_total/1048576}")
used_gb=$(awk  "BEGIN {printf \"%.1f\", $mem_used/1048576}")
free_gb=$(awk  "BEGIN {printf \"%.1f\", $mem_available/1048576}")
used_pct=$(awk "BEGIN {printf \"%d\",   $mem_used*100/$mem_total}")

# ── DISCO (host montado em /host) ────────────────────────────────
disk_info=$(df -h /host 2>/dev/null | tail -1)
disk_size=$(echo  "$disk_info" | awk '{print $2}')
disk_used=$(echo  "$disk_info" | awk '{print $3}')
disk_avail=$(echo "$disk_info" | awk '{print $4}')
disk_pct=$(echo   "$disk_info" | awk '{print $5}')

# ── CONTAINERS DOCKER ────────────────────────────────────────────
containers=$(docker ps --format "{{.Names}}|{{.Status}}|{{.Image}}" 2>/dev/null)

# ── CPU ──────────────────────────────────────────────────────────
cpu_idle=$(awk '/cpu / {idle=$5; total=$2+$3+$4+$5+$6+$7+$8; printf "%.0f", idle*100/total}' /proc/stat 2>/dev/null || echo "0")
cpu_used=$(awk "BEGIN {printf \"%d\", 100 - $cpu_idle}")

# ── UPTIME ───────────────────────────────────────────────────────
uptime_secs=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)
uptime_days=$(( uptime_secs / 86400 ))
uptime_hrs=$(( (uptime_secs % 86400) / 3600 ))
uptime_info="${uptime_days}d ${uptime_hrs}h"

echo "DATE=$DATE"
echo "TOTAL_MEM=${total_gb}GB"
echo "USED_MEM=${used_gb}GB"
echo "FREE_MEM=${free_gb}GB"
echo "USED_MEM_PCT=${used_pct}%"
echo "DISK_SIZE=$disk_size"
echo "DISK_USED=$disk_used"
echo "DISK_AVAIL=$disk_avail"
echo "DISK_PCT=$disk_pct"
echo "CPU_USED=${cpu_used}%"
echo "UPTIME=$uptime_info"
echo "CONTAINERS_RUNNING<<EOF"
echo "$containers"
echo "EOF"
echo "CONTAINERS_STOPPED<<EOF"
nenhum=$(docker ps -a --filter "status=exited" --format "{{.Names}}|{{.Status}}" 2>/dev/null)
echo "${nenhum:-nenhum}"
echo "EOF"
