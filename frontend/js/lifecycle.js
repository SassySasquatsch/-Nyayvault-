/* =========================================================
   NyayVault — Case Document Lifecycle (read-only)

   Add-on for dashboard.js. It registers itself (strings, icon, admin
   section) and exposes two hooks that dashboard.js calls from the existing
   case workspace:
     lifecyclePanelHTML(caseObj) -> panel markup
     lifecycleMount()            -> fetches + renders it

   It only ever performs GET /api/cases/{id}/lifecycle. There is no edit or
   delete control anywhere in this file, by design.
   ========================================================= */

/* ---------------- strings (merged into the existing i18n dictionaries) ---------------- */
Object.assign(I18N.en, {
  nav_lifecycle: "Lifecycle",
  lc_title: "Case Lifecycle",
  lc_desc: "Read-only, chronological history of every recorded document activity in this case.",
  lc_readonly: "Read-only",
  lc_readonly_tip: "Built from the append-only audit log. It cannot be edited or deleted from the interface — by any role.",
  lc_all_docs: "All documents",
  lc_loading: "Loading lifecycle…",
  lc_empty: "No lifecycle events have been recorded for this case yet.",
  lc_events: "events",
  lc_event: "event",
  lc_scope_full: "Full case lifecycle",
  lc_scope_documents: "Evidence & forensic documents",
  lc_scope_security: "Full lifecycle + security details",
  lc_select_event: "Select an event to see its metadata and integrity information.",
  lc_system: "System",
  lc_not_recorded: "Not recorded",
  lc_denied: "You don't have access to this case's lifecycle.",
  lc_f_time: "Timestamp", lc_f_action: "Action", lc_f_user: "Performed by", lc_f_role: "Role",
  lc_f_doc: "Document", lc_f_docid: "Document ID", lc_f_version: "Version", lc_f_reason: "Reason for change",
  lc_f_hash: "SHA-256", lc_f_integrity: "Integrity", lc_f_current: "Current document status",
  lc_f_tx: "Blockchain tx", lc_f_log: "Audit record ID", lc_f_ip: "IP address", lc_f_detail: "Audit detail",
  lc_stage_case: "Case opened", lc_stage_upload: "Upload", lc_stage_version: "Version", lc_stage_access: "Access",
  lc_stage_sharing: "Sharing", lc_stage_verification: "Verification", lc_stage_processing: "Processing",
  lc_stage_anchoring: "Anchoring", lc_stage_court: "Court", lc_stage_report: "Report", lc_stage_other: "Other",
  lc_action_upload: "Document uploaded", lc_action_view: "Document viewed", lc_action_download: "Document downloaded",
  lc_action_verify: "Integrity verified", lc_action_tamper: "Tampering detected", lc_action_present: "Presented in court",
  lc_action_redact: "Redaction run", lc_action_transcribe: "Transcription run", lc_action_report: "Forensic report generated",
  lc_action_case_create: "Case opened", lc_action_forensic_report_upload: "Forensic report uploaded", lc_action_blockchain_anchor: "Hash anchored on blockchain",
  lc_action_blockchain_anchor_failed: "Blockchain anchoring skipped", lc_action_version: "New version created",
  lc_action_court_order_upload: "Court order/judgment uploaded", lc_action_case_close: "Case closed",
  lc_action_sign: "Digitally signed", lc_action_signature_verify: "Signature checked",
  lc_int_signed: "Signed",
  lc_int_hash_recorded: "Hash recorded at upload", lc_int_verified: "Verified — hash matched",
  lc_int_tampered: "Mismatch — possible tampering", lc_int_anchored: "Anchored on blockchain",
  lc_int_not_anchored: "Not anchored on blockchain",
  lc_status_pending: "Pending verification", lc_status_verified: "Verified", lc_status_tampered: "Tampered",
  lc_version_of: "v{n} of {m}",
  lc_version_note: "NyayVault has no version registry, so files with the same name in this case are numbered by upload order (inferred).",
  lc_same_content: "Identical content (same SHA-256) as the previous version.",
  lc_supersedes: "Follows document",
  lc_newer_exists: "A newer version of this file exists.",
});
Object.assign(I18N.hi, {
  nav_lifecycle: "जीवनचक्र",
  lc_title: "केस जीवनचक्र",
  lc_desc: "इस केस में दर्ज हर दस्तावेज़ गतिविधि का केवल-पठन, कालक्रमानुसार इतिहास।",
  lc_readonly: "केवल-पठन",
  lc_readonly_tip: "यह केवल-जोड़ (append-only) ऑडिट लॉग से बनता है। किसी भी भूमिका द्वारा इसे इंटरफ़ेस से बदला या हटाया नहीं जा सकता।",
  lc_all_docs: "सभी दस्तावेज़",
  lc_loading: "जीवनचक्र लोड हो रहा है…",
  lc_empty: "इस केस के लिए अभी तक कोई जीवनचक्र घटना दर्ज नहीं हुई है।",
  lc_events: "घटनाएँ",
  lc_event: "घटना",
  lc_scope_full: "पूर्ण केस जीवनचक्र",
  lc_scope_documents: "साक्ष्य और फ़ोरेंसिक दस्तावेज़",
  lc_scope_security: "पूर्ण जीवनचक्र + सुरक्षा विवरण",
  lc_select_event: "मेटाडेटा और इंटीग्रिटी जानकारी देखने के लिए कोई घटना चुनें।",
  lc_system: "सिस्टम",
  lc_not_recorded: "दर्ज नहीं",
  lc_denied: "आपको इस केस के जीवनचक्र तक पहुँच की अनुमति नहीं है।",
  lc_f_time: "टाइमस्टैम्प", lc_f_action: "कार्रवाई", lc_f_user: "किसके द्वारा", lc_f_role: "भूमिका",
  lc_f_doc: "दस्तावेज़", lc_f_docid: "दस्तावेज़ आईडी", lc_f_version: "संस्करण", lc_f_reason: "बदलाव का कारण",
  lc_f_hash: "SHA-256", lc_f_integrity: "इंटीग्रिटी", lc_f_current: "वर्तमान दस्तावेज़ स्थिति",
  lc_f_tx: "ब्लॉकचेन ट्रांज़ैक्शन", lc_f_log: "ऑडिट रिकॉर्ड आईडी", lc_f_ip: "आईपी पता", lc_f_detail: "ऑडिट विवरण",
  lc_stage_case: "केस खोला गया", lc_stage_upload: "अपलोड", lc_stage_version: "संस्करण", lc_stage_access: "एक्सेस",
  lc_stage_sharing: "साझाकरण", lc_stage_verification: "सत्यापन", lc_stage_processing: "प्रोसेसिंग",
  lc_stage_anchoring: "एंकरिंग", lc_stage_court: "न्यायालय", lc_stage_report: "रिपोर्ट", lc_stage_other: "अन्य",
  lc_action_upload: "दस्तावेज़ अपलोड किया गया", lc_action_view: "दस्तावेज़ देखा गया", lc_action_download: "दस्तावेज़ डाउनलोड किया गया",
  lc_action_verify: "इंटीग्रिटी सत्यापित", lc_action_tamper: "छेड़छाड़ का पता चला", lc_action_present: "न्यायालय में प्रस्तुत",
  lc_action_redact: "रिडैक्शन चलाया गया", lc_action_transcribe: "ट्रांसक्रिप्शन चलाया गया", lc_action_report: "फोरेंसिक रिपोर्ट तैयार",
  lc_action_case_create: "केस खोला गया", lc_action_forensic_report_upload: "फोरेंसिक रिपोर्ट अपलोड की गई", lc_action_blockchain_anchor: "हैश ब्लॉकचेन पर एंकर किया गया",
  lc_action_blockchain_anchor_failed: "ब्लॉकचेन एंकरिंग छोड़ी गई", lc_action_version: "नया संस्करण बना",
  lc_action_court_order_upload: "न्यायालय आदेश/निर्णय अपलोड किया गया", lc_action_case_close: "केस बंद किया गया",
  lc_action_sign: "डिजिटल हस्ताक्षर किया गया", lc_action_signature_verify: "हस्ताक्षर की जाँच की गई",
  lc_int_signed: "हस्ताक्षरित",
  lc_int_hash_recorded: "अपलोड पर हैश दर्ज", lc_int_verified: "सत्यापित — हैश मेल खाया",
  lc_int_tampered: "हैश बेमेल — संभावित छेड़छाड़", lc_int_anchored: "ब्लॉकचेन पर एंकर",
  lc_int_not_anchored: "ब्लॉकचेन पर एंकर नहीं",
  lc_status_pending: "सत्यापन लंबित", lc_status_verified: "सत्यापित", lc_status_tampered: "छेड़छाड़",
  lc_version_of: "v{n} / {m}",
  lc_version_note: "NyayVault में कोई संस्करण रजिस्ट्री नहीं है, इसलिए इस केस में समान नाम वाली फ़ाइलों को अपलोड क्रम से क्रमांकित किया जाता है (अनुमानित)।",
  lc_same_content: "पिछले संस्करण के समान सामग्री (वही SHA-256)।",
  lc_supersedes: "पिछला दस्तावेज़",
  lc_newer_exists: "इस फ़ाइल का नया संस्करण मौजूद है।",
});

ICONS.lifecycle = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="12" r="2"/><path d="M6 8v8M8 6h4a4 4 0 014 4v0M8 18h4a4 4 0 004-4v0"/></svg>`;

/* ---------------- helpers ---------------- */
const LC = { req: 0, caseId: null, docFilter: "", events: [], selectedId: null };

function lcEsc(v){
  return String(v == null ? "" : v).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
}
function lcT(key, fallback){ const v = t(key); return v === key ? fallback : v; }

function lcActionLabel(ev){
  if(ev.stage === "version") return `${t("lc_action_version")} (v${ev.version})`;
  return lcT("lc_action_" + ev.action, ev.action);
}
function lcRoleLabel(role){
  return (role && ROLE_META[role]) ? t(ROLE_META[role].labelKey) : (role || "—");
}
function lcActor(ev){ return ev.actor_name || t("lc_system"); }
function lcVersionText(ev){
  return t("lc_version_of").replace("{n}", ev.version).replace("{m}", ev.version_count);
}
function lcIntegrityClass(s){
  return s === "verified" || s === "anchored" || s === "signed" ? "ok" : s === "tampered" ? "bad" : s ? "neutral" : "";
}
function lcScopeLabel(scope){ return lcT("lc_scope_" + scope, scope); }

/* ---------------- rendering ---------------- */
function lcItemHTML(ev){
  const showVer = ev.version != null && ev.version_count > 1;
  // The action badge already says verified / tampered / anchored; only add a chip where it adds information.
  const showInt = ev.integrity_status === "hash_recorded" || ev.integrity_status === "signed";
  const who = ev.actor_role ? `${lcActor(ev)} · ${lcRoleLabel(ev.actor_role)}` : lcActor(ev);
  return `
    <li class="lc-item stage-${lcEsc(ev.stage)}${ev.action === "tamper" ? " is-bad" : ""}${ev.id === LC.selectedId ? " selected" : ""}"
        data-id="${lcEsc(ev.id)}" tabindex="0" role="button">
      <span class="lc-dot"></span>
      <div class="ti-top">
        <span class="ti-time">${lcEsc(fmtDate(ev.timestamp))}</span>
        <span class="action-badge">${lcEsc(lcActionLabel(ev))}</span>
        ${showVer ? `<span class="lc-chip">${lcEsc(lcVersionText(ev))}</span>` : ""}
        ${showInt ? `<span class="lc-chip">${lcEsc(lcT("lc_int_" + ev.integrity_status, ev.integrity_status))}</span>` : ""}
      </div>
      <div class="lc-who">${lcEsc(who)}</div>
      ${ev.document_id ? `<div class="lc-doc">${lcEsc(ev.document_name || "—")} <code>${lcEsc(ev.document_id)}</code></div>` : ""}
    </li>`;
}

function lcFlowHTML(events){
  const steps = [];
  events.forEach(ev => {
    const label = ev.stage === "version" ? `${t("lc_stage_version")} ${ev.version}` : lcT("lc_stage_" + ev.stage, ev.stage);
    const last = steps[steps.length - 1];
    if(last && last.label === label) last.n++;
    else steps.push({ label, stage: ev.stage, bad: ev.action === "tamper", n: 1 });
  });
  return steps.map(s => `<span class="lc-step stage-${lcEsc(s.stage)}${s.bad ? " is-bad" : ""}">${lcEsc(s.label)}${s.n > 1 ? ` ×${s.n}` : ""}</span>`)
              .join('<span class="lc-arrow">→</span>');
}

function lcDetailHTML(ev){
  const row = (k, v) => `<tr><th>${lcEsc(t(k))}</th><td>${v}</td></tr>`;
  const mono = v => `<code class="lc-mono">${lcEsc(v)}</code>`;
  let version = "—";
  if(ev.version != null){
    const notes = [];
    if(ev.version_count > 1) notes.push(t("lc_version_note"));
    if(ev.supersedes_document_id) notes.push(`${t("lc_supersedes")} ${lcEsc(ev.supersedes_document_id)}.`);
    if(ev.same_content_as_previous) notes.push(t("lc_same_content"));
    if(ev.version < ev.version_count) notes.push(t("lc_newer_exists"));
    version = `<b>${lcEsc(lcVersionText(ev))}</b>${notes.length ? `<div class="lc-note">${notes.map(n => `<div>${n}</div>`).join("")}</div>` : ""}`;
  }
  const integrity = ev.integrity_status
    ? `<span class="lc-chip ${lcIntegrityClass(ev.integrity_status)}">${lcEsc(lcT("lc_int_" + ev.integrity_status, ev.integrity_status))}</span>`
    : "—";
  const current = ev.current_status
    ? `<span class="lc-chip ${lcIntegrityClass(ev.current_status)}">${lcEsc(lcT("lc_status_" + ev.current_status, ev.current_status))}</span>`
    : "—";

  return `
    <div class="lc-detail-title">${lcEsc(lcActionLabel(ev))}</div>
    <table class="lc-table">
      ${row("lc_f_time", `${lcEsc(fmtDate(ev.timestamp))}<div class="lc-note">${lcEsc(ev.timestamp)}</div>`)}
      ${row("lc_f_user", lcEsc(lcActor(ev)))}
      ${row("lc_f_role", lcEsc(lcRoleLabel(ev.actor_role)))}
      ${ev.document_id ? row("lc_f_doc", lcEsc(ev.document_name || "—")) : ""}
      ${ev.document_id ? row("lc_f_docid", mono(ev.document_id)) : ""}
      ${ev.document_id ? row("lc_f_version", version) : ""}
      ${ev.document_id ? row("lc_f_reason", ev.reason ? lcEsc(ev.reason) : `<span class="lc-muted">${lcEsc(t("lc_not_recorded"))}</span>`) : ""}
      ${ev.document_id ? row("lc_f_hash", ev.hash_sha256 ? mono(ev.hash_sha256) : "—") : ""}
      ${ev.document_id ? row("lc_f_integrity", integrity) : ""}
      ${ev.document_id ? row("lc_f_current", current) : ""}
      ${ev.blockchain_tx_hash ? row("lc_f_tx", mono(ev.blockchain_tx_hash)) : ""}
      ${row("lc_f_log", mono(ev.id))}
      ${ev.ip_address ? row("lc_f_ip", mono(ev.ip_address)) : ""}
      ${row("lc_f_detail", lcEsc(ev.detail || "—"))}
    </table>`;
}

function lcSelect(id){
  LC.selectedId = id;
  document.querySelectorAll("#lcList .lc-item").forEach(el => el.classList.toggle("selected", el.getAttribute("data-id") === id));
  const ev = LC.events.find(e => e.id === id);
  const box = document.getElementById("lcDetail");
  if(box) box.innerHTML = ev ? lcDetailHTML(ev) : `<div class="lc-muted">${lcEsc(t("lc_select_event"))}</div>`;
}

/* ---------------- hooks used by dashboard.js ---------------- */
function lifecyclePanelHTML(caseObj){
  if(!caseObj) return "";
  if(LC.caseId !== caseObj.id){ LC.caseId = caseObj.id; LC.docFilter = ""; LC.selectedId = null; LC.events = []; }
  return `
    <section class="lc-panel" id="lcPanel" data-case="${lcEsc(caseObj.id)}">
      <div class="lc-head">
        <div>
          <h4>${lcEsc(t("lc_title"))}</h4>
          <p>${lcEsc(t("lc_desc"))}</p>
        </div>
        <span class="lc-readonly" title="${lcEsc(t("lc_readonly_tip"))}">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="11" width="14" height="9" rx="1.5"/><path d="M8 11V8a4 4 0 018 0v3"/></svg>
          ${lcEsc(t("lc_readonly"))}
        </span>
      </div>
      <div class="lc-toolbar">
        <select id="lcDocFilter" aria-label="${lcEsc(t("lc_f_doc"))}">
          <option value="">${lcEsc(t("lc_all_docs"))}</option>
          ${(caseObj.docs || []).map(d => `<option value="${lcEsc(d.id)}"${d.id === LC.docFilter ? " selected" : ""}>${lcEsc(d.name)} (${lcEsc(d.id)})</option>`).join("")}
        </select>
        <span class="lc-meta" id="lcMeta"></span>
      </div>
      <div class="lc-flow" id="lcFlow"></div>
      <div class="lc-body">
        <ol class="lc-timeline" id="lcList"><li class="lc-muted">${lcEsc(t("lc_loading"))}</li></ol>
        <aside class="lc-detail" id="lcDetail"><div class="lc-muted">${lcEsc(t("lc_select_event"))}</div></aside>
      </div>
    </section>`;
}

async function lifecycleMount(){
  const panel = document.getElementById("lcPanel");
  if(!panel) return;
  const caseId = panel.getAttribute("data-case");
  const token = ++LC.req;
  const list = document.getElementById("lcList");
  const flow = document.getElementById("lcFlow");
  const meta = document.getElementById("lcMeta");
  const detail = document.getElementById("lcDetail");

  document.getElementById("lcDocFilter").addEventListener("change", e => {
    LC.docFilter = e.target.value; LC.selectedId = null; lifecycleMount();
  });
  list.addEventListener("click", e => { const li = e.target.closest(".lc-item"); if(li) lcSelect(li.getAttribute("data-id")); });
  list.addEventListener("keydown", e => {
    if(e.key !== "Enter" && e.key !== " ") return;
    const li = e.target.closest(".lc-item");
    if(li){ e.preventDefault(); lcSelect(li.getAttribute("data-id")); }
  });

  try{
    const data = await NV_API.lifecycle(caseId, LC.docFilter);
    if(token !== LC.req || !panel.isConnected) return;   // superseded by a newer request / re-render
    LC.events = data.events;
    meta.textContent = `${lcScopeLabel(data.scope)} · ${data.total} ${t(data.total === 1 ? "lc_event" : "lc_events")}`;
    flow.innerHTML = lcFlowHTML(data.events);
    list.innerHTML = data.events.length
      ? data.events.map(lcItemHTML).join("")
      : `<li class="lc-muted">${lcEsc(t("lc_empty"))}</li>`;
    if(LC.selectedId) lcSelect(LC.selectedId);
  }catch(err){
    if(token !== LC.req || !panel.isConnected) return;
    const denied = /requires one of|403|not have access/i.test(err.message);
    flow.innerHTML = "";
    list.innerHTML = `<li class="lc-error">${lcEsc(denied ? t("lc_denied") : err.message)}</li>`;
    detail.innerHTML = "";
  }
}

/* ---------------- admin: standalone section (admins have no case workspace) ---------------- */
SECTIONS.lifecycle = function(){
  const c = findCase(state.caseId);
  if(!c) return `<div class="panel"><div class="lc-muted">${lcEsc(t("lc_empty"))}</div></div>`;
  return `
    <div class="case-content-grid panel" style="padding:0;">
      <div class="case-list-col">${caseListHTML(state.caseId)}</div>
      <div class="doc-vault-col" style="padding:20px 20px 20px 22px;">
        <div class="panel-head"><div><h3>${lcEsc(c.number)} — ${lcEsc(c.title)}</h3></div></div>
        ${lifecyclePanelHTML(c)}
      </div>
    </div>`;
};
HANDLERS.lifecycle = function(){
  wireCaseListClicks(() => renderSection("lifecycle"));
  lifecycleMount();
};
