"use strict";
const el = id => document.getElementById(id);
const state = { csrf:"", catalogue:null, providers:[], search:[] };

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function add(parent, ...nodes) { nodes.forEach(n => parent.appendChild(n)); return parent; }
function clear(node) { node.replaceChildren(); }
function notice(text, error=false) {
  const n=el("notice"); n.textContent=text; n.classList.toggle("error",error); n.hidden=false;
}
function humanDate(s) {
  if (!s) return "jamais";
  const d=new Date(s); return Number.isNaN(d.valueOf())?s:d.toLocaleDateString("fr-FR", {day:"2-digit",month:"short",year:"numeric"});
}
function safeLink(href, allowed) {
  try {
    const url=new URL(href);
    if (url.protocol!=="https:" || !allowed.includes(url.hostname)) return null;
    return url.href;
  } catch { return null; }
}
async function request(path, options={}) {
  const method=options.method||"GET";
  const headers={"Accept":"application/json"};
  if (method!=="GET") {
    headers["Content-Type"]="application/json";
    headers["X-Gitnotate-CSRF"]=state.csrf;
  }
  const res=await fetch(path,{method,headers,body:options.data?JSON.stringify(options.data):undefined,
                        credentials:"same-origin",cache:"no-store"});
  let data;
  try { data=await res.json(); } catch { throw new Error("Réponse de l'application illisible."); }
  if (!res.ok) throw new Error(typeof data.detail==="string"?data.detail:"Erreur HTTP "+res.status);
  return data;
}
async function runAction(btn, func) {
  btn.disabled=true;
  try { await func(); }
  catch (err) { notice(err.message||"Opération impossible",true); }
  finally { btn.disabled=false; }
}
function show(view) {
  for(const section of document.querySelectorAll(".view"))
    section.hidden=section.id!=="view-"+view;
  for(const btn of document.querySelectorAll(".nav-button"))
    btn.classList.toggle("is-active",btn.dataset.view===view);
  el("breadcrumb").textContent={recherche:"Recherche",sources:"Sources Notion",fournisseurs:"Fournisseurs IA"}[view]||"";
}
function renderStats(data) {
  el("stat-repos").textContent=(data.repos??0).toLocaleString("fr-FR");
  el("stat-enrichis").textContent=(data.enriched??0).toLocaleString("fr-FR");
  el("stat-nouveaux").textContent=data.not_in_historical===null||data.not_in_historical===undefined
    ?"—":data.not_in_historical.toLocaleString("fr-FR");
}
function sourceChoice(source) {
  const label=make("label","source-choice");
  const cb=make("input"); cb.type="checkbox";cb.value=source.source_id;
  cb.className="source-filter"; cb.checked=false;
  const name=make("span","",source.label);
  add(label,cb,name); return label;
}
function renderSources(data) {
  const previous=new Set([...document.querySelectorAll(".source-filter:checked")].map(x=>x.value));
  clear(el("source-filters"));clear(el("source-list"));
  if (!data.sources?.length) {
    el("source-filters").append(make("span","muted","Aucune source"));
    el("source-list").append(make("p","muted","Aucune page inventoriée. Ajoutez une URL Notion ci-dessous."));
    return;
  }
  for (const item of data.sources) {
    const choice=sourceChoice(item);
    const checked=choice.querySelector("input"); checked.checked=previous.has(item.source_id);
    el("source-filters").append(choice);
    const row=make("article","source-card");
    const col=make("div");
    add(col,make("div","source-card-title",item.label),
         make("div","source-card-meta",item.links_total+" liens · "+item.excluded+" hors dépôt · inventorié le "+humanDate(item.scanned_at)));
    const allowed=safeLink(item.url,["app.notion.com","notion.so","www.notion.so","www.notion.com"]);
    if(allowed) {
      const link=make("a","","Ouvrir dans Notion");
      link.href=allowed;link.target="_blank";link.rel="noopener noreferrer";
      add(row,col,link);
    } else add(row,col);
    el("source-list").append(row);
  }
}
async function loadState() {
  const data=await request("/api/etat");
  state.catalogue=data;
  renderStats(data); renderSources(data);
  if(!data.catalogue_present)
    notice("Aucun catalogue V3 local trouvé. Ouvrez « Sources Notion » et ajoutez la première page.",true);
}
function tag(className, text) { return make("span","tag "+className,text); }
function renderResult(item,index) {
  const card=make("article","result-card");
  const number=make("div","result-position",String(index+1).padStart(2,"0"));
  const body=make("div");
  const title=make("h3","result-title");
  const link=make("a","",item.repo);
  const safe=safeLink(item.github,["github.com","www.github.com"]);
  if(safe){link.href=safe;link.target="_blank";link.rel="noopener noreferrer";}
  add(title,link);
  const descr=make("p","result-description",
     item.description||"Aucune description disponible pour ce dépôt ; enrichir les données GitHub pour en savoir plus.");
  const tags=make("div","result-tags");
  add(tags,tag("coverage",item.coverage+"/"+item.total_concepts+" notions couvertes"),
      item.evidence==="GitHub actuel"?tag("proof","Métadonnées GitHub"):tag("pending","Signet non enrichi"));
  if (item.already_in_historical===false) tags.append(tag("new","Absent des 443 fiches"));
  if (item.already_in_historical===true) tags.append(tag("","Fiche historique existante"));
  if (item.archived) tags.append(tag("status","Archivé"));
  if (item.language) tags.append(tag("",item.language));
  if (item.license) tags.append(tag("",item.license));
  const info=make("div","result-info");
  info.append(make("span","","Source : "+(item.source_pages||[]).join(", ")));
  if(item.checked_at) info.append(make("span","","GitHub contrôlé le "+humanDate(item.checked_at)));
  if(item.stars!==null&&item.stars!==undefined)info.append(make("span","",item.stars.toLocaleString("fr-FR")+" étoiles"));
  add(body,title,descr,tags,info);
  return add(card,number,body);
}
function renderResults(data) {
  const container=el("results");clear(container);
  const results=data.results||[];
  el("result-count").textContent=results.length+" dépôt"+(results.length>1?"s":"");
  el("search-description").textContent=results.length
    ?"Résultats lexicaux pour « "+data.need+" ». Les sources et preuves sont indiquées pour chaque dépôt."
    :"Aucun dépôt trouvé pour ce besoin parmi les informations actuellement indexées.";
  if(!results.length) {
    const box=make("div","empty-state");
    add(box,make("span","empty-symbol","⌕"),
        make("h3","","Aucun résultat exploitable"),
        make("p","","Essayez des mots-clés plus précis ou enrichissez quelques dépôts depuis l'onglet Sources."));
    container.append(box); return;
  }
  results.forEach((x,i)=>container.append(renderResult(x,i)));
}
async function onSearch(event) {
  event.preventDefault();
  await runAction(el("btn-search"),async()=>{
    const besoin=el("search-query").value.trim();
    const sources=[...document.querySelectorAll(".source-filter:checked")].map(x=>x.value);
    const results=await request("/api/recherche",{method:"POST",data:{
      besoin,nombre:Number(el("search-limit").value),sources
    }});
    renderResults(results);
  });
}
async function onAddSource(event) {
  event.preventDefault();
  await runAction(el("btn-source-add"),async()=>{
    const url=el("source-url").value.trim();
    const result=await request("/api/sources/ajouter",{method:"POST",data:{url}});
    notice("Page inventoriée : "+result.distinct_repos+" dépôts distincts au total.");
    el("source-url").value="";
    await loadState();
  });
}
async function onSync() {
  await runAction(el("btn-sync"),async()=>{
    const result=await request("/api/sources/actualiser",{method:"POST",data:{}});
    notice("Inventaire actualisé : "+result.distinct_repos+" dépôts dans "+result.sources.length+" source(s).");
    await loadState();
  });
}
async function onEnrich() {
  await runAction(el("btn-enrich"),async()=>{
    const limite=Number(el("enrich-limit").value);
    const result=await request("/api/depot/enrichir",{method:"POST",data:{limite}});
    if(result.stopped)notice("GitHub : "+result.stopped,true);
    else notice("Enrichissement terminé : "+result.updated+" dépôt(s) mis à jour, "+result.errors.length+" erreur(s).");
    await loadState();
  });
}
async function loadProviders() {
  const data=await request("/api/fournisseurs");
  state.providers=data.providers;
  syncProviderForm();
}
function syncProviderForm() {
  const selected=state.providers.find(p=>p.id===el("provider-select").value);
  if(!selected)return;
  el("provider-model").value=selected.modele;
  el("provider-key").value="";
  el("provider-primary").checked=selected.principal;
  el("key-presence").textContent=selected.cle_presente
     ?"(clé enregistrée — laisser vide pour conserver)"
     :"(aucune clé enregistrée)";
}
async function saveProvider(event) {
  event.preventDefault();
  await runAction(el("btn-provider-save"),async()=>{
    const data=await request("/api/fournisseurs/enregistrer",{method:"POST",data:{
      fournisseur:el("provider-select").value,
      modele:el("provider-model").value,
      cle:el("provider-key").value,
      principal:el("provider-primary").checked
    }});
    notice("Paramètres du fournisseur "+data.fournisseur+" enregistrés dans le dossier privé.");
    await loadProviders();
  });
}
async function checkProviders() {
  await runAction(el("btn-provider-check"),async()=>{
    const data=await request("/api/fournisseurs/verifier",{method:"POST",data:{}});
    const output=el("provider-diagnostic");output.hidden=false;
    output.textContent=data.diagnostic||"Aucun résultat.";
    notice(data.ok?"Diagnostic des clés terminé.":"Un ou plusieurs fournisseurs doivent être corrigés.",!data.ok);
  });
}
async function start() {
  for(const button of document.querySelectorAll(".nav-button"))
    button.addEventListener("click",()=>show(button.dataset.view));
  el("search-form").addEventListener("submit",onSearch);
  el("source-form").addEventListener("submit",onAddSource);
  el("btn-sync").addEventListener("click",onSync);
  el("btn-enrich").addEventListener("click",onEnrich);
  el("btn-refresh").addEventListener("click",()=>runAction(el("btn-refresh"),loadState));
  el("provider-form").addEventListener("submit",saveProvider);
  el("btn-provider-check").addEventListener("click",checkProviders);
  el("provider-select").addEventListener("change",syncProviderForm);
  try {
    const boot=await request("/api/bootstrap"); state.csrf=boot.csrf;
    await Promise.all([loadState(),loadProviders()]);
  } catch (err) { notice("Impossible d'initialiser Gitnotate : "+err.message,true); }
}
document.addEventListener("DOMContentLoaded",start);
