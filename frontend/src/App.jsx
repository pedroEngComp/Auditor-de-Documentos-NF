import { useState, useCallback, useRef } from "react"
import {
  Upload, FileSearch, AlertTriangle, CheckCircle2, XCircle,
  Download, ChevronDown, ChevronUp, Loader2, FileX, ShieldAlert,
  BarChart3, FileText, Filter, X
} from "lucide-react"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

// ─── Paleta e tema ────────────────────────────────────────────────────────────
// Tema: "sala de auditoria financeira" — escuro, preciso, confiável.
// Tipografia: DM Mono para dados, DM Sans para UI.

const RULE_LABELS = {
  NF_DUPLICADA:              { label: "NF Duplicada",              color: "badge-red" },
  CNPJ_DIVERGENTE:           { label: "CNPJ Divergente",           color: "badge-red" },
  FORNECEDOR_SEM_HISTORICO:  { label: "Fornecedor sem histórico",  color: "badge-red" },
  DATA_NF_APOS_PAGAMENTO:    { label: "Data NF > Pagamento",       color: "badge-red" },
  VALOR_FORA_DA_FAIXA:       { label: "Valor fora da faixa",       color: "badge-amber" },
  APROVADOR_NAO_RECONHECIDO: { label: "Aprovador inválido",        color: "badge-amber" },
  STATUS_INCONSISTENTE:      { label: "Status inconsistente",      color: "badge-amber" },
  ARQUIVO_NAO_PROCESSAVEL:   { label: "Arquivo com erro",          color: "badge-gray" },
}

const CONFIDENCE_COLOR = {
  Alto:  "text-red-400",
  Médio: "text-amber-400",
  Baixo: "text-slate-400",
}

// ─── Componentes base ─────────────────────────────────────────────────────────

function Badge({ rule }) {
  const meta = RULE_LABELS[rule] || { label: rule, color: "badge-gray" }
  return <span className={`badge ${meta.color}`}>{meta.label}</span>
}

function StatCard({ icon: Icon, label, value, accent }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${accent}`}><Icon size={18} /></div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}

// ─── Upload zone ──────────────────────────────────────────────────────────────

function UploadZone({ onUpload, loading }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef()

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) onUpload(file)
  }, [onUpload])

  const handleChange = (e) => {
    const file = e.target.files[0]
    if (file) onUpload(file)
  }

  return (
    <div
      className={`upload-zone ${dragging ? "upload-zone--active" : ""} ${loading ? "upload-zone--loading" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !loading && inputRef.current?.click()}
    >
      <input ref={inputRef} type="file" accept=".zip,.txt" onChange={handleChange} style={{ display: "none" }} />

      {loading ? (
        <div className="upload-zone__inner">
          <Loader2 size={36} className="animate-spin text-emerald-400" />
          <p className="upload-zone__title">Processando documentos…</p>
          <p className="upload-zone__sub">Extraindo campos e detectando anomalias via IA</p>
        </div>
      ) : (
        <div className="upload-zone__inner">
          <div className="upload-icon-wrap">
            <Upload size={28} className="text-emerald-400" />
          </div>
          <p className="upload-zone__title">Arraste o arquivo aqui</p>
          <p className="upload-zone__sub">ou clique para selecionar — <code>.zip</code> ou <code>.txt</code></p>
        </div>
      )}
    </div>
  )
}

// ─── Linha expandível da tabela ───────────────────────────────────────────────

function DocRow({ doc }) {
  const [open, setOpen] = useState(false)
  const hasAnomalies = doc.anomalies?.length > 0
  const isError = doc.parse_status === "encoding_error" || doc.parse_status === "empty_or_unrecognized"

  return (
    <>
      <tr
        className={`table-row ${hasAnomalies ? "table-row--anomaly" : ""} ${isError ? "table-row--error" : ""}`}
        onClick={() => setOpen(o => !o)}
      >
        <td className="td td--mono">
          <span className="flex items-center gap-2">
            {hasAnomalies
              ? <AlertTriangle size={14} className="text-amber-400 shrink-0" />
              : isError
                ? <XCircle size={14} className="text-red-500 shrink-0" />
                : <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
            }
            {doc.filename?.split("/").pop()}
          </span>
        </td>
        <td className="td td--mono">{doc.numero_documento || <Nil />}</td>
        <td className="td">{doc.fornecedor || <Nil />}</td>
        <td className="td td--mono">{doc.valor_bruto || <Nil />}</td>
        <td className="td td--mono">{doc.data_pagamento || <Nil />}</td>
        <td className="td">
          <StatusBadge status={doc.status} />
        </td>
        <td className="td">
          <div className="flex flex-wrap gap-1">
            {doc.anomalies?.map((a, i) => <Badge key={i} rule={a.rule} />)}
          </div>
        </td>
        <td className="td td--action">
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </td>
      </tr>

      {open && (
        <tr className="table-row-detail">
          <td colSpan={8} className="td-detail">
            <div className="detail-grid">
              <div>
                <h4 className="detail-section-title">Dados extraídos</h4>
                <dl className="detail-list">
                  {[
                    ["Tipo", doc.tipo_documento],
                    ["CNPJ", doc.cnpj_fornecedor],
                    ["Serviço", doc.descricao_servico],
                    ["Data emissão", doc.data_emissao],
                    ["Data emissão NF", doc.data_emissao_nf],
                    ["Aprovado por", doc.aprovado_por],
                    ["Banco destino", doc.banco_destino],
                    ["Hash", doc.hash_verificacao],
                    ["Encoding", doc.encoding_used],
                    ["Fonte extração", doc.extraction_source],
                    ["Versão prompt", doc.prompt_version],
                  ].map(([k, v]) => (
                    <div key={k} className="detail-item">
                      <dt className="detail-key">{k}</dt>
                      <dd className="detail-val td--mono">{v || "—"}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              {hasAnomalies && (
                <div>
                  <h4 className="detail-section-title">Anomalias detectadas</h4>
                  <div className="anomaly-list">
                    {doc.anomalies.map((a, i) => (
                      <div key={i} className="anomaly-item">
                        <div className="flex items-center gap-2 mb-1">
                          <ShieldAlert size={13} className="text-red-400 shrink-0" />
                          <Badge rule={a.rule} />
                          <span className={`text-xs font-mono ${CONFIDENCE_COLOR[a.confidence]}`}>
                            {a.confidence}
                          </span>
                        </div>
                        <p className="anomaly-desc">{a.description}</p>
                        <p className="anomaly-evidence">Campo: {a.field_evidence}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {isError && (
                <div>
                  <h4 className="detail-section-title">Erro de processamento</h4>
                  <p className="anomaly-desc text-red-400">{doc.parse_error}</p>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function Nil() {
  return <span className="text-slate-600 text-xs">—</span>
}

function StatusBadge({ status }) {
  if (!status) return <Nil />
  const s = status.toUpperCase()
  const cls = s === "PAGO" ? "badge-green" : s === "CANCELADO" ? "badge-red" : "badge-gray"
  return <span className={`badge ${cls}`}>{status}</span>
}

// ─── Painel de filtros ────────────────────────────────────────────────────────

function FilterBar({ filters, setFilters, ruleOptions }) {
  return (
    <div className="filter-bar">
      <Filter size={14} className="text-slate-400 shrink-0" />

      <select
        className="filter-select"
        value={filters.rule}
        onChange={e => setFilters(f => ({ ...f, rule: e.target.value }))}
      >
        <option value="">Todas as anomalias</option>
        {ruleOptions.map(r => (
          <option key={r} value={r}>{RULE_LABELS[r]?.label || r}</option>
        ))}
      </select>

      <select
        className="filter-select"
        value={filters.status}
        onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
      >
        <option value="">Todos os status</option>
        {["PAGO", "CANCELADO", "PENDENTE"].map(s => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>

      <select
        className="filter-select"
        value={filters.onlyAnomalies}
        onChange={e => setFilters(f => ({ ...f, onlyAnomalies: e.target.value }))}
      >
        <option value="">Todos os documentos</option>
        <option value="yes">Somente com anomalias</option>
        <option value="no">Somente sem anomalias</option>
      </select>

      {(filters.rule || filters.status || filters.onlyAnomalies) && (
        <button
          className="filter-clear"
          onClick={() => setFilters({ rule: "", status: "", onlyAnomalies: "" })}
        >
          <X size={12} /> Limpar filtros
        </button>
      )}
    </div>
  )
}

// ─── App principal ────────────────────────────────────────────────────────────

export default function App() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ rule: "", status: "", onlyAnomalies: "" })
  const [exporting, setExporting] = useState("")

  // ── Upload e processamento ─────────────────────────────────────────────────
  const handleUpload = async (file) => {
    setLoading(true)
    setError(null)
    setResult(null)

    const form = new FormData()
    form.append("file", file)

    try {
      const res = await fetch(`${API_URL}/process`, { method: "POST", body: form })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Erro no processamento")
      }
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Exportação ─────────────────────────────────────────────────────────────
  const handleExport = async (type) => {
    setExporting(type)
    try {
      const res = await fetch(`${API_URL}/export/${type}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ documents: result.documents }),
      })
      const blob = await res.blob()
      const ext = type === "csv" ? "csv" : type === "excel" ? "xlsx" : "csv"
      const name = type === "audit-log" ? "log_auditoria.csv" : `resultados_auditoria.${ext}`
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url; a.download = name; a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError("Falha na exportação: " + e.message)
    } finally {
      setExporting("")
    }
  }

  // ── Filtros e estatísticas ─────────────────────────────────────────────────
  const docs = result?.documents || []

  const stats = {
    total: docs.length,
    anomalies: docs.filter(d => d.anomalies?.length > 0).length,
    errors: docs.filter(d => d.parse_status === "encoding_error" || d.parse_status === "empty_or_unrecognized").length,
    clean: docs.filter(d => !d.anomalies?.length).length,
  }

  const allRules = [...new Set(docs.flatMap(d => d.anomalies?.map(a => a.rule) || []))]

  const filtered = docs.filter(doc => {
    if (filters.rule && !doc.anomalies?.some(a => a.rule === filters.rule)) return false
    if (filters.status && doc.status?.toUpperCase() !== filters.status) return false
    if (filters.onlyAnomalies === "yes" && !doc.anomalies?.length) return false
    if (filters.onlyAnomalies === "no" && doc.anomalies?.length > 0) return false
    return true
  })

  return (
    <div className="app">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="header">
        <div className="header__inner">
          <div className="header__brand">
            <FileSearch size={20} className="text-emerald-400" />
            <span className="header__title">Auditor NF</span>
            <span className="header__badge">IA</span>
          </div>
          <span className="header__sub">NLConsulting · Auditoria de Documentos Fiscais</span>
        </div>
      </header>

      <main className="main">

        {/* ── Upload ──────────────────────────────────────────────────────── */}
        <section className="section">
          <UploadZone onUpload={handleUpload} loading={loading} />
          {error && (
            <div className="error-banner">
              <XCircle size={15} className="shrink-0" />
              {error}
            </div>
          )}
        </section>

        {/* ── Resultados ─────────────────────────────────────────────────── */}
        {result && (
          <>
            {/* Stats */}
            <section className="section">
              <div className="stats-grid">
                <StatCard icon={FileText}     label="Documentos"    value={stats.total}     accent="accent-blue" />
                <StatCard icon={AlertTriangle} label="Com anomalias" value={stats.anomalies} accent="accent-amber" />
                <StatCard icon={XCircle}      label="Com erro"      value={stats.errors}    accent="accent-red" />
                <StatCard icon={CheckCircle2} label="Sem anomalias" value={stats.clean}     accent="accent-green" />
              </div>
            </section>

            {/* Exportação */}
            <section className="section">
              <div className="export-bar">
                <span className="export-label">
                  <Download size={14} /> Exportar resultados
                </span>
                {[
                  { type: "csv",       label: "CSV" },
                  { type: "excel",     label: "Excel (.xlsx)" },
                  { type: "audit-log", label: "Log de auditoria" },
                ].map(({ type, label }) => (
                  <button
                    key={type}
                    className="btn-export"
                    onClick={() => handleExport(type)}
                    disabled={!!exporting}
                  >
                    {exporting === type
                      ? <Loader2 size={13} className="animate-spin" />
                      : <Download size={13} />
                    }
                    {label}
                  </button>
                ))}
              </div>
            </section>

            {/* Filtros */}
            <section className="section">
              <FilterBar filters={filters} setFilters={setFilters} ruleOptions={allRules} />
            </section>

            {/* Tabela */}
            <section className="section">
              <div className="table-wrap">
                <div className="table-header-row">
                  <span className="table-count">
                    {filtered.length} de {docs.length} documentos
                  </span>
                </div>
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        {["Arquivo", "Nº NF", "Fornecedor", "Valor", "Pagamento", "Status", "Anomalias", ""].map(h => (
                          <th key={h} className="th">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="td-empty">
                            <FileX size={24} className="mx-auto mb-2 text-slate-600" />
                            Nenhum documento corresponde aos filtros aplicados.
                          </td>
                        </tr>
                      ) : (
                        filtered.map((doc, i) => <DocRow key={i} doc={doc} />)
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  )
}
