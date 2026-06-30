#!/usr/bin/env python3
"""Relatório diário de monitoramento — My-Finances."""

import subprocess
import smtplib
import os
import sys
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

BRT = timezone(timedelta(hours=-3))

GMAIL_USER = os.environ.get("GMAIL_USER", "contato.railandeivid@gmail.com")
DEST_EMAIL = os.environ.get("DEST_EMAIL", "contato.railandeivid@gmail.com")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MONITOR_SH = os.path.join(SCRIPT_DIR, "monitor_server.sh")

CONTAINERS_ESPERADOS = ["my-finances-web", "my-finances-db", "my-finances-redis"]


def load_app_password():
    env_pw = os.environ.get("GMAIL_APP_PASSWORD")
    if env_pw:
        return env_pw
    creds = os.path.join(SCRIPT_DIR, ".monitor_credentials")
    if os.path.exists(creds):
        with open(creds) as f:
            for line in f:
                if line.startswith("GMAIL_APP_PASSWORD="):
                    return line.split("=", 1)[1].strip()
    print("Erro: defina GMAIL_APP_PASSWORD no ambiente", file=sys.stderr)
    sys.exit(1)


def parse_output(raw: str) -> dict:
    data = {}
    mode = None
    buf = []
    for line in raw.splitlines():
        if "<<EOF" in line:
            mode = line.split("<<")[0]
            buf = []
        elif line == "EOF":
            data[mode] = "\n".join(buf).strip()
            mode = None
        elif mode is not None:
            buf.append(line)
        elif "=" in line:
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return data


def color_pct(pct_str: str) -> str:
    try:
        pct = int(str(pct_str).replace("%", ""))
    except (ValueError, AttributeError):
        return "#666"
    return "#e74c3c" if pct >= 85 else "#f39c12" if pct >= 70 else "#27ae60"


def bar(pct_str: str, color: str) -> str:
    try:
        pct = int(str(pct_str).replace("%", ""))
    except (ValueError, AttributeError):
        pct = 0
    return (f'<div style="background:#e0e0e0;border-radius:6px;height:12px;margin-top:8px;">'
            f'<div style="background:{color};width:{pct}%;height:12px;border-radius:6px;"></div></div>')


def stat_box(label: str, value: str, color: str = "#333", sub: str = "") -> str:
    sub_html = f'<div style="color:#888;font-size:11px;margin-top:2px;">{sub}</div>' if sub else ""
    return f"""
    <td style="background:#f8f9fa;border-radius:8px;padding:14px 16px;text-align:center;">
      <div style="color:#888;font-size:11px;text-transform:uppercase;letter-spacing:.5px;">{label}</div>
      <div style="font-size:20px;font-weight:700;color:{color};margin-top:4px;">{value}</div>
      {sub_html}
    </td>"""


def container_rows(containers_str: str) -> tuple:
    rows = []
    running = []
    for line in containers_str.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        name   = parts[0] if len(parts) > 0 else "?"
        status = parts[1] if len(parts) > 1 else "?"
        running.append(name)
        ok = "Up" in status
        color = "#27ae60" if ok else "#e74c3c"
        icon  = "✅" if ok else "❌"
        rows.append(f'<tr><td style="padding:7px 12px;font-family:monospace;font-size:13px;">{name}</td>'
                    f'<td style="padding:7px 12px;"><span style="background:{color};color:#fff;padding:2px 8px;'
                    f'border-radius:4px;font-size:12px;">{icon} {status}</span></td></tr>')
    for exp in CONTAINERS_ESPERADOS:
        if exp not in running:
            rows.append(f'<tr><td style="padding:7px 12px;font-family:monospace;font-size:13px;">{exp}</td>'
                        f'<td style="padding:7px 12px;"><span style="background:#e74c3c;color:#fff;padding:2px 8px;'
                        f'border-radius:4px;font-size:12px;">❌ NÃO ENCONTRADO</span></td></tr>')
    return "\n".join(rows), running


def docker_stats_rows(stats_str: str) -> str:
    rows = []
    for line in stats_str.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        name, cpu, mem_usage, mem_pct = parts[0], parts[1], parts[2], parts[3]
        try:
            pct_val = int(mem_pct.replace("%", "").strip())
            mem_color = "#e74c3c" if pct_val >= 80 else "#f39c12" if pct_val >= 60 else "#27ae60"
        except (ValueError, AttributeError):
            mem_color = "#666"
        rows.append(f'<tr><td style="padding:7px 12px;font-family:monospace;font-size:12px;">{name}</td>'
                    f'<td style="padding:7px 12px;font-size:12px;">{cpu}</td>'
                    f'<td style="padding:7px 12px;font-size:12px;">{mem_usage}</td>'
                    f'<td style="padding:7px 12px;font-size:12px;color:{mem_color};font-weight:600;">{mem_pct}</td></tr>')
    return "\n".join(rows)


def top_ips_rows(ips_str: str) -> str:
    rows = []
    for line in ips_str.splitlines():
        if not line.strip() or "|" not in line:
            continue
        ip, count = line.split("|", 1)
        rows.append(f'<tr><td style="padding:6px 12px;font-family:monospace;font-size:12px;">{ip}</td>'
                    f'<td style="padding:6px 12px;font-size:12px;">{count} req</td></tr>')
    return "\n".join(rows) if rows else '<tr><td colspan="2" style="padding:6px 12px;color:#888;font-size:12px;">sem dados</td></tr>'


def alertas_html(d: dict, running: list) -> str:
    msgs = []
    def pct_int(key):
        try: return int(str(d.get(key, "0")).replace("%", ""))
        except: return 0

    if pct_int("USED_MEM_PCT") >= 85:
        msgs.append(f"⚠️ Memória em uso: {d.get('USED_MEM_PCT')} — acima do limite de 85%")
    if pct_int("DISK_PCT") >= 80:
        msgs.append(f"⚠️ Disco em uso: {d.get('DISK_PCT')} — acima do limite de 80%")
    if pct_int("SWAP_PCT") >= 80:
        msgs.append(f"⚠️ Swap em uso: {d.get('SWAP_PCT')}")
    for exp in CONTAINERS_ESPERADOS:
        if exp not in running:
            msgs.append(f"🚨 Container <b>{exp}</b> não está rodando!")
    try:
        if int(d.get("NGINX_500", 0)) >= 10:
            msgs.append(f"🔥 {d.get('NGINX_500')} erros 500 nas últimas 24h")
    except: pass
    try:
        if int(d.get("NGINX_401", 0)) >= 20:
            msgs.append(f"🛡️ {d.get('NGINX_401')} tentativas de acesso negado (401/403) nas últimas 24h")
    except: pass

    if not msgs:
        return "<p style='color:#27ae60;font-weight:700;margin:0;'>✅ Nenhum alerta — sistema saudável.</p>"
    items = "".join(f"<li style='margin:5px 0;color:#c0392b;'>{m}</li>" for m in msgs)
    return f"<ul style='margin:0;padding-left:20px;'>{items}</ul>"


def section(title: str, content: str) -> str:
    return f"""
  <tr><td style="padding:16px 32px 0;">
    <div style="background:#f8f9fa;border-radius:8px;padding:18px 20px;">
      <h3 style="margin:0 0 14px;color:#333;font-size:13px;text-transform:uppercase;letter-spacing:.6px;">{title}</h3>
      {content}
    </div>
  </td></tr>"""


def build_oci_section() -> str:
    try:
        oci_py = os.path.join(SCRIPT_DIR, "oci_check.py")
        result = subprocess.run(["python3", oci_py], capture_output=True, text=True, timeout=30)
        oci = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
    except Exception:
        oci = {"erro": "Falha ao consultar OCI"}

    if "erro" in oci:
        content = f'<p style="color:#e74c3c;font-size:13px;">⚠️ {oci["erro"]}</p>'
        return section("☁️ Oracle Cloud (Free Tier)", content)

    # Custo
    custo = oci.get("custo_mes_usd", "N/A")
    no_free = oci.get("no_free_tier", True)
    if custo == "N/A":
        custo_color, custo_label = "#666", "N/A"
    elif custo == 0.0:
        custo_color, custo_label = "#27ae60", "US$ 0,00"
    elif custo < 1:
        custo_color, custo_label = "#f39c12", f"US$ {custo:.4f}"
    else:
        custo_color, custo_label = "#e74c3c", f"US$ {custo:.2f}"

    free_badge = ('<span style="background:#27ae60;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">✅ FREE TIER</span>'
                  if no_free else
                  '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">⚠️ GERANDO CUSTO</span>')

    # Storage
    st_gb   = oci.get("storage_usado_gb", "N/A")
    st_pct  = oci.get("storage_pct", 0)
    st_ok   = oci.get("storage_ok", True)
    st_color = "#27ae60" if st_ok else "#e74c3c"

    # Banda
    bw_tb   = oci.get("banda_saida_tb", "N/A")
    bw_pct  = oci.get("banda_pct", 0)
    bw_ok   = oci.get("banda_ok", True)
    bw_color = "#27ae60" if bw_ok else "#e74c3c"

    # Instâncias
    inst_ok    = oci.get("instancias_ok", True)
    inst_total = oci.get("instancias_rodando", "N/A")
    inst_color = "#27ae60" if inst_ok else "#e74c3c"

    content = f"""
      <div style="margin-bottom:14px;">{free_badge}
        <span style="font-size:20px;font-weight:700;color:{custo_color};margin-left:12px;">{custo_label}</span>
        <span style="color:#888;font-size:12px;margin-left:6px;">gasto no mês</span>
      </div>
      <table width="100%" style="border-spacing:8px;"><tr>
        {stat_box("Instâncias", str(inst_total), inst_color, "rodando")}
        <td width="2%"></td>
        {stat_box("Storage", f"{st_gb}GB&nbsp;/&nbsp;200GB", st_color, f"{st_pct}% usado")}
        <td width="2%"></td>
        {stat_box("Banda saída", f"{bw_tb}TB&nbsp;/&nbsp;10TB", bw_color, f"{bw_pct}% do mês")}
        <td width="2%"></td>
        {stat_box("Região", oci.get("instancias_shapes", ["N/A"])[0] if oci.get("instancias_shapes") else "N/A", "#333")}
      </tr></table>
      {bar(str(st_pct) + "%", st_color)}
      <div style="font-size:11px;color:#888;margin-top:4px;">Storage {st_gb}GB de 200GB</div>
      {bar(str(bw_pct) + "%", bw_color)}
      <div style="font-size:11px;color:#888;margin-top:4px;">Banda {bw_tb}TB de 10TB/mês</div>"""

    return section("☁️ Oracle Cloud (Free Tier)", content)


def build_html(d: dict) -> str:
    date_str = datetime.now(tz=BRT).strftime("%d/%m/%Y %H:%M") + " (Brasília)"
    mc = color_pct(d.get("USED_MEM_PCT", "0%"))
    dc = color_pct(d.get("DISK_PCT", "0%"))
    sc = color_pct(d.get("SWAP_PCT", "0%"))

    cont_rows, running = container_rows(d.get("CONTAINERS_RUNNING", ""))
    stats_rows = docker_stats_rows(d.get("DOCKER_STATS", ""))
    ip_rows    = top_ips_rows(d.get("TOP_IPS", ""))

    # ── Seções ───────────────────────────────────────────────────
    mem_content = f"""
      <table width="100%" style="border-spacing:8px;"><tr>
        {stat_box("Total",      d.get('TOTAL_MEM','N/A'), "#333")}
        <td width="2%"></td>
        {stat_box("Usado",      d.get('USED_MEM','N/A'),  mc)}
        <td width="2%"></td>
        {stat_box("Livre",      d.get('FREE_MEM','N/A'),  "#27ae60")}
        <td width="2%"></td>
        {stat_box("Uso",        d.get('USED_MEM_PCT','N/A'), mc)}
      </tr></table>
      {bar(d.get('USED_MEM_PCT','0%'), mc)}
      <div style="margin-top:10px;font-size:12px;color:#888;">
        Swap: {d.get('SWAP_USED','N/A')} / {d.get('SWAP_TOTAL','N/A')}
        <span style="color:{sc};font-weight:600;"> ({d.get('SWAP_PCT','0%')})</span>
      </div>"""

    disk_content = f"""
      <table width="100%" style="border-spacing:8px;"><tr>
        {stat_box("Total",      d.get('DISK_SIZE','N/A'),  "#333")}
        <td width="2%"></td>
        {stat_box("Usado",      d.get('DISK_USED','N/A'),  dc)}
        <td width="2%"></td>
        {stat_box("Disponível", d.get('DISK_AVAIL','N/A'), "#27ae60")}
        <td width="2%"></td>
        {stat_box("Uso",        d.get('DISK_PCT','N/A'),   dc)}
      </tr></table>
      {bar(d.get('DISK_PCT','0%'), dc)}"""

    system_content = f"""
      <table width="100%" style="border-spacing:8px;"><tr>
        {stat_box("CPU",       d.get('CPU_USED','N/A'),  color_pct(d.get('CPU_USED','0%')))}
        <td width="2%"></td>
        {stat_box("Load 1m",  d.get('LOAD_1','N/A'),    "#333")}
        <td width="2%"></td>
        {stat_box("Load 5m",  d.get('LOAD_5','N/A'),    "#333")}
        <td width="2%"></td>
        {stat_box("Uptime",   d.get('UPTIME','N/A'),    "#333")}
      </tr></table>
      <div style="margin-top:10px;font-size:12px;color:#888;">
        Rede — Recebido: <b>{d.get('NET_RX','N/A')}</b> &nbsp;|&nbsp; Enviado: <b>{d.get('NET_TX','N/A')}</b>
      </div>"""

    docker_content = f"""
      <table width="100%" style="border-collapse:collapse;">
        <tr style="background:#eee;">
          <th style="text-align:left;padding:6px 12px;font-size:11px;color:#666;">CONTAINER</th>
          <th style="text-align:left;padding:6px 12px;font-size:11px;color:#666;">STATUS</th>
        </tr>
        {cont_rows}
      </table>"""

    stats_content = f"""
      <table width="100%" style="border-collapse:collapse;">
        <tr style="background:#eee;">
          <th style="text-align:left;padding:6px 12px;font-size:11px;color:#666;">CONTAINER</th>
          <th style="text-align:left;padding:6px 12px;font-size:11px;color:#666;">CPU</th>
          <th style="text-align:left;padding:6px 12px;font-size:11px;color:#666;">MEM USO</th>
          <th style="text-align:left;padding:6px 12px;font-size:11px;color:#666;">MEM %</th>
        </tr>
        {stats_rows}
      </table>"""

    db_content = f"""
      <table width="100%" style="border-spacing:8px;"><tr>
        {stat_box("Tamanho DB",   d.get('DB_SIZE','N/A'),         "#333")}
        <td width="2%"></td>
        {stat_box("Conexões",     d.get('DB_CONNECTIONS','N/A'),  "#333")}
        <td width="2%"></td>
        {stat_box("Usuários",     d.get('USER_COUNT','N/A'),      "#333")}
        <td width="2%"></td>
        {stat_box("Tabelas",      d.get('DB_TABLES','N/A'),       "#333")}
      </tr></table>"""

    try:
        n500 = int(d.get("NGINX_500", 0))
        n404 = int(d.get("NGINX_404", 0))
        n401 = int(d.get("NGINX_401", 0))
        c500 = "#e74c3c" if n500 >= 10 else "#f39c12" if n500 >= 5 else "#27ae60"
        c401 = "#e74c3c" if n401 >= 20 else "#f39c12" if n401 >= 5 else "#27ae60"
    except:
        n500, n404, n401 = "N/A", "N/A", "N/A"
        c500 = c401 = "#666"

    sec_content = f"""
      <table width="100%" style="border-spacing:8px;"><tr>
        {stat_box("Erros 500",    str(n500), c500, "últ. 24h")}
        <td width="2%"></td>
        {stat_box("Erros 404",    str(n404), "#888",  "últ. 24h")}
        <td width="2%"></td>
        {stat_box("401/403",      str(n401), c401, "últ. 24h")}
        <td width="2%"></td>
        {stat_box("",             "",       "#333")}
      </tr></table>
      <div style="margin-top:14px;">
        <div style="font-size:12px;color:#888;margin-bottom:6px;text-transform:uppercase;letter-spacing:.4px;">Top IPs (requisições)</div>
        <table width="100%" style="border-collapse:collapse;">
          <tr style="background:#eee;">
            <th style="text-align:left;padding:5px 12px;font-size:11px;color:#666;">IP</th>
            <th style="text-align:left;padding:5px 12px;font-size:11px;color:#666;">TOTAL</th>
          </tr>
          {ip_rows}
        </table>
      </div>"""

    # ── Oracle Cloud ─────────────────────────────────────────────
    oci_section = build_oci_section()

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f7fa;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f7fa;padding:24px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0"
  style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">

  <tr><td style="background:linear-gradient(135deg,#1a1a2e,#0f3460);padding:28px 32px;">
    <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">📊 My-Finances Monitor</h1>
    <p style="margin:4px 0 0;color:#a0aec0;font-size:13px;">{date_str} — Relatório Diário</p>
  </td></tr>

  <tr><td style="padding:20px 32px 0;">
    <div style="background:#fff8e1;border-left:4px solid #f39c12;border-radius:6px;padding:14px 18px;">
      <h3 style="margin:0 0 10px;color:#333;font-size:12px;text-transform:uppercase;letter-spacing:.6px;">Alertas</h3>
      {alertas_html(d, running)}
    </div>
  </td></tr>

  {section("🧠 Memória RAM", mem_content)}
  {section("💾 Disco", disk_content)}
  {section("⚡ Sistema", system_content)}
  {section("🐳 Containers — Status", docker_content)}
  {section("📈 Containers — Uso de Recursos", stats_content)}
  {section("🗄️ Banco de Dados (PostgreSQL)", db_content)}
  {section("🛡️ Segurança (últimas 24h)", sec_content)}
  {oci_section}

  <tr><td style="padding:24px 32px;border-top:1px solid #f0f0f0;margin-top:20px;">
    <p style="margin:0;color:#aaa;font-size:12px;text-align:center;">
      My-Finances Monitor · Gerado em {date_str}
    </p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>"""


def send_email(html: str, subject: str, pw: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = DEST_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(GMAIL_USER, pw)
        smtp.sendmail(GMAIL_USER, [DEST_EMAIL], msg.as_string())


def main():
    result = subprocess.run(["sh", MONITOR_SH], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"Erro no monitor_server.sh:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    data    = parse_output(result.stdout)
    now_brt = datetime.now(tz=BRT).strftime("%d/%m/%Y")
    subject = f"📊 Relatório Diário My-Finances — {now_brt}"
    html    = build_html(data)
    pw      = load_app_password()

    send_email(html, subject, pw)
    print(f"✅ Relatório enviado para {DEST_EMAIL}", flush=True)


if __name__ == "__main__":
    main()
