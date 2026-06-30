"""Aguarda e dispara send_report.py todo dia às 8h."""
import time
import subprocess
from datetime import datetime, timedelta


def segundos_ate_8h():
    now = datetime.now()
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


while True:
    espera = segundos_ate_8h()
    print(f"Próximo relatório em {espera/3600:.1f}h ({datetime.now()})", flush=True)
    time.sleep(espera)
    subprocess.run(["python3", "/app/scripts/send_report.py"])
