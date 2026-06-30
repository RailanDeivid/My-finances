#!/usr/bin/env python3
"""Envia email de alerta imediato para condições críticas."""

import smtplib
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

GMAIL_USER = os.environ.get("GMAIL_USER", "contato.railandeivid@gmail.com")
DEST_EMAIL = os.environ.get("DEST_EMAIL", "contato.railandeivid@gmail.com")

TIPOS = {
    "MEMORIA_ALTA":   ("🧠", "#e74c3c", "Memória RAM Alta"),
    "DISCO_CHEIO":    ("💾", "#e74c3c", "Disco Quase Cheio"),
    "CONTAINER_FORA": ("🐳", "#c0392b", "Container Fora do Ar"),
    "ERROS_500":      ("🔥", "#e67e22", "Erros 500 em Sequência"),
    "TUNNEL_FORA":    ("🌐", "#c0392b", "Tunnel Cloudflare Fora"),
    "BRUTE_FORCE":    ("🛡️", "#8e44ad", "Possível Ataque Brute Force"),
}


def build_html(alerts: list) -> tuple:
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    rows = ""
    labels = []

    for alert_type, detail in alerts:
        icon, color, label = TIPOS.get(alert_type, ("⚠️", "#e74c3c", alert_type))
        labels.append(label)
        rows += f"""
        <tr>
          <td style="padding:18px 24px;border-bottom:1px solid #f5f5f5;">
            <table><tr>
              <td style="font-size:32px;padding-right:16px;vertical-align:middle;">{icon}</td>
              <td style="vertical-align:middle;">
                <div style="font-weight:700;color:{color};font-size:15px;">{label}</div>
                <div style="color:#555;font-size:13px;margin-top:4px;">{detail}</div>
              </td>
            </tr></table>
          </td>
        </tr>"""

    suffix = "..." if len(labels) > 2 else ""
    subject = f"🚨 ALERTA My-Finances — {' + '.join(labels[:2])}{suffix}"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f7fa;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f7fa;padding:24px 0;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0"
  style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,.12);">

  <tr><td style="background:linear-gradient(135deg,#c0392b,#e74c3c);padding:24px 32px;">
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;">🚨 Alerta — My-Finances</h1>
    <p style="margin:4px 0 0;color:rgba(255,255,255,.8);font-size:13px;">{date_str}</p>
  </td></tr>

  <tr><td style="padding:8px 0;">
    <table width="100%">{rows}</table>
  </td></tr>

  <tr><td style="padding:16px 32px;border-top:1px solid #f0f0f0;">
    <p style="margin:0;color:#aaa;font-size:12px;text-align:center;">
      My-Finances Monitor · Alerta automático — verifique o servidor
    </p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>"""

    return subject, html


def send_email(subject: str, html: str):
    app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_pw:
        print("GMAIL_APP_PASSWORD não definido", file=sys.stderr)
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = DEST_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(GMAIL_USER, app_pw)
        smtp.sendmail(GMAIL_USER, [DEST_EMAIL], msg.as_string())


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        return

    alerts = []
    for line in raw.splitlines():
        if "|" in line:
            t, _, d = line.partition("|")
            alerts.append((t.strip(), d.strip()))

    if not alerts:
        return

    subject, html = build_html(alerts)
    send_email(subject, html)
    print(f"✅ Alerta enviado: {subject}", flush=True)


if __name__ == "__main__":
    main()
