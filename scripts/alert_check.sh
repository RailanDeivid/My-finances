#!/bin/sh
# Verificação de condições críticas — imprime alertas encontrados (com cooldown de 1h)

STATE_FILE="/tmp/alert_state"
NOW=$(date +%s)
COOLDOWN=3600

check_cooldown() {
    key="$1"
    last=$(grep "^${key}=" "$STATE_FILE" 2>/dev/null | cut -d= -f2)
    if [ -n "$last" ]; then
        diff=$(( NOW - last ))
        [ "$diff" -lt "$COOLDOWN" ] && return 1
    fi
    tmp=$(mktemp)
    grep -v "^${key}=" "$STATE_FILE" 2>/dev/null > "$tmp" && mv "$tmp" "$STATE_FILE" || rm -f "$tmp"
    echo "${key}=${NOW}" >> "$STATE_FILE"
    return 0
}

# ── MEMÓRIA ─────────────────────────────────────────────────────
mem_total=$(awk '/MemTotal/     {print $2}' /proc/meminfo)
mem_available=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
mem_used=$(( mem_total - mem_available ))
mem_pct=$(awk "BEGIN {printf \"%d\", $mem_used*100/$mem_total}")
if [ "$mem_pct" -ge 85 ]; then
    check_cooldown "mem_alta" && {
        used_gb=$(awk "BEGIN {printf \"%.1f\", $mem_used/1048576}")
        echo "MEMORIA_ALTA|${mem_pct}% em uso (${used_gb}GB)"
    }
fi

# ── DISCO ────────────────────────────────────────────────────────
disk_pct=$(df /host 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
if [ -n "$disk_pct" ] && [ "$disk_pct" -ge 80 ]; then
    check_cooldown "disco_cheio" && {
        disk_avail=$(df -h /host 2>/dev/null | tail -1 | awk '{print $4}')
        echo "DISCO_CHEIO|${disk_pct}% em uso (${disk_avail} disponível)"
    }
fi

# ── CONTAINERS ESSENCIAIS ────────────────────────────────────────
for container in my-finances-web my-finances-db my-finances-redis; do
    status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null)
    if [ "$status" != "running" ]; then
        check_cooldown "container_${container}" && \
            echo "CONTAINER_FORA|$container está ${status:-ausente}"
    fi
done

# ── TUNNEL CLOUDFLARE ────────────────────────────────────────────
tunnel_status=$(docker inspect --format='{{.State.Status}}' my-finances-tunnel 2>/dev/null)
if [ "$tunnel_status" != "running" ]; then
    check_cooldown "tunnel_fora" && \
        echo "TUNNEL_FORA|Container Cloudflare está ${tunnel_status:-ausente}"
fi

# ── ERROS 500 (últimos 5 min) ────────────────────────────────────
errors_500=$(docker logs --since 5m my-finances-nginx 2>&1 | grep -c '" 5' 2>/dev/null || true)
if [ "${errors_500:-0}" -ge 5 ]; then
    check_cooldown "erros_500" && \
        echo "ERROS_500|${errors_500} erros HTTP 5xx nos últimos 5 minutos"
fi

# ── BRUTE FORCE (401/403 do mesmo IP nos últimos 5 min) ──────────
top_fail=$(docker logs --since 5m my-finances-nginx 2>&1 | \
    grep '" 40[13]' | awk '{print $1}' | sort | uniq -c | sort -rn | head -1)
fail_count=$(echo "$top_fail" | awk '{print $1}')
fail_ip=$(echo "$top_fail" | awk '{print $2}')
if [ "${fail_count:-0}" -ge 10 ] && [ -n "$fail_ip" ]; then
    check_cooldown "brute_${fail_ip}" && \
        echo "BRUTE_FORCE|${fail_count} tentativas do IP ${fail_ip} em 5 minutos"
fi

# ── AGENTE WHATSAPP — ERROS (últimos 5 min) ──────────────────────
wa_logs=$(docker logs --since 5m my-finances-web 2>&1)

wa_webhook_errors=$(echo "$wa_logs" | grep -c "Webhook error phone=" 2>/dev/null || true)
if [ "${wa_webhook_errors:-0}" -ge 3 ]; then
    check_cooldown "wa_webhook_erro" && \
        echo "WA_WEBHOOK_ERRO|${wa_webhook_errors} erros no webhook do agente WhatsApp nos últimos 5 minutos"
fi

wa_llm_errors=$(echo "$wa_logs" | grep -c "LLM error:" 2>/dev/null || true)
if [ "${wa_llm_errors:-0}" -ge 3 ]; then
    check_cooldown "wa_llm_erro" && \
        echo "WA_LLM_ERRO|${wa_llm_errors} erros na chamada da IA (OpenAI) nos últimos 5 minutos"
fi

wa_llm_credito=$(echo "$wa_logs" | grep -Eic "insufficient_quota|exceeded your current quota|invalid_api_key|AuthenticationError|RateLimitError" 2>/dev/null || true)
if [ "${wa_llm_credito:-0}" -ge 1 ]; then
    check_cooldown "wa_llm_credito" && \
        echo "WA_LLM_CREDITO|Possível falta de crédito ou chave inválida da OpenAI detectada nos logs"
fi

wa_send_errors=$(echo "$wa_logs" | grep -c "Evolution API send error" 2>/dev/null || true)
if [ "${wa_send_errors:-0}" -ge 3 ]; then
    check_cooldown "wa_send_erro" && \
        echo "WA_SEND_ERRO|${wa_send_errors} falhas ao enviar mensagem pelo WhatsApp (Evolution API) nos últimos 5 minutos"
fi
