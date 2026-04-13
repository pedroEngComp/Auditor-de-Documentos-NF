import re
import statistics
from typing import Optional
from parser import parse_date, parse_currency


# Desvio padrão aceito antes de considerar valor fora da faixa
ZSCORE_THRESHOLD = 2.5

# Aprovador é "conhecido" se aparece em pelo menos este número de documentos
MIN_APPROVER_OCCURRENCES = 2

# Fornecedor é "sem histórico" se aparece em menos documentos que este threshold
MIN_SUPPLIER_OCCURRENCES = 2


# ─── Contexto global (calculado uma vez para o dataset todo) ──────────────────

def build_global_context(docs: list[dict]) -> dict:

    nf_count: dict[str, int] = {}
    cnpj_by_supplier: dict[str, dict[str, int]] = {}
    values_by_supplier: dict[str, list[float]] = {}
    approver_count: dict[str, int] = {}
    supplier_count: dict[str, int] = {}

    for doc in docs:
        nf_num = doc.get("numero_documento")
        supplier = (doc.get("fornecedor") or "").strip().lower()
        cnpj = doc.get("cnpj_fornecedor")
        valor = doc.get("valor_bruto_num")
        aprovador = (doc.get("aprovado_por") or "").strip().lower()

        if nf_num:
            nf_count[nf_num] = nf_count.get(nf_num, 0) + 1

        if supplier and cnpj:
            cnpj_by_supplier.setdefault(supplier, {})
            cnpj_by_supplier[supplier][cnpj] = cnpj_by_supplier[supplier].get(cnpj, 0) + 1

        if supplier and valor is not None:
            values_by_supplier.setdefault(supplier, [])
            values_by_supplier[supplier].append(valor)

        # Aprovadores conhecidos derivados do próprio dataset
        if aprovador:
            approver_count[aprovador] = approver_count.get(aprovador, 0) + 1

        # Frequência de fornecedores para detectar quem é raro demais
        if supplier:
            supplier_count[supplier] = supplier_count.get(supplier, 0) + 1

    canonical_cnpj: dict[str, str] = {
        supplier: max(cnpjs, key=lambda c: cnpjs[c])
        for supplier, cnpjs in cnpj_by_supplier.items()
    }

    # Aprovador "conhecido" = aparece em >= MIN_APPROVER_OCCURRENCES documentos
    known_approvers = {
        name for name, count in approver_count.items()
        if count >= MIN_APPROVER_OCCURRENCES
    }

    return {
        "nf_count": nf_count,
        "canonical_cnpj": canonical_cnpj,
        "values_by_supplier": values_by_supplier,
        "supplier_count": supplier_count,
        "known_approvers": known_approvers,
    }


# ─── Detecção por documento ───────────────────────────────────────────────────

def detect_anomalies(doc: dict, ctx: dict) -> list[dict]:

    anomalies = []

    # Arquivo não processável — não faz sentido checar o resto
    if doc.get("parse_status") in ("encoding_error", "empty_or_unrecognized"):
        anomalies.append({
            "rule": "ARQUIVO_NAO_PROCESSAVEL",
            "description": f"Arquivo não pôde ser processado: {doc.get('parse_error')}",
            "field_evidence": "arquivo",
            "confidence": "Médio",
        })
        return anomalies

    # ── Regra 1: NF duplicada ─────────────────────────────────────────────────
    nf_num = doc.get("numero_documento")
    if nf_num and ctx["nf_count"].get(nf_num, 0) > 1:
        anomalies.append({
            "rule": "NF_DUPLICADA",
            "description": f"Número de NF '{nf_num}' aparece mais de uma vez no dataset",
            "field_evidence": "numero_documento",
            "confidence": "Alto",
        })

    # ── Regra 2: CNPJ divergente ──────────────────────────────────────────────
    supplier = (doc.get("fornecedor") or "").strip().lower()
    cnpj = doc.get("cnpj_fornecedor")
    canonical = ctx["canonical_cnpj"].get(supplier)
    if cnpj and canonical and cnpj != canonical:
        anomalies.append({
            "rule": "CNPJ_DIVERGENTE",
            "description": f"CNPJ '{cnpj}' difere do padrão histórico '{canonical}' para '{supplier}'",
            "field_evidence": "cnpj_fornecedor",
            "confidence": "Alto",
        })

    # ── Regra 3: Fornecedor sem histórico ─────────────────────────────────────
    supplier_occurrences = ctx["supplier_count"].get(supplier, 0)
    if supplier and supplier_occurrences < MIN_SUPPLIER_OCCURRENCES:
        anomalies.append({
            "rule": "FORNECEDOR_SEM_HISTORICO",
            "description": f"Fornecedor '{doc.get('fornecedor')}' aparece em apenas {supplier_occurrences} documento(s) — sem histórico consistente",
            "field_evidence": "fornecedor",
            "confidence": "Alto",
        })

    # ── Regra 4: Data de emissão NF posterior ao pagamento ────────────────────
    data_nf = parse_date(doc.get("data_emissao_nf"))
    data_pag = parse_date(doc.get("data_pagamento"))
    if data_nf and data_pag and data_nf > data_pag:
        anomalies.append({
            "rule": "DATA_NF_APOS_PAGAMENTO",
            "description": (
                f"NF emitida em {doc.get('data_emissao_nf')} mas paga em "
                f"{doc.get('data_pagamento')} — pagamento antes da emissão"
            ),
            "field_evidence": "data_emissao_nf, data_pagamento",
            "confidence": "Alto",
        })

    # ── Regra 5: Valor fora da faixa do fornecedor ────────────────────────────
    valor = doc.get("valor_bruto_num")
    supplier_values = ctx["values_by_supplier"].get(supplier, [])
    if valor is not None and len(supplier_values) >= 3:
        mean = statistics.mean(supplier_values)
        stdev = statistics.stdev(supplier_values)
        if stdev > 0:
            zscore = abs((valor - mean) / stdev)
            if zscore > ZSCORE_THRESHOLD:
                anomalies.append({
                    "rule": "VALOR_FORA_DA_FAIXA",
                    "description": (
                        f"Valor R$ {valor:,.2f} é {zscore:.1f}σ fora da média "
                        f"R$ {mean:,.2f} para '{doc.get('fornecedor')}'"
                    ),
                    "field_evidence": "valor_bruto",
                    "confidence": "Médio",
                })

    # ── Regra 6: Aprovador não reconhecido ────────────────────────────────────
    aprovador = (doc.get("aprovado_por") or "").strip().lower()
    known_approvers = ctx.get("known_approvers", set())
    # Só dispara se temos aprovadores conhecidos suficientes para comparar
    if aprovador and known_approvers and aprovador not in known_approvers:
        anomalies.append({
            "rule": "APROVADOR_NAO_RECONHECIDO",
            "description": f"Aprovador '{doc.get('aprovado_por')}' não aparece com frequência suficiente no dataset para ser considerado conhecido",
            "field_evidence": "aprovado_por",
            "confidence": "Médio",
        })

    # ── Regra 7: STATUS inconsistente ────────────────────────────────────────
    status = (doc.get("status") or "").upper()
    if status == "CANCELADO" and doc.get("data_pagamento"):
        anomalies.append({
            "rule": "STATUS_INCONSISTENTE",
            "description": f"STATUS é CANCELADO mas DATA_PAGAMENTO está preenchida: {doc.get('data_pagamento')}",
            "field_evidence": "status, data_pagamento",
            "confidence": "Médio",
        })

    return anomalies
