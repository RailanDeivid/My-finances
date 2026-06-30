"""Agenda relatório diário às 8h (Brasília) e alertas a cada 5 minutos."""
import time
import subprocess
import os
from datetime import datetime, timedelta, timezone, date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BRT = timezone(timedelta(hours=-3))
HORA_RELATORIO = 8


def agora_brt() -> datetime:
    return datetime.now(tz=BRT)


def run(script: str, stdin: str = None):
    path = os.path.join(SCRIPT_DIR, script)
    return subprocess.run(
        ["python3", path] if script.endswith(".py") else ["sh", path],
        input=stdin, text=True, capture_output=False
    )


def run_alertas():
    alert_sh = os.path.join(SCRIPT_DIR, "alert_check.sh")
    result = subprocess.run(["sh", alert_sh], capture_output=True, text=True)
    if result.stdout.strip():
        send_py = os.path.join(SCRIPT_DIR, "send_alert.py")
        subprocess.run(["python3", send_py], input=result.stdout, text=True)


def main():
    ultimo_relatorio: date = None

    while True:
        now = agora_brt()

        # Relatório diário às 8h BRT (janela de 5 min para não perder)
        if now.hour == HORA_RELATORIO and now.minute < 5:
            if ultimo_relatorio != now.date():
                print(f"[{now.strftime('%d/%m/%Y %H:%M')} BRT] Enviando relatório diário...", flush=True)
                run("send_report.py")
                ultimo_relatorio = now.date()

        # Checagem de alertas
        run_alertas()

        print(f"[{now.strftime('%d/%m/%Y %H:%M')} BRT] Próxima verificação em 5 min", flush=True)
        time.sleep(300)


if __name__ == "__main__":
    main()
