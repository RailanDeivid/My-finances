from datetime import datetime, time, timedelta

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone


_HEALTH_TTL = 300   # 5 min
_LOGIN_FAIL_AMBER_MAX = 5


def _safe_url(name):
    try:
        return reverse(name)
    except Exception:
        return "#"


# ── Health bar ──────────────────────────────────────────────────────────────

def _system_health_bar(window_days=30):
    today = timezone.localdate()
    cache_key = f"myfinances:health_bar:{today.isoformat()}:{window_days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    start = today - timedelta(days=window_days - 1)

    day_buckets = {
        start + timedelta(days=i): {"marks": [], "login_falhas": 0}
        for i in range(window_days)
    }

    # ── Fonte 1: erros reais do sistema (LogErro) ──────────────────────
    try:
        from apps.gastos.models import LogErro

        erro_rows = (
            LogErro.objects
            .filter(timestamp__date__gte=start)
            .values("pk", "tipo", "timestamp", "path", "exception_type", "status_code")
            .order_by("timestamp")
        )
        erros_url = _safe_url("admin:gastos_logerro_changelist")
        for row in erro_rows:
            day = timezone.localtime(row["timestamp"]).date()
            bucket = day_buckets.get(day)
            if bucket is None:
                continue
            tipo = row["tipo"]
            if tipo == "500":
                label = "Erro interno 500"
                level = "falha"
            elif tipo == "webhook":
                label = "Erro Webhook WhatsApp"
                level = "falha"
            elif tipo == "llm":
                label = "Erro LLM"
                level = "retry"
            else:
                label = "Erro do sistema"
                level = "falha"

            bucket["marks"].append({
                "level": level,
                "time": row["timestamp"],
                "label": label,
                "descr": row["exception_type"] or row["path"] or "",
                "status_label": tipo.upper(),
                "url": erros_url,
            })
    except Exception:
        pass

    # ── Fonte 2: falhas de login (axes) ────────────────────────────────
    try:
        from axes.models import AccessFailureLog

        login_rows = (
            AccessFailureLog.objects
            .filter(attempt_time__date__gte=start)
            .annotate(day=TruncDate("attempt_time"))
            .values("day")
            .annotate(total=Count("id"))
        )
        axes_url = _safe_url("admin:axes_accessfailurelog_changelist")
        for row in login_rows:
            bucket = day_buckets.get(row["day"])
            if bucket is None:
                continue
            bucket["login_falhas"] = row["total"]
            level = "falha" if row["total"] > _LOGIN_FAIL_AMBER_MAX else "retry"
            day_dt = datetime.combine(row["day"], time.min)
            if timezone.is_aware(timezone.now()):
                day_dt = timezone.make_aware(day_dt)
            bucket["marks"].append({
                "level": level,
                "time": day_dt,
                "label": "Falhas de login",
                "descr": f"{row['total']} tentativa(s) inválida(s)",
                "status_label": "FALHA DE LOGIN",
                "url": axes_url,
            })
    except Exception:
        pass

    # ── Fonte 3: atividade LLM por dia (sinal de saúde positivo) ──────
    try:
        from apps.whatsapp.models import LLMUsage

        llm_rows = (
            LLMUsage.objects
            .filter(timestamp__date__gte=start)
            .annotate(day=TruncDate("timestamp"))
            .values("day")
            .annotate(total=Count("id"))
        )
        llm_url = _safe_url("admin:whatsapp_llmusage_changelist")
        for row in llm_rows:
            bucket = day_buckets.get(row["day"])
            if bucket is None:
                continue
            day_dt = datetime.combine(row["day"], time.min)
            if timezone.is_aware(timezone.now()):
                day_dt = timezone.make_aware(day_dt)
            bucket["marks"].append({
                "level": "ok",
                "time": day_dt,
                "label": "Chamadas LLM",
                "descr": f"{row['total']} chamada(s) ao agente",
                "status_label": "OK",
                "url": llm_url,
            })
    except Exception:
        pass

    # ── Monta estrutura final ──────────────────────────────────────────
    days_list = []
    healthy = 0
    total_falhas = total_retries = total_login_falhas = 0

    for i in range(window_days):
        d = start + timedelta(days=i)
        bucket = day_buckets[d]
        marks = sorted(bucket["marks"], key=lambda m: m["time"] or d)

        n_falhas  = sum(1 for m in marks if m["level"] == "falha")
        n_retries = sum(1 for m in marks if m["level"] == "retry")
        total_falhas  += n_falhas
        total_retries += n_retries
        total_login_falhas += bucket["login_falhas"]

        if marks:
            if n_falhas > 0:
                day_level = "falha"
            elif n_retries > 0:
                day_level = "retry"
            else:
                day_level = "ok"
                healthy += 1
        else:
            day_level = "idle"
            healthy += 1

        days_list.append({
            "date": d,
            "level": day_level,
            "marks": marks,
            "n_falhas": n_falhas,
            "n_retries": n_retries,
            "n_total": len(marks),
        })

    healthy_pct = round(healthy * 100 / window_days) if window_days else 0

    result = {
        "days": days_list,
        "healthy_pct": healthy_pct,
        "total_falhas": total_falhas,
        "total_retries": total_retries,
        "total_login_falhas": total_login_falhas,
        "window_days": window_days,
    }
    cache.set(cache_key, result, _HEALTH_TTL)
    return result


# ── Callback principal ───────────────────────────────────────────────────────

def dashboard_callback(request, context):
    User = get_user_model()

    from apps.whatsapp.models import LLMUsage, WhatsAppAccess
    from apps.gastos.models import LogErro

    total_users = User.objects.count()
    total_wa    = WhatsAppAccess.objects.filter(ativo=True).count()

    llm_agg   = LLMUsage.objects.aggregate(
        total_cost=Sum("cost_usd"),
        total_calls=Count("id"),
        total_tokens_in=Sum("tokens_input"),
        total_tokens_out=Sum("tokens_output"),
    )
    llm_cost       = llm_agg["total_cost"] or 0
    llm_calls      = llm_agg["total_calls"] or 0
    llm_tokens_in  = llm_agg["total_tokens_in"] or 0
    llm_tokens_out = llm_agg["total_tokens_out"] or 0

    # Estatísticas do mês atual
    hoje = timezone.now()
    llm_mes_agg = LLMUsage.objects.filter(
        timestamp__year=hoje.year, timestamp__month=hoje.month
    ).aggregate(custo_mes=Sum("cost_usd"), calls_mes=Count("id"))
    llm_cost_mes  = llm_mes_agg["custo_mes"] or 0
    llm_calls_mes = llm_mes_agg["calls_mes"] or 0

    from decimal import Decimal
    llm_avg_cost = (llm_cost / llm_calls).quantize(Decimal("0.000001")) if llm_calls else Decimal("0")

    total_erros = LogErro.objects.count()

    context["kpis"] = [
        {
            "label": "Usuários",
            "value": total_users,
            "icon": "person",
            "color": "blue",
            "link": _safe_url("admin:auth_user_changelist"),
        },
        {
            "label": "WhatsApp ativos",
            "value": total_wa,
            "icon": "chat",
            "color": "cyan",
            "link": _safe_url("admin:whatsapp_whatsappaccess_changelist"),
        },
        {
            "label": "Chamadas LLM",
            "value": llm_calls,
            "icon": "smart_toy",
            "color": "purple",
            "link": _safe_url("admin:whatsapp_llmusage_changelist"),
        },
        {
            "label": "Erros registrados",
            "value": total_erros,
            "icon": "bug_report",
            "color": "red",
            "link": _safe_url("admin:gastos_logerro_changelist"),
        },
    ]

    context["llm_cost_usd"]    = llm_cost
    context["llm_cost_mes"]    = llm_cost_mes
    context["llm_calls_total"] = llm_calls
    context["llm_calls_mes"]   = llm_calls_mes
    context["llm_avg_cost"]    = llm_avg_cost
    context["llm_tokens_in"]   = llm_tokens_in
    context["llm_tokens_out"]  = llm_tokens_out
    context["health_bar"]     = _system_health_bar(window_days=30)

    context["llm_por_usuario"] = (
        LLMUsage.objects
        .values("user__username")
        .annotate(
            total_calls=Count("id"),
            total_tokens=Sum("tokens_total"),
            total_cost=Sum("cost_usd"),
        )
        .order_by("-total_cost")[:15]
    )

    context["recent_actions"] = (
        LogEntry.objects
        .select_related("user", "content_type")
        .order_by("-action_time")[:10]
    )

    return context
