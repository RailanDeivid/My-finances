#!/usr/bin/env python3
"""Relatório diário de monitoramento — My-Finances."""

import subprocess
import smtplib
import os
import dotenv
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# ── Configurações ────────────────────────────────────────────────────────────
dotenv.load_dotenv()
GMAIL_USER  = os.getenv("GMAIL_USER")
DEST_EMAIL  = os.getenv("DEST_EMAIL")
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE  = os.path.join(SCRIPT_DIR, ".monitor_credentials")
MONITOR_SH  = os.path.join(SCRIPT_DIR, "monitor_server.sh")

CONTAINERS_ESPERADOS = ["my-finances-web", "my-finances-db", "my-finances-redis"]


def load_app_password():
    # Dentro do container: variável de ambiente tem prioridade
    env_pw = os.environ.get("GMAIL_APP_PASSWORD")
    if env_pw:
        return env_pw
    # Local: lê do arquivo de credenciais
    if not os.path.exists(CREDS_FILE):
        print(f"Erro: defina GMAIL_APP_PASSWORD no ambiente ou em {CREDS_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(CREDS_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith("GMAIL_APP_PASSWORD="):
                return line.split("=", 1)[1].strip()
    print("Erro: GMAIL_APP_PASSWORD não encontrado em .monitor_credentials", file=sys.stderr)
    sys.exit(1)


def parse_monitor_output(raw: str) -> dict:
    data = {}
    mode = None
    buffer = []
    for line in raw.splitlines():
        if "<<EOF" in line:
            key = line.split("<<")[0]
            mode = key
            buffer = []
        elif line == "EOF":
            data[mode] = "\n".join(buffer).strip()
            mode = None
        elif mode:
            buffer.append(line)
        elif "=" in line:
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return data


def color_for_pct(pct_str: str) -> str:
    try:
        pct = int(pct_str.replace("%", ""))
    except ValueError:
        return "#666"
    if pct >= 85:
        return "#e74c3c"
    if pct >= 70:
        return "#f39c12"
    return "#27ae60"


def progress_bar(pct_str: str, color: str) -> str:
    try:
        pct = int(pct_str.replace("%", ""))
    except ValueError:
        pct = 0
    return f"""
    <div style="background:#e0e0e0;border-radius:6px;height:14px;width:100%;margin-top:6px;">
      <div style="background:{color};width:{pct}%;height:14px;border-radius:6px;"></div>
    </div>"""


def container_rows(containers_str: str) -> str:
    rows = []
    running_names = []
    for line in containers_str.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        name   = parts[0] if len(parts) > 0 else "?"
        status = parts[1] if len(parts) > 1 else "?"
        running_names.append(name)
        ok = "Up" in status
        badge_color = "#27ae60" if ok else "#e74c3c"
        icon        = "✅" if ok else "❌"
        rows.append(f"""
        <tr>
          <td style="padding:8px 12px;font-family:monospace;font-size:13px;">{name}</td>
          <td style="padding:8px 12px;">
            <span style="background:{badge_color};color:#fff;padding:3px 8px;border-radius:4px;font-size:12px;">{icon} {status}</span>
          </td>
        </tr>""")
    # Containers esperados mas não encontrados
    for expected in CONTAINERS_ESPERADOS:
        if expected not in running_names:
            rows.append(f"""
        <tr>
          <td style="padding:8px 12px;font-family:monospace;font-size:13px;">{expected}</td>
          <td style="padding:8px 12px;">
            <span style="background:#e74c3c;color:#fff;padding:3px 8px;border-radius:4px;font-size:12px;">❌ NÃO ENCONTRADO</span>
          </td>
        </tr>""")
    return "\n".join(rows)


def alertas(d: dict, running_names: list) -> str:
    msgs = []
    mem_pct = int(d.get("USED_MEM_PCT", "0").replace("%", "") or 0)
    disk_pct_str = d.get("DISK_PCT", "0%").replace("%", "")
    disk_pct = int(disk_pct_str) if disk_pct_str.isdigit() else 0

    if mem_pct >= 85:
        msgs.append(f"⚠️ Memória em uso: {d.get('USED_MEM_PCT')} — acima do limite de 85%!")
    if disk_pct >= 80:
        msgs.append(f"⚠️ Disco em uso: {d.get('DISK_PCT')} — acima do limite de 80%!")
    for expected in CONTAINERS_ESPERADOS:
        if expected not in running_names:
            msgs.append(f"🚨 Container <b>{expected}</b> não está rodando!")

    if not msgs:
        return "<p style='color:#27ae60;font-weight:bold;'>✅ Nenhum alerta — sistema saudável.</p>"
    items = "".join(f"<li style='margin:4px 0;color:#e74c3c;'>{m}</li>" for m in msgs)
    return f"<ul style='margin:0;padding-left:20px;'>{items}</ul>"


def build_html(d: dict) -> str:
    date_str = d.get("DATE", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    mem_color  = color_for_pct(d.get("USED_MEM_PCT", "0%"))
    disk_color = color_for_pct(d.get("DISK_PCT", "0%"))

    containers_raw = d.get("CONTAINERS_RUNNING", "")
    running_names = [l.split("|")[0] for l in containers_raw.splitlines() if l.strip()]

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f7fa;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f7fa;padding:24px 0;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">

  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);padding:28px 32px;">
    <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">📊 My-Finances Monitor</h1>
    <p style="margin:4px 0 0;color:#a0aec0;font-size:13px;">{date_str} — Relatório Diário</p>
  </td></tr>

  <!-- Alertas -->
  <tr><td style="padding:20px 32px 0;">
    <div style="background:#fff8e1;border-left:4px solid #f39c12;border-radius:6px;padding:14px 18px;">
      <h3 style="margin:0 0 8px;color:#333;font-size:14px;text-transform:uppercase;letter-spacing:.5px;">Alertas</h3>
      {alertas(d, running_names)}
    </div>
  </td></tr>

  <!-- Memória -->
  <tr><td style="padding:20px 32px 0;">
    <div style="background:#f8f9fa;border-radius:8px;padding:18px 20px;">
      <h3 style="margin:0 0 12px;color:#333;font-size:14px;text-transform:uppercase;letter-spacing:.5px;">🧠 Memória RAM</h3>
      <table width="100%"><tr>
        <td style="color:#555;font-size:13px;">Total</td>
        <td style="color:#555;font-size:13px;">Usado</td>
        <td style="color:#555;font-size:13px;">Livre</td>
        <td style="color:#555;font-size:13px;">Uso</td>
      </tr><tr>
        <td style="font-size:16px;font-weight:700;color:#333;">{d.get('TOTAL_MEM','N/A')}</td>
        <td style="font-size:16px;font-weight:700;color:{mem_color};">{d.get('USED_MEM','N/A')}</td>
        <td style="font-size:16px;font-weight:700;color:#27ae60;">{d.get('FREE_MEM','N/A')}</td>
        <td style="font-size:16px;font-weight:700;color:{mem_color};">{d.get('USED_MEM_PCT','N/A')}</td>
      </tr></table>
      {progress_bar(d.get('USED_MEM_PCT','0%'), mem_color)}
    </div>
  </td></tr>

  <!-- Disco -->
  <tr><td style="padding:16px 32px 0;">
    <div style="background:#f8f9fa;border-radius:8px;padding:18px 20px;">
      <h3 style="margin:0 0 12px;color:#333;font-size:14px;text-transform:uppercase;letter-spacing:.5px;">💾 Disco (/ raiz)</h3>
      <table width="100%"><tr>
        <td style="color:#555;font-size:13px;">Total</td>
        <td style="color:#555;font-size:13px;">Usado</td>
        <td style="color:#555;font-size:13px;">Disponível</td>
        <td style="color:#555;font-size:13px;">Uso</td>
      </tr><tr>
        <td style="font-size:16px;font-weight:700;color:#333;">{d.get('DISK_SIZE','N/A')}</td>
        <td style="font-size:16px;font-weight:700;color:{disk_color};">{d.get('DISK_USED','N/A')}</td>
        <td style="font-size:16px;font-weight:700;color:#27ae60;">{d.get('DISK_AVAIL','N/A')}</td>
        <td style="font-size:16px;font-weight:700;color:{disk_color};">{d.get('DISK_PCT','N/A')}</td>
      </tr></table>
      {progress_bar(d.get('DISK_PCT','0%'), disk_color)}
    </div>
  </td></tr>

  <!-- CPU + Uptime -->
  <tr><td style="padding:16px 32px 0;">
    <table width="100%"><tr>
      <td width="48%" style="background:#f8f9fa;border-radius:8px;padding:18px 20px;vertical-align:top;">
        <h3 style="margin:0 0 8px;color:#333;font-size:14px;text-transform:uppercase;letter-spacing:.5px;">⚡ CPU</h3>
        <p style="margin:0;font-size:28px;font-weight:700;color:#333;">{d.get('CPU_USED','N/A')}</p>
        <p style="margin:4px 0 0;color:#888;font-size:12px;">em uso</p>
      </td>
      <td width="4%"></td>
      <td width="48%" style="background:#f8f9fa;border-radius:8px;padding:18px 20px;vertical-align:top;">
        <h3 style="margin:0 0 8px;color:#333;font-size:14px;text-transform:uppercase;letter-spacing:.5px;">⏱ Uptime</h3>
        <p style="margin:0;font-size:18px;font-weight:700;color:#333;">{d.get('UPTIME','N/A')}</p>
        <p style="margin:4px 0 0;color:#888;font-size:12px;">desde o último boot</p>
      </td>
    </tr></table>
  </td></tr>

  <!-- Containers -->
  <tr><td style="padding:16px 32px 0;">
    <div style="background:#f8f9fa;border-radius:8px;padding:18px 20px;">
      <h3 style="margin:0 0 12px;color:#333;font-size:14px;text-transform:uppercase;letter-spacing:.5px;">🐳 Containers Docker</h3>
      <table width="100%" style="border-collapse:collapse;">
        <tr style="border-bottom:1px solid #e0e0e0;">
          <th style="text-align:left;padding:6px 12px;color:#888;font-size:12px;font-weight:600;">NOME</th>
          <th style="text-align:left;padding:6px 12px;color:#888;font-size:12px;font-weight:600;">STATUS</th>
        </tr>
        {container_rows(containers_raw)}
      </table>
    </div>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:24px 32px;border-top:1px solid #f0f0f0;margin-top:20px;">
    <p style="margin:0;color:#aaa;font-size:12px;text-align:center;">
      My-Finances Monitor · Gerado automaticamente às {date_str}
    </p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>"""


def send_email(html_body: str, subject: str, app_password: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = DEST_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(GMAIL_USER, app_password)
        smtp.sendmail(GMAIL_USER, [DEST_EMAIL], msg.as_string())


def main():
    result = subprocess.run(
        ["sh", MONITOR_SH],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        print(f"Erro no monitor.sh:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    data = parse_monitor_output(result.stdout)
    date_str = data.get("DATE", datetime.now().strftime("%d/%m/%Y"))
    subject  = f"📊 Relatório Diário My-Finances — {date_str}"
    html     = build_html(data)
    password = load_app_password()

    send_email(html, subject, password)
    print(f"✅ Relatório enviado para {DEST_EMAIL}")


if __name__ == "__main__":
    main()
