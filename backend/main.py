import os
import io
import json
import zipfile
import asyncio
import hashlib
from datetime import datetime
from typing import Optional

import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from parser import parse_txt_file
from anomaly_detector import detect_anomalies, build_global_context
from exporter import export_to_csv, export_to_excel, export_audit_log

# ─── Inicialização ────────────────────────────────────────────────────────────

app = FastAPI(title="Auditor de NF", version="1.0.0")

# Permite chamadas do frontend (ajuste origin em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cliente Gemini - chave vem de variável de ambiente, NUNCA do frontend
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

PROMPT_VERSION = "v1.0"

# ─── Endpoint principal: upload e processamento ───────────────────────────────

@app.post("/process")
async def process_documents(file: UploadFile = File(...)):

    # Validação de tipo e tamanho (segurança)
    if not file.filename.endswith((".zip", ".txt")):
        raise HTTPException(400, "Apenas arquivos .zip ou .txt são aceitos.")

    content = await file.read()
    if len(content) > 100 * 1024 * 1024:  # 100 MB
        raise HTTPException(400, "Arquivo muito grande. Limite: 100 MB.")

    # Coleta os arquivos brutos (nome → bytes)
    raw_files: dict[str, bytes] = {}

    if file.filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.endswith(".txt") and not name.startswith("__MACOSX"):
                        raw_files[name] = zf.read(name)
        except zipfile.BadZipFile:
            raise HTTPException(400, "ZIP inválido ou corrompido.")
    else:
        raw_files[file.filename] = content

    if not raw_files:
        raise HTTPException(400, "Nenhum arquivo .txt encontrado.")

    # ── Etapa 1: parse local de cada arquivo ──────────────────────────────────
    parsed_docs = []
    for filename, raw_bytes in raw_files.items():
        doc = parse_txt_file(filename, raw_bytes)
        parsed_docs.append(doc)

    # ── Etapa 2: extração de campos via Claude API (em lotes) ─────────────────
    parsed_docs = await extract_fields_batch(parsed_docs)

    # ── Etapa 3: detecção de anomalias (requer visão global do dataset) ───────
    global_ctx = build_global_context(parsed_docs)
    for doc in parsed_docs:
        doc["anomalies"] = detect_anomalies(doc, global_ctx)
        doc["processed_at"] = datetime.utcnow().isoformat()
        doc["prompt_version"] = PROMPT_VERSION

    return {"total": len(parsed_docs), "documents": parsed_docs}


# ─── Extração em lote via Claude ──────────────────────────────────────────────

async def extract_fields_batch(docs: list[dict], batch_size: int = 10) -> list[dict]:

    semaphore = asyncio.Semaphore(5)  # máximo 5 chamadas simultâneas

    async def extract_one(doc: dict) -> dict:
        # Se o parser local já extraiu tudo com sucesso, evita chamada à API
        if doc.get("parse_status") == "ok" and all(
            doc.get(f) for f in ["numero_documento", "fornecedor", "valor_bruto"]
        ):
            doc["extraction_source"] = "local_parser"
            return doc

        async with semaphore:
            return await call_gemini_for_extraction(doc)

    # Processa em lotes para não estourar memória
    results = []
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        batch_results = await asyncio.gather(*[extract_one(d) for d in batch])
        results.extend(batch_results)

    return results


async def call_gemini_for_extraction(doc: dict) -> dict:
 
    raw_text = doc.get("raw_text", "")

    prompt = f"""Você é um extrator de dados de documentos fiscais brasileiros.
Extraia os campos do documento abaixo e retorne JSON puro, sem markdown.

Campos esperados:
tipo_documento, numero_documento, data_emissao, fornecedor, cnpj_fornecedor,
descricao_servico, valor_bruto, data_pagamento, data_emissao_nf,
aprovado_por, banco_destino, status, hash_verificacao

Regras:
- Se um campo não existir ou não puder ser extraído, use null
- Não invente valores — registre null se incerto
- Datas no formato DD/MM/AAAA

Documento:
{raw_text}

Retorne apenas o JSON, sem explicações."""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(prompt)
        )

        text = response.text.strip()
        # Remove possíveis backticks caso o modelo adicione markdown
        text = text.replace("```json", "").replace("```", "").strip()
        extracted = json.loads(text)

        for key, value in extracted.items():
            if value is not None:
                doc[key] = value

        doc["extraction_source"] = "gemini_api"
        doc["parse_status"] = "ok_via_ai"

    except json.JSONDecodeError:
        doc["extraction_source"] = "gemini_api"
        doc["parse_status"] = "ai_json_parse_error"
        doc["extraction_error"] = "Resposta da IA não era JSON válido"

    except Exception as e:
        doc["parse_status"] = "extraction_failed"
        doc["extraction_error"] = "Falha na extração via IA"

    return doc


# ─── Endpoints de exportação ──────────────────────────────────────────────────

@app.post("/export/csv")
async def export_csv(payload: dict):

    docs = payload.get("documents", [])
    csv_bytes = export_to_csv(docs)
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=resultados_auditoria.csv"},
    )


@app.post("/export/excel")
async def export_excel(payload: dict):

    docs = payload.get("documents", [])
    excel_bytes = export_to_excel(docs)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=resultados_auditoria.xlsx"},
    )


@app.post("/export/audit-log")
async def export_audit(payload: dict):
    
    docs = payload.get("documents", [])
    log_bytes = export_audit_log(docs)
    return StreamingResponse(
        io.BytesIO(log_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=log_auditoria.csv"},
    )


@app.get("/health")
def health():
    api_key_ok = bool(os.environ.get("GEMINI_API_KEY"))
    return {
        "status": "ok" if api_key_ok else "degraded",
        "version": "1.0.0",
        "api_key_configured": api_key_ok,
    }
