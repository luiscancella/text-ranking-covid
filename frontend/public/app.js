(function () {
  "use strict";

  const API = ((window.APP_CONFIG && window.APP_CONFIG.apiUrl) || "http://localhost:8000").replace(/\/+$/, "");
  const METRIC_LABELS = {
    "map": "MAP", "map_cut.1": "MAP@1", "map_cut.3": "MAP@3", "map_cut.5": "MAP@5", "map_cut.10": "MAP@10",
    "ndcg": "nDCG", "ndcg_cut.1": "nDCG@1", "ndcg_cut.3": "nDCG@3", "ndcg_cut.5": "nDCG@5", "ndcg_cut.10": "nDCG@10",
  };

  const $ = (sel) => document.querySelector(sel);
  const el = {
    form: $("#search-form"), q: $("#q"), btn: $("#search-btn"), size: $("#size"),
    status: $("#status"), banner: $("#banner"), topics: $("#topics"),
    section: $("#results-section"), meta: $("#results-meta"), list: $("#results"), pagination: $("#pagination"),
    evalBtn: $("#eval-btn"), depth: $("#depth"), evalOut: $("#evaluation-output"),
    apiUrl: $("#api-url"), apiDocs: $("#api-docs"),
  };

  const state = { q: "", model: "bm25", size: 10, offset: 0, total: 0, indexReady: false };

  el.apiUrl.textContent = API;
  el.apiDocs.href = API + "/docs";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  // Os destaques vêm do Elasticsearch apenas com <em>…</em>; escapa o resto.
  function highlightHtml(s) {
    return esc(s).replace(/&lt;em&gt;/g, "<em>").replace(/&lt;\/em&gt;/g, "</em>");
  }
  function model() { return el.form.closest("main").querySelector('input[name="model"]:checked').value; }

  async function api(path, opts) {
    const res = await fetch(API + path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("Erro " + res.status));
    return data;
  }

  // ---------- estado do índice ----------
  let statusTimer = null;
  async function refreshStatus() {
    try {
      const h = await api("/health");
      const idx = h.indexing || {};
      if (!h.elasticsearch.reachable) {
        setStatus("Elasticsearch indisponível", "err");
        showBanner("Não foi possível conectar ao Elasticsearch em " + esc(h.elasticsearch.url) + ".", "err");
        state.indexReady = false;
      } else if (idx.state === "running") {
        const done = idx.indexed || 0, total = idx.total || 0;
        const pct = total ? Math.round(100 * done / total) : 0;
        setStatus("indexando… " + pct + "%", "warn");
        showBanner(
          "<strong>Indexando a coleção</strong> (" + done.toLocaleString("pt-BR") + (total ? " / " + total.toLocaleString("pt-BR") : "") +
          " documentos). A busca ficará disponível ao final." +
          '<div class="progress"><div style="width:' + pct + '%"></div></div>', "warn");
        state.indexReady = false;
        schedule(2000);
        return;
      } else if (idx.state === "error") {
        setStatus("erro na indexação", "err");
        showBanner("Erro na indexação: " + esc(idx.error), "err");
        state.indexReady = false;
      } else if (h.index.exists && h.index.docs > 0) {
        setStatus(h.index.docs.toLocaleString("pt-BR") + " documentos indexados", "ok");
        hideBanner();
        state.indexReady = true;
      } else {
        setStatus("índice vazio", "warn");
        showBanner('Índice ainda não criado. <button type="button" id="reindex" class="secondary">Indexar coleção</button>', "warn");
        state.indexReady = false;
        $("#reindex").addEventListener("click", async () => {
          try { await api("/index", { method: "POST" }); refreshStatus(); } catch (e) { showBanner(esc(e.message), "err"); }
        });
      }
    } catch (e) {
      setStatus("API indisponível", "err");
      showBanner("Não foi possível conectar à API em " + esc(API) + ". Verifique a variável <code>API_URL</code>.", "err");
      state.indexReady = false;
    }
    schedule(15000);
  }
  function schedule(ms) { clearTimeout(statusTimer); statusTimer = setTimeout(refreshStatus, ms); }
  function setStatus(text, cls) { el.status.textContent = text; el.status.className = "status " + (cls || ""); }
  function showBanner(html, cls) { el.banner.innerHTML = html; el.banner.className = "banner " + (cls || ""); el.banner.hidden = false; }
  function hideBanner() { el.banner.hidden = true; }

  // ---------- tópicos de exemplo ----------
  async function loadTopics() {
    try {
      const data = await api("/topics");
      el.topics.innerHTML = data.topics.map((t) =>
        '<button type="button" class="chip" title="' + esc(t.description) + '" data-q="' + esc(t.query) + '">' + esc(t.qid + ". " + t.query) + "</button>"
      ).join("");
      el.topics.addEventListener("click", (ev) => {
        const b = ev.target.closest(".chip");
        if (!b) return;
        el.q.value = b.dataset.q;
        runSearch(0);
      });
    } catch (_) { /* tópicos são opcionais */ }
  }

  // ---------- busca ----------
  async function runSearch(offset) {
    const q = el.q.value.trim();
    if (!q) return;
    state.q = q; state.model = model(); state.size = parseInt(el.size.value, 10); state.offset = offset;
    el.btn.disabled = true;
    el.section.hidden = false;
    el.meta.textContent = "Buscando…";
    el.list.innerHTML = ""; el.pagination.innerHTML = "";
    try {
      const params = new URLSearchParams({ q, model: state.model, size: state.size, offset });
      const data = await api("/search?" + params);
      state.total = data.total;
      renderResults(data);
      history.replaceState(null, "", "?" + new URLSearchParams({ q, model: state.model }));
    } catch (e) {
      el.meta.textContent = "";
      el.list.innerHTML = '<li class="empty">' + esc(e.message) + "</li>";
    } finally {
      el.btn.disabled = false;
    }
  }

  function renderResults(data) {
    const modelName = data.model === "tfidf" ? "Vetorial TF-IDF" : "BM25";
    el.meta.innerHTML = "<strong>" + data.total.toLocaleString("pt-BR") + "</strong> documentos para <em>“" + esc(data.query) + "”</em> · modelo " + modelName + " · " + data.took_ms + " ms";
    if (!data.results.length) {
      el.list.innerHTML = '<li class="empty">Nenhum documento encontrado.</li>';
      return;
    }
    el.list.innerHTML = data.results.map((r) => {
      const title = r.highlight.title ? highlightHtml(r.highlight.title) : esc(r.title || "(sem título)");
      const snippet = r.highlight.abstract && r.highlight.abstract.length
        ? r.highlight.abstract.map(highlightHtml).join(" … ")
        : esc((r.abstract || "").slice(0, 300)) + (r.abstract && r.abstract.length > 300 ? "…" : "");
      const link = r.url ? '<a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + title + "</a>" : title;
      return (
        '<li class="result">' +
          '<h3><span class="rank">' + r.rank + ".</span> " + link + "</h3>" +
          '<div class="meta">' +
            "<span>docno <code>" + esc(r.docno) + "</code></span>" +
            (r.date ? "<span>" + esc(r.date) + "</span>" : "") +
            (r.doi ? "<span>DOI " + esc(r.doi) + "</span>" : "") +
            "<span>score " + r.score.toFixed(3) + "</span>" +
          "</div>" +
          '<p class="snippet">' + (snippet || "<span class=\"empty\">(sem resumo)</span>") + "</p>" +
          (r.abstract ? "<details><summary>Resumo completo</summary><p>" + esc(r.abstract) + "</p></details>" : "") +
        "</li>"
      );
    }).join("");
    renderPagination();
  }

  function renderPagination() {
    const page = Math.floor(state.offset / state.size) + 1;
    const pages = Math.max(1, Math.ceil(Math.min(state.total, 10000) / state.size));
    if (pages <= 1) { el.pagination.innerHTML = ""; return; }
    el.pagination.innerHTML =
      '<button type="button" class="secondary" data-off="' + (state.offset - state.size) + '"' + (page <= 1 ? " disabled" : "") + ">← Anterior</button>" +
      "<span>Página " + page + " de " + pages + "</span>" +
      '<button type="button" class="secondary" data-off="' + (state.offset + state.size) + '"' + (page >= pages ? " disabled" : "") + ">Próxima →</button>";
    el.pagination.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => { runSearch(parseInt(b.dataset.off, 10)); window.scrollTo({ top: el.section.offsetTop - 70, behavior: "smooth" }); })
    );
  }

  // ---------- avaliação ----------
  async function runEvaluation() {
    el.evalBtn.disabled = true;
    el.evalOut.innerHTML = '<p class="empty">Executando as 30 consultas em cada modelo…</p>';
    try {
      const data = await api("/evaluate?model=all&depth=" + encodeURIComponent(el.depth.value || 1000));
      const rows = data.metrics.map((m) => {
        const vals = data.results.map((r) => r.metrics[m]);
        const best = Math.max.apply(null, vals);
        return "<tr><td>" + (METRIC_LABELS[m] || m) + "</td>" +
          vals.map((v) => '<td class="' + (v === best && vals.some((x) => x !== best) ? "best" : "") + '">' + v.toFixed(4) + "</td>").join("") + "</tr>";
      }).join("");
      el.evalOut.innerHTML =
        '<table class="metrics"><thead><tr><th>Métrica</th>' + data.results.map((r) => "<th>" + esc(r.name) + "</th>").join("") + "</tr></thead>" +
        "<tbody>" + rows + "</tbody></table>" +
        '<p class="empty">Profundidade do ranking: ' + data.depth + " · " + data.results[0].topics + " tópicos.</p>";
    } catch (e) {
      el.evalOut.innerHTML = '<p class="empty">' + esc(e.message) + "</p>";
    } finally {
      el.evalBtn.disabled = false;
    }
  }

  // ---------- init ----------
  el.form.addEventListener("submit", (ev) => { ev.preventDefault(); runSearch(0); });
  document.querySelectorAll('input[name="model"]').forEach((r) => r.addEventListener("change", () => { if (state.q) runSearch(0); }));
  el.size.addEventListener("change", () => { if (state.q) runSearch(0); });
  el.evalBtn.addEventListener("click", runEvaluation);

  const initial = new URLSearchParams(location.search);
  if (initial.get("model")) { const r = document.querySelector('input[name="model"][value="' + initial.get("model") + '"]'); if (r) r.checked = true; }
  if (initial.get("q")) { el.q.value = initial.get("q"); runSearch(0); }

  refreshStatus();
  loadTopics();
})();
