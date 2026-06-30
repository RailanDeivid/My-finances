#!/usr/bin/env python3
"""Consulta Oracle Cloud para verificar uso e custos do free tier."""

import os
import sys
import json
from datetime import datetime, timedelta, timezone

try:
    import oci
except ImportError:
    print(json.dumps({"erro": "SDK OCI não instalado"}))
    sys.exit(0)


def get_config():
    key_path = os.environ.get("OCI_KEY_PATH", "/app/oci_key.pem")
    if not os.path.exists(key_path):
        return None, "Chave privada não encontrada em " + key_path
    for var in ["OCI_USER", "OCI_FINGERPRINT", "OCI_TENANCY", "OCI_REGION"]:
        if not os.environ.get(var):
            return None, f"Variável {var} não definida"
    return {
        "user":        os.environ["OCI_USER"],
        "fingerprint": os.environ["OCI_FINGERPRINT"],
        "tenancy":     os.environ["OCI_TENANCY"],
        "region":      os.environ["OCI_REGION"],
        "key_file":    key_path,
    }, None


def main():
    config, err = get_config()
    if not config:
        print(json.dumps({"erro": err}))
        return

    tenancy_id = config["tenancy"]
    result = {}

    # ── Custo do mês atual ───────────────────────────────────────
    try:
        usage_client = oci.usage_api.UsageapiClient(config)
        now = datetime.now(tz=timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        req = oci.usage_api.models.RequestSummarizedUsagesDetails(
            tenant_id=tenancy_id,
            time_usage_started=start,
            time_usage_ended=now,
            granularity="DAILY",
        )
        usage = usage_client.request_summarized_usages(req).data
        total_cost = sum(float(i.computed_amount or 0) for i in (usage.items or []))
        result["custo_mes_usd"] = round(total_cost, 4)
        result["no_free_tier"] = total_cost == 0.0
    except Exception as e:
        # Usage API pode não estar disponível em contas free tier — não é crítico
        result["custo_mes_usd"] = 0.0
        result["no_free_tier"] = True
        result["custo_nota"] = "API de custo indisponível — assumindo free tier"

    # ── Instâncias compute ───────────────────────────────────────
    try:
        compute = oci.core.ComputeClient(config)
        instances = oci.pagination.list_call_get_all_results(
            compute.list_instances, compartment_id=tenancy_id
        ).data
        free_shapes = {"VM.Standard.E2.1.Micro", "VM.Standard.A1.Flex"}
        running = [i for i in instances if i.lifecycle_state == "RUNNING"]
        paid   = [i for i in running if i.shape not in free_shapes]

        result["instancias_rodando"] = len(running)
        result["instancias_pagas"]   = len(paid)
        result["instancias_ok"]      = len(paid) == 0
        result["instancias_shapes"]  = [i.shape for i in running]
    except Exception as e:
        result["instancias_erro"] = str(e)[:150]

    # ── Block Storage (volumes + boot volumes) ───────────────────
    try:
        block = oci.core.BlockstorageClient(config)

        volumes = oci.pagination.list_call_get_all_results(
            block.list_volumes, compartment_id=tenancy_id
        ).data
        try:
            boot_volumes = oci.pagination.list_call_get_all_results(
                block.list_boot_volumes, compartment_id=tenancy_id
            ).data
        except Exception:
            boot_volumes = []

        ativo_vols  = [v for v in volumes      if v.lifecycle_state not in ("TERMINATED", "FAULTY")]
        ativo_boots = [v for v in boot_volumes if v.lifecycle_state not in ("TERMINATED", "FAULTY")]
        total_gb = sum(v.size_in_gbs for v in ativo_vols + ativo_boots)

        result["storage_usado_gb"]  = total_gb
        result["storage_limite_gb"] = 200
        result["storage_pct"]       = round(total_gb * 100 / 200, 1)
        result["storage_ok"]        = total_gb <= 200
    except Exception as e:
        result["storage_erro"] = str(e)[:150]

    # ── Transferência de saída (mês atual via Monitoring) ────────
    try:
        monitoring = oci.monitoring.MonitoringClient(config)
        now = datetime.now(tz=timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        query = oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace="oci_vcn",
            query='VnicFromNetworkBytes[1d].sum()',
            start_time=start,
            end_time=now,
            resolution="1d",
        )
        resp = monitoring.summarize_metrics_data(
            compartment_id=tenancy_id,
            summarize_metrics_data_details=query
        ).data

        total_bytes = sum(
            dp.value for item in resp for dp in (item.aggregated_datapoints or [])
        )
        total_tb = round(total_bytes / (1024 ** 4), 4)
        result["banda_saida_tb"]    = total_tb
        result["banda_limite_tb"]   = 10
        result["banda_pct"]         = round(total_tb * 100 / 10, 2)
        result["banda_ok"]          = total_tb < 9
    except Exception as e:
        result["banda_erro"] = str(e)[:150]

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
