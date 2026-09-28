/* =========================================================
   NyayVault — Investigating Officer dashboard

   Add-on for dashboard.js (same pattern as lifecycle.js). For the IO role it
   replaces the "overview" section with:

     My Cases  [+ Add Case]
       case cards  -> Open Case (js/case-workspace.js: Overview | Documents | Evidence | Lifecycle)
       Recent Activity

   Nothing here decides who may see what: the backend (RBAC + ABAC) already
   returns only the cases this officer is authorised for. This file just
   renders them, reusing existing renderers and existing endpoints
   (GET /api/cases, POST /api/cases, GET /api/audit-logs).
   ========================================================= */

/* ---------------- strings ---------------- */
Object.assign(I18N.en, {
  no_cases_title: "No cases to show",
  no_cases_hint: "There are no cases within your organisational scope yet.",

  iod_title: "My Cases",
  iod_scope: "Scope",
  btn_add_case: "+ Add Case",
  iod_no_cases: "You have no cases yet",
  iod_no_cases_hint: "Only cases assigned to you, within your organisational scope, appear here. Use + Add Case to open one.",
  iod_open_case: "Open Case",
  iod_last_activity: "Last activity",
  iod_no_activity: "No activity yet",
  iod_evidence: "evidence",
  iod_recent: "Recent Activity",
  iod_recent_empty: "No recent activity on your cases.",
  iod_back: "← My Cases",
  iod_tab_overview: "Overview",
  iod_tab_documents: "Documents",
  iod_tab_evidence: "Evidence",
  iod_tab_lifecycle: "Lifecycle",
  iod_upload_doc: "Upload document",
  iod_upload_ev: "Upload evidence",
  iod_docs_empty: "No documents in this case yet.",
  iod_ev_empty: "No evidence files in this case yet.",
  iod_sort_note: "Files are sorted by type: video, audio and images are Evidence; PDFs, forensic reports and everything else are Documents.",
  iod_uploading: "Uploading and hashing…",
  iod_details: "Details",

  ov_number: "FIR / Case number",
  ov_title: "Case title",
  ov_status: "Status",
  ov_owner: "Assigned IO",
  ov_org: "Organisational scope",
  ov_opened: "Opened",
  ov_files: "Files",
  ov_integrity: "Evidence integrity",
  ov_verified: "verified",
  ov_pending: "pending",
  ov_tampered: "tampered",
  ov_latest: "Latest activity",

  ac_title: "Add Case",
  ac_number: "FIR Number",
  ac_number_ph: "e.g. FIR-2026-445566",
  ac_number_hint: "Format: FIR-YYYY-NNNNNN — FIR, a four-digit year, then a six-digit number.",
  ac_number_invalid: "FIR number must be in the format FIR-YYYY-NNNNNN (for example FIR-2026-445566).",
  ac_case_title: "Case Title",
  ac_case_title_ph: "e.g. State vs. …",
  ac_status: "Status",
  ac_scope_note: "This case will be opened in your organisational scope ({scope}) and assigned to you.",
  ac_submit: "Create case",
  ac_cancel: "Cancel",
  ac_required: "FIR number and case title are required.",
  ac_created: "Case {n} opened",

  action_access_denied: "ACCESS DENIED",
  lc_action_access_denied: "Access denied",
});
Object.assign(I18N.hi, {
  no_cases_title: "दिखाने के लिए कोई केस नहीं",
  no_cases_hint: "आपके संगठनात्मक दायरे में अभी कोई केस नहीं है।",

  iod_title: "मेरे केस",
  iod_scope: "दायरा",
  btn_add_case: "+ केस जोड़ें",
  iod_no_cases: "आपके पास अभी कोई केस नहीं है",
  iod_no_cases_hint: "यहाँ केवल वही केस दिखते हैं जो आपको सौंपे गए हैं और आपके संगठनात्मक दायरे में आते हैं। नया केस खोलने के लिए + केस जोड़ें दबाएँ।",
  iod_open_case: "केस खोलें",
  iod_last_activity: "अंतिम गतिविधि",
  iod_no_activity: "अभी कोई गतिविधि नहीं",
  iod_evidence: "साक्ष्य",
  iod_recent: "हाल की गतिविधि",
  iod_recent_empty: "आपके केसों पर कोई हाल की गतिविधि नहीं।",
  iod_back: "← मेरे केस",
  iod_tab_overview: "अवलोकन",
  iod_tab_documents: "दस्तावेज़",
  iod_tab_evidence: "साक्ष्य",
  iod_tab_lifecycle: "जीवनचक्र",
  iod_upload_doc: "दस्तावेज़ अपलोड करें",
  iod_upload_ev: "साक्ष्य अपलोड करें",
  iod_docs_empty: "इस केस में अभी कोई दस्तावेज़ नहीं है।",
  iod_ev_empty: "इस केस में अभी कोई साक्ष्य फ़ाइल नहीं है।",
  iod_sort_note: "फ़ाइलें प्रकार के आधार पर बँटी हैं: वीडियो, ऑडियो और चित्र साक्ष्य हैं; PDF, फोरेंसिक रिपोर्ट और बाकी सब दस्तावेज़ हैं।",
  iod_uploading: "अपलोड और हैश हो रहा है…",
  iod_details: "विवरण",

  ov_number: "FIR / केस नंबर",
  ov_title: "केस शीर्षक",
  ov_status: "स्थिति",
  ov_owner: "सौंपे गए आईओ",
  ov_org: "संगठनात्मक दायरा",
  ov_opened: "खोला गया",
  ov_files: "फ़ाइलें",
  ov_integrity: "साक्ष्य इंटीग्रिटी",
  ov_verified: "सत्यापित",
  ov_pending: "लंबित",
  ov_tampered: "छेड़छाड़",
  ov_latest: "नवीनतम गतिविधि",

  ac_title: "केस जोड़ें",
  ac_number: "FIR नंबर",
  ac_number_ph: "जैसे FIR-2026-445566",
  ac_number_hint: "प्रारूप: FIR-YYYY-NNNNNN — FIR, चार अंकों का वर्ष, फिर छह अंकों की संख्या।",
  ac_number_invalid: "FIR नंबर FIR-YYYY-NNNNNN प्रारूप में होना चाहिए (जैसे FIR-2026-445566)।",
  ac_case_title: "केस शीर्षक",
  ac_case_title_ph: "जैसे राज्य बनाम …",
  ac_status: "स्थिति",
  ac_scope_note: "यह केस आपके संगठनात्मक दायरे ({scope}) में खोला जाएगा और आपको सौंपा जाएगा।",
  ac_submit: "केस बनाएँ",
  ac_cancel: "रद्द करें",
  ac_required: "FIR नंबर और केस शीर्षक आवश्यक हैं।",
  ac_created: "केस {n} खोला गया",

  action_access_denied: "प्रवेश अस्वीकृत",
  lc_action_access_denied: "प्रवेश अस्वीकृत",
});

/* ---------------- state + helpers ---------------- */
// Only the FIR format (one place; the backend enforces the same rule in app/utils/doc_category.py).
const IOD = { justCreated: null };
const IOD_FIR_RE = /^FIR-(?:19|20)\d{2}-\d{6}$/;

function iodDate(value){
  if(!value) return null;
  // API timestamps are UTC; SQLite returns them without a "Z".
  if(typeof value === "string" && /^\d{4}-\d{2}-\d{2}T[\d:.]+$/.test(value)) value += "Z";
  const d = new Date(value);
  return isNaN(d) ? null : d;
}
function iodAgo(value){
  const d = iodDate(value);
  if(!d) return t("iod_no_activity");
  const secs = Math.round((d.getTime() - Date.now()) / 1000);
  const abs = Math.abs(secs);
  const lang = localStorage.getItem("nv_lang") || "en";
  try{
    const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
    if(abs < 60) return rtf.format(0, "second");
    if(abs < 3600) return rtf.format(Math.round(secs / 60), "minute");
    if(abs < 86400) return rtf.format(Math.round(secs / 3600), "hour");
    if(abs < 7 * 86400) return rtf.format(Math.round(secs / 86400), "day");
  }catch(_){ /* fall through to an absolute date */ }
  return d.toLocaleDateString();
}
function iodScopeText(org){
  const parts = [org && org.state, org && org.district, org && org.unit].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}
/* ---------------- My Cases (list) ---------------- */
function iodCardHTML(c){
  const evCount = cwEvidence(c).length;
  const docCount = cwDocs(c).length;
  const last = c.lastActivity;
  return `
    <article class="iod-card${c.id === IOD.justCreated ? " iod-new" : ""}" data-open="${escapeHTML(c.id)}" tabindex="0" role="button">
      <div class="iod-card-top">
        <span class="case-num">${escapeHTML(c.number)}</span>
        <span class="status-badge ${statusBadgeClass(c.status)}">${statusBadgeLabel(c.status)}</span>
      </div>
      <h4 class="iod-card-title">${escapeHTML(c.title)}</h4>
      <div class="iod-card-stats">
        <span><b>${docCount}</b> ${escapeHTML(t("docs_count"))}</span>
        <span><b>${evCount}</b> ${escapeHTML(t("iod_evidence"))}</span>
      </div>
      <div class="iod-card-foot">
        <span class="iod-last" title="${escapeHTML(last ? fmtDate(last) : "")}">${escapeHTML(t("iod_last_activity"))}: ${escapeHTML(iodAgo(last))}</span>
        <button type="button" class="btn-ghost iod-open">${escapeHTML(t("iod_open_case"))}</button>
      </div>
    </article>`;
}

function iodRecentHTML(items, opts){
  opts = opts || {};
  if(!items.length) return `<div class="lc-muted">${escapeHTML(t("iod_recent_empty"))}</div>`;
  return items.map(l => {
    const c = findCase(l.case_id);
    return `
      <div class="iod-act">
        <div class="iod-act-top">
          <span class="action-badge ${escapeHTML(l.action)}">${escapeHTML(t("action_" + l.action))}</span>
          ${!opts.hideCase && c ? `<span class="iod-act-case">${escapeHTML(c.number)}</span>` : ""}
          <span class="iod-act-time" title="${escapeHTML(fmtDate(l.timestamp))}">${escapeHTML(iodAgo(l.timestamp))}</span>
        </div>
        <div class="iod-act-detail">${escapeHTML(l.detail)}</div>
      </div>`;
  }).join("");
}

function iodListHTML(){
  const scope = state.me ? iodScopeText(state.me) : "";
  const recent = NV_RECENT.filter(l => findCase(l.case_id)).slice(0, 6);
  return `
    <div class="iod-head">
      <div>
        <h2 class="font-head iod-h">${escapeHTML(t("iod_title"))}</h2>
        ${scope && scope !== "—" ? `<p class="iod-sub">${escapeHTML(t("iod_scope"))}: ${escapeHTML(scope)}</p>` : ""}
      </div>
      <button type="button" class="btn-primary iod-add" id="iodAddCase">${escapeHTML(t("btn_add_case"))}</button>
    </div>
    <div class="iod-layout">
      <section>
        ${NV_CASES.length ? `<div class="iod-grid">${NV_CASES.map(iodCardHTML).join("")}</div>` : `
          <div class="panel iod-empty">
            <h3>${escapeHTML(t("iod_no_cases"))}</h3>
            <p>${escapeHTML(t("iod_no_cases_hint"))}</p>
          </div>`}
      </section>
      <aside class="panel iod-recent">
        <div class="panel-head"><div><h3>${escapeHTML(t("iod_recent"))}</h3></div></div>
        ${iodRecentHTML(recent)}
      </aside>
    </div>`;
}

/* ---------------- Add Case ---------------- */
function iodAddCaseModal(){
  const scope = state.me ? iodScopeText(state.me) : "—";
  openModal(`
    <h3 class="font-head">${escapeHTML(t("ac_title"))}</h3>
    <form id="iodAddForm" class="iod-form" novalidate>
      <label class="iod-lbl" for="acNumber">${escapeHTML(t("ac_number"))}</label>
      <input class="iod-input" id="acNumber" name="number" type="text" maxlength="15" autocomplete="off" spellcheck="false" placeholder="${escapeHTML(t("ac_number_ph"))}" aria-describedby="acNumberHint">
      <p class="iod-hint" id="acNumberHint">${escapeHTML(t("ac_number_hint"))}</p>
      <label class="iod-lbl" for="acTitle">${escapeHTML(t("ac_case_title"))}</label>
      <input class="iod-input" id="acTitle" name="title" type="text" maxlength="200" autocomplete="off" placeholder="${escapeHTML(t("ac_case_title_ph"))}">
      <label class="iod-lbl" for="acStatus">${escapeHTML(t("ac_status"))}</label>
      <select class="iod-input" id="acStatus" name="status">
        <option value="active" selected>${escapeHTML(t("case_active"))}</option>
        <option value="court">${escapeHTML(t("case_in_court"))}</option>
        <option value="closed">${escapeHTML(t("case_closed"))}</option>
      </select>
      <p class="iod-note">${escapeHTML(t("ac_scope_note").replace("{scope}", scope))}</p>
      <div class="iod-form-error" id="iodAddError" role="alert" hidden></div>
      <div class="iod-form-actions">
        <button type="button" class="btn-ghost" id="iodAddCancel">${escapeHTML(t("ac_cancel"))}</button>
        <button type="submit" class="btn-primary" id="iodAddSubmit">${escapeHTML(t("ac_submit"))}</button>
      </div>
    </form>`);
  const form = document.getElementById("iodAddForm");
  const err = document.getElementById("iodAddError");
  const submit = document.getElementById("iodAddSubmit");
  const showErr = msg => { err.textContent = msg; err.hidden = !msg; };
  document.getElementById("iodAddCancel").addEventListener("click", closeModal);
  const numberInput = document.getElementById("acNumber");
  numberInput.focus();
  // clear the format error as soon as the number becomes valid
  numberInput.addEventListener("input", () => { if(IOD_FIR_RE.test(numberInput.value.trim())) showErr(""); });

  form.addEventListener("submit", async e => {
    e.preventDefault();
    const number = form.number.value.trim();
    const title = form.title.value.trim();
    if(!number || !title){ showErr(t("ac_required")); return; }
    if(!IOD_FIR_RE.test(number)){ showErr(t("ac_number_invalid")); document.getElementById("acNumber").focus(); return; }
    showErr("");
    submit.disabled = true;
    try{
      // Existing endpoint. Owner + org scope are set server-side from this officer's account.
      const created = await NV_API.createCase({ number, title, status: form.status.value });
      await loadLiveData();                  // refresh My Cases (+ Recent Activity, incl. the audit event)
      closeModal();
      CW.openId = null; IOD.justCreated = created.id;
      state.section = "overview";
      renderSidebar(); renderSection("overview");
      toast(t("ac_created").replace("{n}", created.number));
      setTimeout(() => { IOD.justCreated = null; }, 2500);
    }catch(ex){
      showErr(ex.message);
      submit.disabled = false;
    }
  });
}

/* ---------------- wiring ---------------- */
function iodWire(){
  const addBtn = document.getElementById("iodAddCase");
  if(addBtn) addBtn.addEventListener("click", iodAddCaseModal);
  // case cards, and the opened case (tabs, uploads, details, lifecycle): js/case-workspace.js
  cwWire();
}

/* ---------------- hook into the existing section registry ---------------- */
const IOD_BASE_OVERVIEW = SECTIONS.overview;
const IOD_BASE_OVERVIEW_HANDLER = HANDLERS.overview;

SECTIONS.overview = function(){
  if(state.role !== "io") return IOD_BASE_OVERVIEW();
  const c = cwOpenCase();          // null once the case is no longer visible
  if(!c) CW.openId = null;
  return c ? cwCaseHTML(c) : iodListHTML();
};
HANDLERS.overview = function(){
  if(state.role !== "io") return IOD_BASE_OVERVIEW_HANDLER();
  iodWire();
};
