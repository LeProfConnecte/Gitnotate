"use strict";

/*
 * Gitnotate V3-C : recherche 100 % locale. Aucune cle API ne transite par ce code.
 * Toujours construire les resultats avec textContent, jamais innerHTML.
 */
const byId = (id) => document.getElementById(id);
const state = {
  csrf: "",
  catalogue: null,
  allResults: [],
  filter: "all",
  selectedSources: new Set(),
  busy: false,
  lastQuery: "",
  aiProviders: [],
  aiSelected: new Set(),
  aiPreview: null,
};

function element(tag, className, text) {
  const obj = document.createElement(tag);
  if (className) obj.className = className;
  if (text !== undefined && text !== null) obj.textContent = String(text);
  return obj;
}

function append(parent, ...children) {
  for (const child of children) {
    if (child !== null && child !== undefined) parent.appendChild(child);
  }
  return parent;
}

function formatCount(number) {
  return Number.isFinite(number) ? new Intl.NumberFormat("fr-FR").format(number) : "—";
}

function formatDate(value) {
  if (!value) return "Date inconnue";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date inconnue"
    : new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(date);
}

function notify(message, isError = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.classList.toggle("error", !!isError);
  notice.classList.remove("hidden");
}

function clearNotice() {
  const notice = byId("notice");
  notice.classList.remove("error");
  notice.classList.add("hidden");
  notice.textContent = "";
}

function setBusy(enabled) {
  state.busy = !!enabled;
  for (const id of ["search-submit", "refresh-sources", "toggle-add-source"]) {
    byId(id).disabled = state.busy;
  }
  byId("enrich-visible").disabled = state.busy;
  byId("ai-prepare").disabled = state.busy;
  byId("ai-send").disabled = state.busy || !byId("ai-consent-check").checked;
  for (const b of document.querySelectorAll(".card-action")) b.disabled = state.busy;
  for (const input of document.querySelectorAll(".ai-card-check")) input.disabled = state.busy;
  if (!enabled) {
    updateEnrichButton();
    updateAISelection();
  }
}

async function api(url, options = {}) {
  const method = options.method || "GET";
  const headers = { Accept: "application/json" };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = state.csrf;
  }
  const response = await fetch(url, {
    method, headers, cache: "no-store", credentials: "omit",
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Réponse inattendue du serveur local"); }
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? "Informations de formulaire invalides"
      : "Opération refusée par le serveur local";
    throw new Error(message);
  }
  return data;
}

function sourceFilters() {
  const entries = state.catalogue?.sources || [];
  if (state.selectedSources.size === 0 || state.selectedSources.size === entries.length) return [];
  return [...state.selectedSources];
}

function renderSources() {
  const list = byId("source-list");
  list.replaceChildren();
  const sources = state.catalogue?.sources || [];
  byId("refresh-sources").disabled = state.busy || sources.length === 0;
  if (!sources.length) {
    append(list, element("span", "source-placeholder", "Aucune page indexée"));
    return;
  }
  for (const source of sources) {
    const label = element("label", "source-option");
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.value = source.source_id;
    checkbox.checked = state.selectedSources.has(source.source_id);
    checkbox.setAttribute("aria-label", "Inclure " + source.label);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selectedSources.add(source.source_id);
      else state.selectedSources.delete(source.source_id);
      runSearch().catch((err) => notify(err.message, true));
    });
    const labelText = element("span", "source-option-text");
    append(labelText, element("strong", "", source.label || "Page Notion"),
      element("small", "", formatCount(source.links_total) + " liens GitHub repérés"));
    append(label, checkbox, labelText);
    list.appendChild(label);
  }
}

function renderMetrics() {
  const db = state.catalogue || {};
  byId("metric-total").textContent = formatCount(db.repos);
  byId("metric-enriched").textContent = formatCount(db.enriched);
  byId("metric-new").textContent = db.comparison_available
    ? formatCount(db.not_in_historical) : "—";
  byId("nav-count").textContent = formatCount(db.repos);
}

async function loadState() {
  const current = await api("/api/state");
  state.catalogue = current;
  const sourceIDs = new Set((current.sources || []).map((x) => x.source_id));
  const hadSelection = state.selectedSources.size > 0;
  if (hadSelection) {
    state.selectedSources = new Set([...state.selectedSources].filter((x) => sourceIDs.has(x)));
  } else {
    state.selectedSources = new Set([...sourceIDs]);
  }
  renderMetrics();
  renderSources();
  return current;
}

function filteredResults() {
  return state.allResults.filter((repo) => {
    if (state.filter === "enriched") return repo.evidence === "GitHub actuel";
    if (state.filter === "bookmark") return repo.evidence !== "GitHub actuel";
    if (state.filter === "new") return repo.already_in_historical === false;
    return true;
  });
}

function tag(text, kind = "gray") {
  return element("span", "tag " + kind, text);
}

function validGithubLink(link) {
  return typeof link === "string"
    && /^https:\/\/github\.com\/[a-z0-9_.-]+\/[a-z0-9_.-]+\/?$/i.test(link);
}

function createCard(repo, index) {
  const card = element("article", "result-card");
  const header = element("div", "card-top");
  const meta = element("div", "repo-meta");
  meta.appendChild(element("span", "repo-owner", "Dépôt GitHub"));
  const repoTitle = validGithubLink(repo.github)
    ? element("a", "repo-title", repo.repo || "Dépôt sans nom")
    : element("strong", "repo-title", repo.repo || "Dépôt sans nom");
  if (repoTitle.tagName === "A") {
    repoTitle.href = repo.github;
    repoTitle.target = "_blank";
    repoTitle.rel = "noopener noreferrer";
    repoTitle.title = "Ouvrir " + repo.repo + " sur GitHub";
  }
  append(meta, repoTitle, element("span", "external", "↗"));
  header.appendChild(meta);

  const actions = element("div", "card-top-actions");
  if (repo.evidence === "GitHub actuel") {
    const choose = element("label", "ai-card-label");
    const check = element("input", "ai-card-check");
    check.type = "checkbox";
    check.value = repo.repo;
    check.checked = state.aiSelected.has(repo.repo);
    check.disabled = state.busy;
    check.addEventListener("change", () => {
      if (check.checked && state.aiSelected.size >= 5) {
        check.checked = false;
        notify("Sélection limitée à cinq dépôts pour maîtriser les données envoyées.", true);
        return;
      }
      if (check.checked) state.aiSelected.add(repo.repo);
      else state.aiSelected.delete(repo.repo);
      resetAIPreview();
      updateAISelection();
    });
    append(choose, check, element("span", "", "Évaluer avec l'IA"));
    actions.appendChild(choose);
  } else {
    const action = element("button", "card-action", "Enrichir ce dépôt");
    action.type = "button";
    action.disabled = state.busy;
    action.addEventListener("click", () => {
      enrichSelected([repo.repo]).catch((err) => notify(err.message, true));
    });
    actions.appendChild(action);
  }
  header.appendChild(actions);
  card.appendChild(header);

  const description = repo.description?.trim();
  const summary = description
    ? description
    : "Signet enregistré dans Notion. Le README n'a pas encore été consulté : aucun cas d'usage n'est confirmé.";
  card.appendChild(element("p", "card-summary", summary));

  const tags = element("div", "card-tags");
  tags.appendChild(repo.evidence === "GitHub actuel"
    ? tag("GitHub consulté", "ok") : tag("Signet seul", "pending"));
  if (repo.already_in_historical === true) tags.appendChild(tag("Fiche historique", "gray"));
  if (repo.already_in_historical === false) tags.appendChild(tag("Absent de l'historique", "info"));
  tags.appendChild(tag(
    formatCount(repo.coverage) + " / " + formatCount(repo.total_concepts) + " notions lexicales", "gray"));
  if (repo.archived) tags.appendChild(tag("Archivé", "pending"));
  if (repo.language) tags.appendChild(tag(repo.language, "gray"));
  card.appendChild(tags);

  const footer = element("div", "card-footer");
  footer.appendChild(element("span", "", "Source : " + (repo.source_pages || []).join(" · ")));
  if (Number.isFinite(repo.stars)) footer.appendChild(element("span", "", "★ " + formatCount(repo.stars)));
  if (repo.license) footer.appendChild(element("span", "", "Licence : " + repo.license));
  footer.appendChild(element("span", "card-evidence",
    repo.evidence === "GitHub actuel"
      ? "Consulté le " + formatDate(repo.checked_at) : "Informations non vérifiées"));
  card.appendChild(footer);

  card.setAttribute("aria-label", "Résultat " + (index + 1) + " : " + repo.repo);
  return card;
}

function updateEnrichButton() {
  const candidates = filteredResults().filter((x) => x.evidence !== "GitHub actuel").slice(0, 5);
  const btn = byId("enrich-visible");
  btn.disabled = state.busy || candidates.length === 0;
  btn.textContent = candidates.length ? "Enrichir " + candidates.length + " candidats" : "Aucun dépôt à enrichir";
}

function renderResults() {
  const matches = filteredResults();
  const container = byId("results-list");
  container.replaceChildren();
  byId("results-count").textContent = formatCount(matches.length);
  byId("result-subtitle").textContent =
    formatCount(state.allResults.length) + " correspondances chargées · ordre lexical exploratoire";

  if (!matches.length) {
    container.appendChild(element("div", "empty-panel", state.catalogue?.missing
      ? "Aucun inventaire local. Ajoute d'abord une page Notion dans la barre latérale."
      : state.allResults.length
        ? "Aucun résultat ne correspond à ce filtre parmi les candidats chargés."
        : "Aucun dépôt correspondant. Essaie un besoin plus précis ou enrichis davantage de signets."));
  } else {
    matches.forEach((repo, i) => container.appendChild(createCard(repo, i)));
  }
  updateEnrichButton();
  updateAISelection();
}

async function runSearch() {
  if (state.busy) return;
  const query = byId("search-input").value.trim();
  if (query.length < 2) {
    notify("Décris un besoin d'au moins deux caractères.", true);
    return;
  }
  state.lastQuery = query;
  state.aiSelected.clear();
  resetAIPreview(true);
  clearNotice();
  setBusy(true);
  byId("results-list").replaceChildren(element("div", "empty-panel", "Recherche locale en cours…"));
  try {
    const params = new URLSearchParams();
    params.set("q", query);
    params.set("limit", "50");
    for (const id of sourceFilters()) params.append("source", id);
    const result = await api("/api/search?" + params.toString());
    state.allResults = result.results || [];
    renderResults();
  } catch (error) {
    state.allResults = [];
    renderResults();
    notify(error.message, true);
  } finally {
    setBusy(false);
    renderResults();
  }
}

async function enrichSelected(repos) {
  if (state.busy) return;
  if (!repos.length) return;
  const names = repos.slice(0, 5);
  const accepted = window.confirm(
    "Consulter GitHub pour " + names.length + " dépôt(s) sélectionné(s) ?\n\n"
    + names.join("\n")
    + "\n\nJusqu'à deux requêtes GitHub par dépôt. Aucune IA, aucune écriture Notion."
  );
  if (!accepted) return;

  clearNotice();
  setBusy(true);
  notify("Récupération des données GitHub des dépôts sélectionnés…");
  try {
    const result = await api("/api/enrich", { method: "POST", body: { repos: names } });
    await loadState();
    if (result.stopped) notify(result.stopped, true);
    else if (result.errors?.length) notify(result.errors.join(" ; "), true);
    else notify(formatCount(result.updated) + " dépôt(s) enrichi(s). Recherche locale actualisée.");
  } catch (err) {
    notify(err.message, true);
  } finally {
    setBusy(false);
    await runSearch();
  }
}

async function addSource(url) {
  if (state.busy) return;
  if (!window.confirm(
    "Lire cette page avec Gitnotate-ReadOnly et actualiser le catalogue local ?\n\n"
    + url + "\n\nAucune modification Notion."
  )) return;
  setBusy(true);
  clearNotice();
  notify("Lecture paginée des signets Notion en cours…");
  try {
    const result = await api("/api/source", { method: "POST", body: { url } });
    state.selectedSources.clear();
    await loadState();
    notify(formatCount(result.distinct_repos) + " dépôts distincts au catalogue.");
    byId("add-source-form").classList.add("hidden");
    byId("new-source-url").value = "";
  } catch (err) { notify(err.message, true); }
  finally {
    setBusy(false);
    await runSearch();
  }
}

async function refreshSources() {
  if (state.busy) return;
  if (!window.confirm("Actualiser toutes les pages Notion enregistrées, en lecture seule ?")) return;
  setBusy(true);
  clearNotice();
  notify("Actualisation des sources Notion…");
  try {
    const result = await api("/api/sources/refresh", { method: "POST" });
    await loadState();
    notify(formatCount(result.distinct_repos) + " dépôts distincts après actualisation.");
  } catch (err) { notify(err.message, true); }
  finally {
    setBusy(false);
    await runSearch();
  }
}

function bindEvents() {
  byId("search-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    runSearch().catch((err) => notify(err.message, true));
  });
  for (const filter of document.querySelectorAll("[data-filter]")) {
    filter.addEventListener("click", () => {
      state.filter = filter.dataset.filter;
      for (const chip of document.querySelectorAll("[data-filter]")) {
        const active = chip === filter;
        chip.classList.toggle("active", active);
        chip.setAttribute("aria-pressed", active ? "true" : "false");
      }
      renderResults();
    });
  }
  byId("enrich-visible").addEventListener("click", () => {
    const chosen = filteredResults().filter((x) => x.evidence !== "GitHub actuel")
      .slice(0, 5).map((x) => x.repo);
    enrichSelected(chosen).catch((err) => notify(err.message, true));
  });
  byId("toggle-add-source").addEventListener("click", () => {
    byId("add-source-form").classList.toggle("hidden");
    if (!byId("add-source-form").classList.contains("hidden")) byId("new-source-url").focus();
  });
  byId("add-source-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const url = byId("new-source-url").value.trim();
    if (url) addSource(url).catch((err) => notify(err.message, true));
  });
  byId("refresh-sources").addEventListener("click", () => {
    refreshSources().catch((err) => notify(err.message, true));
  });
  bindAIEvents();
}

async function start() {
  bindEvents();
  try {
    state.csrf = (await api("/api/session")).csrf;
    await loadState();
    await loadAIProviders();
    if (!state.catalogue.missing) await runSearch();
    else {
      state.allResults = [];
      renderResults();
      notify("Aucun catalogue local trouvé. Ajoute une page Notion pour commencer.");
    }
  } catch (err) {
    notify("Serveur local indisponible : " + err.message, true);
    byId("results-list").replaceChildren(
      element("div", "empty-panel", "Impossible de charger le catalogue local."));
  }
}

document.addEventListener("DOMContentLoaded", start);
