#!/bin/sh
# Monitoramento completo do servidor — My-Finances

DATE=$(date '+%d/%m/%Y %H:%M:%S')

# ── MEMÓRIA ─────────────────────────────────────────────────────
mem_total=$(awk '/MemTotal/     {print $2}' /proc/meminfo)
mem_available=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
mem_used=$(( mem_total - mem_available ))
swap_total=$(awk '/SwapTotal/ {print $2}' /proc/meminfo)
swap_free=$(awk '/SwapFree/   {print $2}' /proc/meminfo)
swap_used=$(( swap_total - swap_free ))

total_gb=$(awk "BEGIN {printf \"%.1f\", $mem_total/1048576}")
used_gb=$(awk  "BEGIN {printf \"%.1f\", $mem_used/1048576}")
free_gb=$(awk  "BEGIN {printf \"%.1f\", $mem_available/1048576}")
used_pct=$(awk "BEGIN {printf \"%d\",   $mem_used*100/$mem_total}")
swap_total_gb=$(awk "BEGIN {printf \"%.1f\", $swap_total/1048576}")
swap_used_gb=$(awk  "BEGIN {printf \"%.1f\", $swap_used/1048576}")
swap_pct=0
[ "$swap_total" -gt 0 ] && swap_pct=$(awk "BEGIN {printf \"%d\", $swap_used*100/$swap_total}")

# ── DISCO ────────────────────────────────────────────────────────
disk_info=$(df -h /host 2>/dev/null | tail -1)
disk_size=$(echo  "$disk_info" | awk '{print $2}')
disk_used=$(echo  "$disk_info" | awk '{print $3}')
disk_avail=$(echo "$disk_info" | awk '{print $4}')
disk_pct=$(echo   "$disk_info" | awk '{print $5}')

# ── LOAD AVERAGE ─────────────────────────────────────────────────
load=$(cat /proc/loadavg)
load_1=$(echo  $load | awk '{print $1}')
load_5=$(echo  $load | awk '{print $2}')
load_15=$(echo $load | awk '{print $3}')

# ── CPU ──────────────────────────────────────────────────────────
cpu_idle=$(awk '/^cpu / {idle=$5; total=$2+$3+$4+$5+$6+$7+$8; printf "%.0f", idle*100/total; exit}' /proc/stat 2>/dev/null || echo "0")
cpu_used=$(awk "BEGIN {printf \"%d\", 100 - $cpu_idle}")

# ── REDE ─────────────────────────────────────────────────────────
net_iface=$(ip route 2>/dev/null | awk '/default/ {print $5; exit}')
if [ -n "$net_iface" ]; then
    net_rx=$(awk -v iface="${net_iface}:" '$1==iface {print $2; exit}' /proc/net/dev 2>/dev/null || echo 0)
    net_tx=$(awk -v iface="${net_iface}:" '$1==iface {print $10; exit}' /proc/net/dev 2>/dev/null || echo 0)
    net_rx_mb=$(awk "BEGIN {printf \"%.1f\", ${net_rx:-0}/1048576}")
    net_tx_mb=$(awk "BEGIN {printf \"%.1f\", ${net_tx:-0}/1048576}")
else
    net_rx_mb="N/A"; net_tx_mb="N/A"
fi

# ── UPTIME ───────────────────────────────────────────────────────
uptime_secs=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)
uptime_days=$(( uptime_secs / 86400 ))
uptime_hrs=$(( (uptime_secs % 86400) / 3600 ))
uptime_info="${uptime_days}d ${uptime_hrs}h"

# ── CONTAINERS ───────────────────────────────────────────────────
containers=$(docker ps --format "{{.Names}}|{{.Status}}|{{.Image}}" 2>/dev/null)
containers_stopped=$(docker ps -a --filter "status=exited" --format "{{.Names}}|{{.Status}}" 2>/dev/null)
docker_stats=$(docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}" 2>/dev/null)

# ── NGINX LOGS (últimas 24h) ─────────────────────────────────────
nginx_logs=$(docker logs --since 24h my-finances-nginx 2>&1)
nginx_500=$(echo "$nginx_logs" | grep -c '" 5' 2>/dev/null || echo 0)
nginx_404=$(echo "$nginx_logs" | grep -c '" 404' 2>/dev/null || echo 0)
nginx_401=$(echo "$nginx_logs" | grep -c '" 401\|" 403' 2>/dev/null || echo 0)
top_ips=$(echo "$nginx_logs" | awk '{print $1}' | grep -E '^[0-9]' | sort | uniq -c | sort -rn | head -5 | awk '{print $2"|"$1}')

# ── BANCO DE DADOS ───────────────────────────────────────────────
if [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_DB" ]; then
    export PGPASSWORD="$POSTGRES_PASSWORD"
    psql_cmd="psql -h db -U $POSTGRES_USER -d $POSTGRES_DB -t -c"
    db_size=$(        $psql_cmd "SELECT pg_size_pretty(pg_database_size('$POSTGRES_DB'));" 2>/dev/null | tr -d ' \n')
    db_connections=$( $psql_cmd "SELECT count(*) FROM pg_stat_activity WHERE state='active';" 2>/dev/null | tr -d ' \n')
    user_count=$(     $psql_cmd "SELECT count(*) FROM auth_user;" 2>/dev/null | tr -d ' \n')
    db_tables=$(      $psql_cmd "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' \n')
else
    db_size="N/A"; db_connections="N/A"; user_count="N/A"; db_tables="N/A"
fi

# ── SAÍDA ────────────────────────────────────────────────────────
echo "DATE=$DATE"
echo "TOTAL_MEM=${total_gb}GB"
echo "USED_MEM=${used_gb}GB"
echo "FREE_MEM=${free_gb}GB"
echo "USED_MEM_PCT=${used_pct}%"
echo "SWAP_TOTAL=${swap_total_gb}GB"
echo "SWAP_USED=${swap_used_gb}GB"
echo "SWAP_PCT=${swap_pct}%"
echo "DISK_SIZE=$disk_size"
echo "DISK_USED=$disk_used"
echo "DISK_AVAIL=$disk_avail"
echo "DISK_PCT=$disk_pct"
echo "CPU_USED=${cpu_used}%"
echo "LOAD_1=$load_1"
echo "LOAD_5=$load_5"
echo "LOAD_15=$load_15"
echo "UPTIME=$uptime_info"
echo "NET_RX=${net_rx_mb}MB"
echo "NET_TX=${net_tx_mb}MB"
echo "NGINX_500=$nginx_500"
echo "NGINX_404=$nginx_404"
echo "NGINX_401=$nginx_401"
echo "DB_SIZE=$db_size"
echo "DB_CONNECTIONS=$db_connections"
echo "USER_COUNT=$user_count"
echo "DB_TABLES=$db_tables"
echo "CONTAINERS_RUNNING<<EOF"
echo "$containers"
echo "EOF"
echo "CONTAINERS_STOPPED<<EOF"
echo "${containers_stopped:-nenhum}"
echo "EOF"
echo "DOCKER_STATS<<EOF"
echo "$docker_stats"
echo "EOF"
echo "TOP_IPS<<EOF"
echo "$top_ips"
echo "EOF"
