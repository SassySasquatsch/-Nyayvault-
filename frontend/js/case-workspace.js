/* =========================================================
   NyayVault — case workspace (shared by IO, Forensic and Judge)

   Add-on for dashboard.js (same pattern as lifecycle.js / io-dashboard.js).
   Opening a case shows the same header + tabs for every role; only the tab
   set and the contextual actions differ:

     IO        Overview | Documents | Evidence | Lifecycle
     Judge     Overview | Documents | Evidence | Lifecycle    + Court Presentation
     Forensic  Overview | Evidence | Verify | Forensic Report | Lifecycle
                                                              + Upload Forensic Report

   Where the case opens (the "host" section):
     IO -> Overview (My Cases)   Judge -> Overview   Forensic -> Cases

   Also here: Document Details (hash, uploader, status, blockchain, and the
   EXIF / metadata that used to have its own menu item), authenticated
   downloads, the forensic-report upload, and search click-through.

   Nothing here decides who may see or do what. The backend (RBAC + ABAC)
   already returns only what the caller may see and refuses everything else;
   this file only renders it and calls existing endpoints plus
   POST /api/cases/{id}/forensic-reports.
   ========================================================= */

/* ---------------- strings ---------------- */
Object.assign(I18N.en, {
  cw_back_cases: "← Cases",
  cw_tab_verify: "Verify",
  cw_tab_report: "Forensic Report",
  cw_forensic_report: "Forensic Report",
  cw_download: "Download",
  cw_present: "Court Presentation",
  cw_present_failed: "Could not open the presentation",
  search_none: "No matches found.",

  cw_upload_report: "+ Upload Forensic Report",
  cw_report_types: "A forensic report must be a PDF or Word file (.pdf, .doc, .docx).",
  cw_report_uploading: "Uploading and hashing the report…",
  cw_report_uploaded: "Forensic report uploaded",
  cw_report_note: "Each report is hashed (SHA-256) on upload, stamped with your name and the time, and added to this case's lifecycle and audit trail. Only users authorised for this case can open it.",
  cw_reports_empty: "No forensic report has been uploaded for this case yet.",
  cw_receipt_title: "Report recorded",
  cw_receipt_hash: "SHA-256 generated",
  cw_receipt_by: "Uploaded by",
  cw_receipt_at: "Uploaded",

  cw_ev_all_note: "Every file in this case other than forensic reports — for examination and integrity checks.",
  cw_verify_note: "Select a file and compare the SHA-256 recorded at upload with the file as it is on disk right now. Forensic reports can be verified too.",
  cw_verify_none: "There are no files in this case to verify yet.",
  cw_hash_upload: "Hash at upload",
  cw_hash_now: "Hash now",

  ov_reports: "Forensic reports",

  cw_queue_title: "Needs verification",
  cw_queue_desc: "Files that are not currently verified, across your cases.",
  cw_queue_empty: "Nothing is waiting for verification.",
  cw_recent_reports: "Recent forensic reports",
  cw_recent_reports_empty: "No forensic reports have been uploaded yet.",

  cw_dd_case: "Case",
  cw_dd_by: "Uploaded by",
  cw_dd_at: "Uploaded",
  cw_dd_size: "Size",
  cw_dd_hash: "SHA-256",
  cw_dd_status: "Integrity",
  cw_dd_verified: "Last verified",
  cw_dd_tx: "Blockchain tx",
  cw_dd_tx_none: "Not anchored (yet)",
  cw_dd_id: "Document ID",
  cw_meta_title: "Metadata (EXIF)",
  cw_meta_note: "Read automatically at upload. Images carry camera data and PDFs carry producer data; other files show only the file timestamp.",

  cw_court_order: "Court Order / Judgment",
  cw_signed_badge: "Digitally signed",
  btn_verify_signature: "Verify Signature",
  sig_none: "This document has not been digitally signed.",
  sig_valid: "Signature valid",
  sig_invalid: "Signature invalid — file may have changed since signing",
  sig_signer: "Signed by",
  sig_role: "Role",
  sig_signed_at: "Signed at",
  sig_algorithm: "Algorithm",

  cw_upload_court_order: "+ Upload Court Order",
  cw_court_order_types: "A court order / judgment must be a PDF or Word file (.pdf, .doc, .docx).",
  cw_court_order_uploading: "Uploading and hashing the order…",
  cw_court_order_uploaded: "Court order/judgment uploaded",

  cw_close_case: "Close Case",
  cw_close_case_confirm: "Close this case? This action is recorded and digitally signed.",
  cw_close_case_done: "Case closed",
  cw_close_case_already: "This case is already closed.",
});
Object.assign(I18N.hi, {
  cw_back_cases: "← केस",
  cw_tab_verify: "सत्यापन",
  cw_tab_report: "फोरेंसिक रिपोर्ट",
  cw_forensic_report: "फोरेंसिक रिपोर्ट",
  cw_download: "डाउनलोड",
  cw_present: "न्यायालय प्रस्तुति",
  cw_present_failed: "प्रस्तुति नहीं खोली जा सकी",
  search_none: "कोई परिणाम नहीं मिला।",

  cw_upload_report: "+ फोरेंसिक रिपोर्ट अपलोड करें",
  cw_report_types: "फोरेंसिक रिपोर्ट PDF या Word फ़ाइल (.pdf, .doc, .docx) होनी चाहिए।",
  cw_report_uploading: "रिपोर्ट अपलोड और हैश हो रही है…",
  cw_report_uploaded: "फोरेंसिक रिपोर्ट अपलोड हुई",
  cw_report_note: "हर रिपोर्ट अपलोड पर हैश (SHA-256) की जाती है, आपके नाम और समय के साथ दर्ज होती है, और इस केस के जीवनचक्र व ऑडिट ट्रेल में जुड़ जाती है। इसे केवल इस केस के लिए अधिकृत उपयोगकर्ता ही खोल सकते हैं।",
  cw_reports_empty: "इस केस के लिए अभी कोई फोरेंसिक रिपोर्ट अपलोड नहीं हुई है।",
  cw_receipt_title: "रिपोर्ट दर्ज हुई",
  cw_receipt_hash: "SHA-256 बना",
  cw_receipt_by: "अपलोड करने वाले",
  cw_receipt_at: "अपलोड समय",

  cw_ev_all_note: "इस केस की फोरेंसिक रिपोर्ट के अलावा हर फ़ाइल — जाँच और इंटीग्रिटी परीक्षण के लिए।",
  cw_verify_note: "कोई फ़ाइल चुनें और अपलोड के समय दर्ज SHA-256 की तुलना डिस्क पर मौजूद फ़ाइल से करें। फोरेंसिक रिपोर्ट भी सत्यापित की जा सकती हैं।",
  cw_verify_none: "इस केस में सत्यापन के लिए अभी कोई फ़ाइल नहीं है।",
  cw_hash_upload: "अपलोड पर हैश",
  cw_hash_now: "अभी का हैश",

  ov_reports: "फोरेंसिक रिपोर्ट",

  cw_queue_title: "सत्यापन आवश्यक",
  cw_queue_desc: "आपके केसों की वे फ़ाइलें जो अभी सत्यापित नहीं हैं।",
  cw_queue_empty: "सत्यापन के लिए कुछ भी लंबित नहीं है।",
  cw_recent_reports: "हाल की फोरेंसिक रिपोर्ट",
  cw_recent_reports_empty: "अभी तक कोई फोरेंसिक रिपोर्ट अपलोड नहीं हुई है।",

  cw_dd_case: "केस",
  cw_dd_by: "अपलोड करने वाले",
  cw_dd_at: "अपलोड समय",
  cw_dd_size: "आकार",
  cw_dd_hash: "SHA-256",
  cw_dd_status: "इंटीग्रिटी",
  cw_dd_verified: "अंतिम सत्यापन",
  cw_dd_tx: "ब्लॉकचेन ट्रांज़ैक्शन",
  cw_dd_tx_none: "एंकर नहीं (अभी)",
  cw_dd_id: "दस्तावेज़ आईडी",
  cw_meta_title: "मेटाडेटा (EXIF)",
  cw_meta_note: "अपलोड पर स्वतः पढ़ा गया। चित्रों में कैमरा डेटा और PDF में प्रोड्यूसर डेटा होता है; अन्य फ़ाइलों में केवल फ़ाइल का टाइमस्टैम्प दिखता है।",

  cw_court_order: "न्यायालय आदेश / निर्णय",
  cw_signed_badge: "डिजिटल हस्ताक्षरित",
  btn_verify_signature: "हस्ताक्षर सत्यापित करें",
  sig_none: "इस दस्तावेज़ पर डिजिटल हस्ताक्षर नहीं किए गए हैं।",
  sig_valid: "हस्ताक्षर मान्य",
  sig_invalid: "हस्ताक्षर अमान्य — हस्ताक्षर के बाद फ़ाइल बदली हो सकती है",
  sig_signer: "हस्ताक्षरकर्ता",
  sig_role: "भूमिका",
  sig_signed_at: "हस्ताक्षर समय",
  sig_algorithm: "एल्गोरिद्म",

  cw_upload_court_order: "+ न्यायालय आदेश अपलोड करें",
  cw_court_order_types: "न्यायालय आदेश/निर्णय PDF या Word फ़ाइल (.pdf, .doc, .docx) होनी चाहिए।",
  cw_court_order_uploading: "आदेश अपलोड और हैश हो रहा है…",
  cw_court_order_uploaded: "न्यायालय आदेश/निर्णय अपलोड हुआ",

  cw_close_case: "केस बंद करें",
  cw_close_case_confirm: "यह केस बंद करें? यह कार्रवाई दर्ज और डिजिटल हस्ताक्षरित होती है।",
  cw_close_case_done: "केस बंद हुआ",
  cw_close_case_already: "यह केस पहले से बंद है।",
});

/* ---------------- state + helpers ---------------- */
const CW = { openId: null, tab: "overview", docId: null, justUploaded: null };

// where each role's opened case lives, and which tabs it has
const CW_HOST = { io: "overview", judge: "overview", forensic: "cases" };
const CW_TABS = {
  io:       ["overview", "documents", "evidence", "lifecycle"],
  judge:    ["overview", "documents", "evidence", "lifecycle"],
  forensic: ["overview", "evidence", "verify", "report", "lifecycle"],
};
const CW_TAB_LABEL = {
  overview: "iod_tab_overview", documents: "iod_tab_documents", evidence: "iod_tab_evidence",
  lifecycle: "iod_tab_lifecycle", verify: "cw_tab_verify", report: "cw_tab_report",
};
const CW_REPORT_EXTENSIONS = ["pdf", "doc", "docx"];

// Files are sorted by their existing `type`: media -> Evidence, everything else -> Documents.
// Forensic reports are always documents.
const CW_MEDIA_TYPES = ["VIDEO", "AUDIO", "IMAGE"];
const cwIsMedia = d => CW_MEDIA_TYPES.includes(d.type) && !d.isReport;
const cwDocs = c => c.docs.filter(d => !cwIsMedia(d));
const cwEvidence = c => c.docs.filter(cwIsMedia);
const cwReports = c => c.docs.filter(d => d.isReport);
// The forensic officer has no Documents tab, so their Evidence tab is every non-report file.
const cwEvidenceFor = c => state.role === "forensic" ? c.docs.filter(d => !d.isReport) : cwEvidence(c);

const cwOpenCase = () => CW.openId ? findCase(CW.openId) : null;
const cwTabs = () => CW_TABS[state.role] || CW_TABS.io;

function cwSize(bytes){
  const n = Number(bytes) || 0;
  if(n < 1024) return `${n} B`;
  if(n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if(n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
function cwStatusChip(status){
  return `<span class="doc-status ${docStatusClass(status)}"><span class="dot"></span>${escapeHTML(docStatusLabel(status))}</span>`;
}

/* ---------------- navigation ---------------- */
function cwOpen(caseId, tab, docId){
  const host = CW_HOST[state.role];
  if(!host || !findCase(caseId)) return;
  CW.openId = caseId;
  CW.tab = cwTabs().includes(tab) ? tab : "overview";
  CW.docId = docId || null;
  CW.justUploaded = null;
  state.caseId = caseId;
  if(state.section !== host){ state.section = host; renderSidebar(); }
  renderSection(host);
}
function cwClose(){
  CW.openId = null; CW.docId = null; CW.justUploaded = null;
  renderSection(state.section);
}
// A search hit opens its case - on Documents / Evidence when the hit is a file.
function cwOpenFromSearch(caseId, docId){
  const c = findCase(caseId);
  if(!c){ toast(t("no_cases_hint"), true); return; }
  let tab = "overview";
  const d = docId ? findDoc(c, docId) : null;
  if(d) tab = cwIsMedia(d) ? "evidence" : "documents";
  cwOpen(caseId, tab);
}

/* ---------------- case list (cards) ---------------- */
function cwCardGridHTML(){
  if(!NV_CASES.length){
    return `<div class="panel iod-empty"><h3>${escapeHTML(t("no_cases_title"))}</h3><p>${escapeHTML(t("no_cases_hint"))}</p></div>`;
  }
  return `<div class="iod-grid">${NV_CASES.map(iodCardHTML).join("")}</div>`;
}

/* ---------------- forensic overview ---------------- */
function cwForensicOverviewHTML(){
  const queue = [];
  NV_CASES.forEach(c => c.docs.forEach(d => { if(d.status !== "verified") queue.push({ c, d }); }));
  const reports = [];
  NV_CASES.forEach(c => cwReports(c).forEach(d => reports.push({ c, d })));
  reports.sort((a, b) => String(b.d.uploadedAt || "").localeCompare(String(a.d.uploadedAt || "")));

  const row = ({ c, d }, tab) => `
    <div class="case-list-item cw-jump" tabindex="0" role="button" data-case="${escapeHTML(c.id)}" data-doc="${escapeHTML(d.id)}" data-tab="${tab}">
      <span class="case-num">${escapeHTML(c.number)}</span>
      <div class="case-title">${escapeHTML(d.name)}</div>
      <div class="case-meta">${cwStatusChip(d.status)}<span>${escapeHTML(d.uploader)} · ${escapeHTML(d.time)}</span></div>
    </div>`;

  return overviewKpisHTML() + `
    <div class="two-col">
      <div class="panel">
        <div class="panel-head"><div><h3>${escapeHTML(t("cw_queue_title"))}</h3><p>${escapeHTML(t("cw_queue_desc"))}</p></div></div>
        ${queue.length ? queue.slice(0, 8).map(x => row(x, "verify")).join("") : `<div class="lc-muted">${escapeHTML(t("cw_queue_empty"))}</div>`}
      </div>
      <div class="panel">
        <div class="panel-head"><h3>${escapeHTML(t("cw_recent_reports"))}</h3></div>
        ${reports.length ? reports.slice(0, 6).map(x => row(x, "report")).join("") : `<div class="lc-muted">${escapeHTML(t("cw_recent_reports_empty"))}</div>`}
      </div>
    </div>`;
}

/* ---------------- opened case ---------------- */
function cwTabsHTML(c){
  const counts = { documents: cwDocs(c).length, evidence: cwEvidenceFor(c).length, report: cwReports(c).length };
  return `
    <div class="iod-tabs" role="tablist">
      ${cwTabs().map(id => `
        <button type="button" role="tab" class="iod-tab${CW.tab === id ? " active" : ""}" data-tab="${id}" aria-selected="${CW.tab === id}">
          ${escapeHTML(t(CW_TAB_LABEL[id]))}${counts[id] != null ? ` <span class="iod-count">${counts[id]}</span>` : ""}
        </button>`).join("")}
    </div>`;
}

function cwOverviewHTML(c){
  const verified = c.docs.filter(d => d.status === "verified").length;
  const tampered = c.docs.filter(d => d.status === "tampered").length;
  const pending = c.docs.length - verified - tampered;
  const row = (k, v) => `<tr><td>${escapeHTML(t(k))}</td><td>${v}</td></tr>`;
  // IO: the recent-activity feed already loaded for My Cases. Judge / forensic: fetched for this case
  // (a forensic officer only sees document-linked events, same as their Lifecycle).
  const activity = state.role === "io"
    ? iodRecentHTML(NV_RECENT.filter(l => l.case_id === c.id).slice(0, 5), { hideCase: true })
    : `<div id="cwOvActivity" data-case="${escapeHTML(c.id)}"><div class="lc-muted">${escapeHTML(t("lc_loading"))}</div></div>`;
  return `
    <div class="iod-ov">
      <table class="exif-table iod-facts">
        ${row("ov_number", `<span class="case-num">${escapeHTML(c.number)}</span>`)}
        ${row("ov_title", escapeHTML(c.title))}
        ${row("ov_status", `<span class="status-badge ${statusBadgeClass(c.status)}">${statusBadgeLabel(c.status)}</span>`)}
        ${row("ov_owner", escapeHTML(c.ownerName || "—"))}
        ${row("ov_org", escapeHTML(iodScopeText(c.org)))}
        ${row("ov_opened", escapeHTML(fmtDate(c.createdAt)))}
        ${row("ov_files", `${cwDocs(c).length} ${escapeHTML(t("docs_count"))} · ${cwEvidence(c).length} ${escapeHTML(t("iod_evidence"))}`)}
        ${row("ov_reports", String(cwReports(c).length))}
        ${row("ov_integrity", `${verified} ${escapeHTML(t("ov_verified"))} · ${pending} ${escapeHTML(t("ov_pending"))}${tampered ? ` · <b class="iod-bad">${tampered} ${escapeHTML(t("ov_tampered"))}</b>` : ""}`)}
        ${row("ov_latest", escapeHTML(c.lastActivity ? fmtDate(c.lastActivity) : t("iod_no_activity")))}
      </table>
      <div class="iod-ov-activity">
        <h4>${escapeHTML(t("iod_recent"))}</h4>
        ${activity}
      </div>
    </div>`;
}

async function cwLoadOverviewActivity(){
  const box = document.getElementById("cwOvActivity");
  if(!box) return;
  const caseId = box.getAttribute("data-case");
  try{
    let logs = await NV_API.audit(caseId);
    if(state.role === "forensic") logs = logs.filter(l => l.document_id);
    if(!box.isConnected) return;
    box.innerHTML = iodRecentHTML(logs.slice(0, 5), { hideCase: true });
  }catch(err){
    if(box.isConnected) box.innerHTML = `<div class="lc-muted">${escapeHTML(err.message)}</div>`;
  }
}

function cwFilesHTML(c, kind){
  const files = kind === "documents" ? cwDocs(c) : cwEvidenceFor(c);
  const canUpload = state.role === "io";
  const note = (kind === "evidence" && state.role === "forensic") ? t("cw_ev_all_note") : t("iod_sort_note");
  return `
    <div class="iod-files-head">
      <p class="iod-note">${escapeHTML(note)}</p>
      ${canUpload ? `
        <button type="button" class="btn-ghost iod-upload">${escapeHTML(t(kind === "evidence" ? "iod_upload_ev" : "iod_upload_doc"))}</button>
        <input type="file" id="cwFile" style="display:none">` : ""}
    </div>
    ${files.length
      ? docListHTML({ docs: files }, null, { showActions: true, showStatus: true, actionLabel: t("iod_details") })
      : `<div class="lc-muted">${escapeHTML(t(kind === "evidence" ? "iod_ev_empty" : "iod_docs_empty"))}</div>`}`;
}

function cwVerifyHTML(c){
  if(!c.docs.length) return `<div class="lc-muted">${escapeHTML(t("cw_verify_none"))}</div>`;
  const sel = (CW.docId && findDoc(c, CW.docId)) || c.docs[0];
  CW.docId = sel.id;
  return `
    <p class="iod-note cw-verify-note">${escapeHTML(t("cw_verify_note"))}</p>
    ${docListHTML({ docs: c.docs }, sel.id, { selectable: true, showStatus: true })}
    <button type="button" class="btn-primary cw-verify-btn" id="cwVerifyBtn">${escapeHTML(t("btn_verify"))}</button>
    <div class="hash-result" id="cwVerifyResult"></div>`;
}

function cwReceiptHTML(d){
  return `
    <div class="hash-result visible cw-receipt" id="cwReceipt">
      <div class="label"><b>${escapeHTML(t("cw_receipt_title"))}</b> — ${escapeHTML(d.name)}</div>
      <div class="label">${escapeHTML(t("cw_receipt_hash"))}</div>
      <div class="hash-val">${escapeHTML(d.fullHash)}</div>
      <div class="label cw-receipt-meta">${escapeHTML(t("cw_receipt_by"))}: <b>${escapeHTML(d.uploader)}</b> · ${escapeHTML(t("cw_receipt_at"))}: <b>${escapeHTML(d.time)}</b></div>
    </div>`;
}

function cwReportHTML(c){
  const reports = cwReports(c).slice().sort((a, b) => String(b.uploadedAt || "").localeCompare(String(a.uploadedAt || "")));
  const fresh = CW.justUploaded ? reports.find(d => d.id === CW.justUploaded) : null;
  return `
    <div class="iod-files-head">
      <p class="iod-note">${escapeHTML(t("cw_report_note"))}</p>
    </div>
    ${fresh ? cwReceiptHTML(fresh) : ""}
    ${reports.length
      ? docListHTML({ docs: reports }, null, { showActions: true, showStatus: true, showDownload: true, actionLabel: t("iod_details") })
      : `<div class="panel cw-report-empty">
           <p>${escapeHTML(t("cw_reports_empty"))}</p>
           <button type="button" class="btn-primary cw-upload-report">${escapeHTML(t("cw_upload_report"))}</button>
         </div>`}`;
}

function cwCaseHTML(c){
  let body = "";
  if(CW.tab === "overview") body = cwOverviewHTML(c);
  else if(CW.tab === "documents") body = cwFilesHTML(c, "documents");
  else if(CW.tab === "evidence") body = cwFilesHTML(c, "evidence");
  else if(CW.tab === "verify") body = cwVerifyHTML(c);
  else if(CW.tab === "report") body = cwReportHTML(c);
  else body = lifecyclePanelHTML(c);

  // contextual actions, by role
  let actions = "";
  if(state.role === "judge"){
    actions += `<button type="button" class="btn-primary cw-action" id="cwPresent">${escapeHTML(t("cw_present"))}</button>
                <button type="button" class="btn-secondary cw-action cw-upload-court-order">${escapeHTML(t("cw_upload_court_order"))}</button>
                <input type="file" id="cwCourtOrderFile" accept=".pdf,.doc,.docx" style="display:none">`;
    if(c.status !== "closed"){
      actions += `<button type="button" class="btn-secondary cw-action" id="cwCloseCase">${escapeHTML(t("cw_close_case"))}</button>`;
    }
  }
  if(state.role === "forensic"){
    actions += `<button type="button" class="btn-primary cw-action cw-upload-report">${escapeHTML(t("cw_upload_report"))}</button>
                <input type="file" id="cwReportFile" accept=".pdf,.doc,.docx" style="display:none">`;
  }

  const backKey = state.role === "io" ? "iod_back" : "cw_back_cases";
  return `
    <button type="button" class="btn-ghost iod-back" id="cwBack">${escapeHTML(t(backKey))}</button>
    <div class="panel iod-case">
      <div class="panel-head iod-case-head">
        <div>
          <span class="case-num">${escapeHTML(c.number)}</span>
          <h3>${escapeHTML(c.title)}</h3>
        </div>
        <div class="cw-head-right">
          ${actions}
          <span class="status-badge ${statusBadgeClass(c.status)}">${statusBadgeLabel(c.status)}</span>
        </div>
      </div>
      ${cwTabsHTML(c)}
      <div class="iod-tab-body${CW.tab === "lifecycle" ? " iod-tab-lifecycle" : ""}">${body}</div>
    </div>`;
}

/* ---------------- Document Details (incl. EXIF / metadata) ---------------- */
function cwDetailsHTML(d, c){
  const row = (k, v) => `<tr><td>${escapeHTML(t(k))}</td><td>${v}</td></tr>`;
  const mono = v => `<span class="cw-mono">${escapeHTML(v)}</span>`;
  const ex = d.exif || {};
  return `
    <div id="cwDetails" data-doc="${escapeHTML(d.id)}">
      <h3 class="font-head cw-dd-title">${escapeHTML(d.name)}</h3>
      <div class="cw-dd-badges">
        <span class="doc-type-badge">${escapeHTML(d.type)}</span>
        ${d.isReport ? `<span class="doc-type-badge cw-report-badge">${escapeHTML(t("cw_forensic_report"))}</span>` : ""}
        ${d.isCourtOrder ? `<span class="doc-type-badge cw-report-badge">${escapeHTML(t("cw_court_order"))}</span>` : ""}
        ${d.signature ? `<span class="doc-type-badge cw-sig-badge">${escapeHTML(t("cw_signed_badge"))}</span>` : ""}
      </div>
      <table class="exif-table cw-dd-table">
        ${row("cw_dd_case", escapeHTML(c ? c.number : "—"))}
        ${row("cw_dd_by", escapeHTML(d.uploader))}
        ${row("cw_dd_at", escapeHTML(d.time))}
        ${row("cw_dd_size", escapeHTML(cwSize(d.size)))}
        ${row("cw_dd_hash", mono(d.fullHash || d.hash))}
        ${row("cw_dd_status", cwStatusChip(d.status))}
        ${row("cw_dd_verified", escapeHTML(fmtDate(d.verifiedAt)))}
        ${row("cw_dd_tx", d.tx
          ? (d.explorerUrl
              ? `<a class="cw-mono cw-explorer-link" href="${escapeHTML(d.explorerUrl)}" target="_blank" rel="noopener noreferrer">${escapeHTML(d.tx)} ↗</a>`
              : mono(d.tx))
          : `<span class="lc-muted">${escapeHTML(t("cw_dd_tx_none"))}</span>`)}
        ${row("cw_dd_id", mono(d.id))}
      </table>
      <h4 class="cw-dd-sub">${escapeHTML(t("cw_meta_title"))}</h4>
      <table class="exif-table cw-dd-table" id="cwMeta">
        ${row("exif_device", escapeHTML(ex.device || "—"))}
        ${row("exif_gps", escapeHTML(ex.gps || "—"))}
        ${row("exif_imei", escapeHTML(ex.imei || "—"))}
        ${row("exif_created", escapeHTML(ex.created || "—"))}
      </table>
      <p class="iod-note">${escapeHTML(t("cw_meta_note"))}</p>
      <div class="cw-dd-actions">
        <button type="button" class="btn-primary" id="cwDlBtn">${escapeHTML(t("cw_download"))}</button>
        <button type="button" class="btn-secondary" id="cwVerifySigBtn">${escapeHTML(t("btn_verify_signature"))}</button>
      </div>
      <div class="sig-result" id="cwVerifySigResult"></div>
    </div>`;
}

function cwSigResultHTML(v){
  if(v.result === "no_signature"){
    return `<div class="sig-result-box sig-neutral">${escapeHTML(t("sig_none"))}</div>`;
  }
  const cls = v.result === "valid" ? "sig-ok" : "sig-bad";
  const label = v.result === "valid" ? t("sig_valid") : t("sig_invalid");
  const roleLabel = v.signer_role && ROLE_META[v.signer_role] ? t(ROLE_META[v.signer_role].labelKey) : (v.signer_role || "—");
  return `
    <div class="sig-result-box ${cls}">
      <div class="sig-result-verdict">${escapeHTML(label)}</div>
      <table class="exif-table cw-dd-table">
        <tr><td>${escapeHTML(t("sig_signer"))}</td><td>${escapeHTML(v.signer_name || "—")}</td></tr>
        <tr><td>${escapeHTML(t("sig_role"))}</td><td>${escapeHTML(roleLabel)}</td></tr>
        <tr><td>${escapeHTML(t("sig_signed_at"))}</td><td>${escapeHTML(fmtDate(v.signed_at))}</td></tr>
        <tr><td>${escapeHTML(t("sig_algorithm"))}</td><td><span class="cw-mono">${escapeHTML(v.algorithm || "—")}</span></td></tr>
      </table>
      <p class="iod-note">${escapeHTML(v.detail || "")}</p>
    </div>`;
}

function cwDetailsOpen(){
  const bd = document.getElementById("modalBackdrop");
  return bd && !bd.classList.contains("hidden");
}
function cwWireDetails(d){
  const btn = document.getElementById("cwDlBtn");
  if(btn) btn.addEventListener("click", () => cwDownload(d.id, d.name, btn));
  const sigBtn = document.getElementById("cwVerifySigBtn");
  if(sigBtn) sigBtn.addEventListener("click", () => cwVerifySignature(d.id, sigBtn));
}
async function cwVerifySignature(docId, btn){
  const box = document.getElementById("cwVerifySigResult");
  if(btn) btn.disabled = true;
  try{
    const result = await NV_API.signatureVerify(docId);
    if(box) box.innerHTML = cwSigResultHTML(result);
  }catch(err){
    toast(err.message, true);
    if(box) box.innerHTML = `<div class="sig-result-box sig-bad">${escapeHTML(err.message)}</div>`;
  }finally{ if(btn) btn.disabled = false; }
}
async function cwDetails(docId){
  const c = findCase(state.caseId);
  const d = c && findDoc(c, docId);
  if(!d) return;
  openModal(cwDetailsHTML(d, c), { wide: true });
  cwWireDetails(d);
  // Opening a document is a recorded access (GET /api/documents/{id} writes the 'view' audit event)
  // and returns the current blockchain anchoring status.
  try{
    const fresh = mapDoc(await NV_API.document(docId));
    Object.assign(d, fresh);
    const box = document.getElementById("cwDetails");
    if(cwDetailsOpen() && box && box.getAttribute("data-doc") === docId){
      openModal(cwDetailsHTML(d, c), { wide: true });
      cwWireDetails(d);
    }
  }catch(_){ /* keep the details we already have */ }
}
async function cwDownload(docId, name, btn){
  if(btn) btn.disabled = true;
  try{
    await NV_API.download(docId, name);
    toast(`${t("cw_download")}: ${name}`);
  }catch(err){ toast(err.message, true); }
  finally{ if(btn) btn.disabled = false; }
}

/* ---------------- actions ---------------- */
async function cwUploadEvidence(file){
  const c = cwOpenCase();
  if(!c) return;
  toast(t("iod_uploading"));
  try{
    const doc = await NV_API.upload(c.id, file);
    await loadLiveData();
    state.caseId = c.id;
    toast(`${t("hash_generated")}: ${doc.name}`);
    CW.tab = CW_MEDIA_TYPES.includes(doc.type) ? "evidence" : "documents";   // land on the tab it belongs to
    renderSection(state.section);
  }catch(err){ toast(err.message, true); }
}

async function cwUploadReport(file){
  const c = cwOpenCase();
  if(!c) return;
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if(!CW_REPORT_EXTENSIONS.includes(ext)){ toast(t("cw_report_types"), true); return; }
  toast(t("cw_report_uploading"));
  try{
    // The server computes the SHA-256 and records uploader + timestamp; nothing is supplied here.
    const doc = await NV_API.uploadForensicReport(c.id, file);
    await loadLiveData();
    state.caseId = c.id;
    CW.tab = "report";
    CW.justUploaded = doc.id;
    toast(`${t("cw_report_uploaded")}: ${doc.name}`);
    renderSection(state.section);
  }catch(err){ toast(err.message, true); }
}

async function cwVerify(){
  const c = cwOpenCase();
  const doc = c && findDoc(c, CW.docId);
  const btn = document.getElementById("cwVerifyBtn");
  const result = document.getElementById("cwVerifyResult");
  if(!doc || !btn || !result) return;
  btn.disabled = true;
  result.classList.add("visible");
  result.innerHTML = `<div class="label">${escapeHTML(t("verify_running"))}</div>`;
  try{
    const v = await NV_API.verify(doc.id);
    doc.status = v.status;
    doc.verifiedAt = v.checked_at || doc.verifiedAt;
    if(!result.isConnected) return;
    result.innerHTML = `
      <div class="label">${escapeHTML(doc.name)}</div>
      <div class="doc-status ${v.match ? "verified" : "tampered"} cw-verify-verdict"><span class="dot"></span>${escapeHTML(v.match ? t("verify_ok") : t("verify_bad"))}</div>
      <div class="label cw-verify-hash">${escapeHTML(t("cw_hash_upload"))}</div><div class="hash-val cw-mono">${escapeHTML(v.hash_at_upload)}</div>
      <div class="label cw-verify-hash">${escapeHTML(t("cw_hash_now"))}</div><div class="hash-val cw-mono${v.match ? "" : " iod-bad"}">${escapeHTML(v.hash_now)}</div>`;
    toast(`${doc.name}: ${v.match ? t("verify_ok") : t("verify_bad")}`, !v.match);
    // keep the list's status badges honest without losing the result panel
    document.querySelectorAll("#mainContent .doc-card.selectable").forEach(el => {
      const d = findDoc(c, el.getAttribute("data-doc"));
      const st = el.querySelector(".doc-status");
      if(d && st) st.outerHTML = cwStatusChip(d.status);
    });
  }catch(err){
    if(result.isConnected) result.innerHTML = `<div class="label">${escapeHTML(err.message)}</div>`;
    toast(err.message, true);
  }finally{ btn.disabled = false; }
}

// Court Presentation (judge) - a contextual action on the case, not a menu item.
async function cwPresent(){
  const c = cwOpenCase();
  if(!c) return;
  try{
    // Records the presentation (who / which case / when) in the audit trail and lifecycle.
    await NV_API.present(c.id);
  }catch(err){ toast(`${t("cw_present_failed")}: ${err.message}`, true); return; }
  const wmText = `${t("watermark_label")} ${state.user.toUpperCase()} · ${t(ROLE_META[state.role].labelKey).toUpperCase()}`;
  openModal(`
    <div class="presentation-view">
      <div class="clock" id="courtClock"></div>
      <div class="wm-overlay">${escapeHTML(wmText.replace(/(.{22})/g, "$1\n"))}</div>
      <div class="doc-mock">
        <strong>${escapeHTML(c.number)}</strong><br><br>
        ${escapeHTML(c.title)}<br><br>
        Evidence document rendered for court presentation. All viewer sessions are logged with timestamp and viewing officer.
      </div>
    </div>
  `);
  const clockEl = document.getElementById("courtClock");
  const tick = () => { clockEl.textContent = new Date().toLocaleString(); };
  tick();
  const iv = setInterval(() => {
    if(!document.getElementById("courtClock")){ clearInterval(iv); return; }
    tick();
  }, 1000);
  toast(t("cw_present") + " ✓");
}

async function cwUploadCourtOrder(file){
  const c = cwOpenCase();
  if(!c) return;
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if(!CW_REPORT_EXTENSIONS.includes(ext)){ toast(t("cw_court_order_types"), true); return; }
  toast(t("cw_court_order_uploading"));
  try{
    // The server computes the SHA-256, records the judge + timestamp, and
    // digitally signs the hash with the judge's own key (non-repudiation).
    const doc = await NV_API.uploadCourtOrder(c.id, file);
    await loadLiveData();
    state.caseId = c.id;
    CW.tab = "documents";
    toast(`${t("cw_court_order_uploaded")}: ${doc.name}`);
    renderSection(state.section);
  }catch(err){ toast(err.message, true); }
}

// Case closure (judge) - digitally signed, non-repudiable action.
async function cwCloseCase(){
  const c = cwOpenCase();
  if(!c) return;
  if(c.status === "closed"){ toast(t("cw_close_case_already"), true); return; }
  if(!confirm(t("cw_close_case_confirm"))) return;
  try{
    await NV_API.closeCase(c.id);
    await loadLiveData();
    state.caseId = c.id;
    toast(t("cw_close_case_done"));
    renderSection(state.section);
  }catch(err){ toast(err.message, true); }
}

/* ---------------- wiring (cards + opened case) ---------------- */
function cwWire(){
  // case cards -> open
  document.querySelectorAll("#mainContent .iod-card").forEach(el => {
    const open = () => cwOpen(el.getAttribute("data-open"), "overview");
    el.addEventListener("click", open);
    el.addEventListener("keydown", e => { if(e.key === "Enter" || e.key === " "){ e.preventDefault(); open(); } });
  });
  // forensic overview rows -> jump straight to the right tab of that case
  document.querySelectorAll("#mainContent .cw-jump").forEach(el => {
    const go = () => cwOpen(el.getAttribute("data-case"), el.getAttribute("data-tab"), el.getAttribute("data-doc"));
    el.addEventListener("click", go);
    el.addEventListener("keydown", e => { if(e.key === "Enter" || e.key === " "){ e.preventDefault(); go(); } });
  });

  const c = cwOpenCase();
  if(!c) return;
  state.caseId = c.id;

  const back = document.getElementById("cwBack");
  if(back) back.addEventListener("click", cwClose);
  document.querySelectorAll("#mainContent .iod-tab").forEach(el => {
    el.addEventListener("click", () => { CW.tab = el.getAttribute("data-tab"); CW.justUploaded = null; renderSection(state.section); });
  });

  // Document Details / Download
  document.querySelectorAll("#mainContent .preview-doc").forEach(btn => {
    btn.addEventListener("click", e => { e.stopPropagation(); cwDetails(btn.getAttribute("data-doc")); });
  });
  document.querySelectorAll("#mainContent .dl-doc").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      const d = findDoc(c, btn.getAttribute("data-doc"));
      if(d) cwDownload(d.id, d.name, btn);
    });
  });

  // IO: upload a document / evidence file
  const upBtn = document.querySelector("#mainContent .iod-upload");
  const fileInput = document.getElementById("cwFile");
  if(upBtn && fileInput){
    upBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => { if(fileInput.files[0]) cwUploadEvidence(fileInput.files[0]); });
  }

  // Forensic: + Upload Forensic Report (header button, and the empty state on the report tab)
  const reportInput = document.getElementById("cwReportFile");
  document.querySelectorAll("#mainContent .cw-upload-report").forEach(btn => {
    btn.addEventListener("click", () => { if(reportInput) reportInput.click(); });
  });
  if(reportInput){
    reportInput.addEventListener("change", () => { if(reportInput.files[0]) cwUploadReport(reportInput.files[0]); });
  }

  // Forensic: Verify tab
  if(CW.tab === "verify"){
    document.querySelectorAll("#mainContent .doc-card.selectable").forEach(el => {
      el.addEventListener("click", () => { CW.docId = el.getAttribute("data-doc"); renderSection(state.section); });
    });
    const vb = document.getElementById("cwVerifyBtn");
    if(vb) vb.addEventListener("click", cwVerify);
  }

  // Judge: Court Presentation
  const pres = document.getElementById("cwPresent");
  if(pres) pres.addEventListener("click", cwPresent);

  // Judge: + Upload Court Order
  const courtOrderInput = document.getElementById("cwCourtOrderFile");
  document.querySelectorAll("#mainContent .cw-upload-court-order").forEach(btn => {
    btn.addEventListener("click", () => { if(courtOrderInput) courtOrderInput.click(); });
  });
  if(courtOrderInput){
    courtOrderInput.addEventListener("change", () => { if(courtOrderInput.files[0]) cwUploadCourtOrder(courtOrderInput.files[0]); });
  }

  // Judge: Close Case
  const closeBtn = document.getElementById("cwCloseCase");
  if(closeBtn) closeBtn.addEventListener("click", cwCloseCase);

  // tab content that loads data
  if(CW.tab === "lifecycle" && typeof lifecycleMount === "function") lifecycleMount();
  if(CW.tab === "overview") cwLoadOverviewActivity();
}

/* ---------------- hook into the existing section registry ---------------- */
// Judge + forensic Overview (IO's is in io-dashboard.js, admin's stays in dashboard.js).
const CW_BASE_OVERVIEW = SECTIONS.overview;
const CW_BASE_OVERVIEW_HANDLER = HANDLERS.overview;

SECTIONS.overview = function(){
  if(state.role === "judge"){
    const c = cwOpenCase();
    if(!c) CW.openId = null;
    return c ? cwCaseHTML(c) : overviewKpisHTML() + `<h3 class="font-head cw-list-h">${escapeHTML(t("nav_cases"))}</h3>` + cwCardGridHTML();
  }
  if(state.role === "forensic") return cwForensicOverviewHTML();
  return CW_BASE_OVERVIEW();
};
HANDLERS.overview = function(){
  if(state.role === "judge" || state.role === "forensic") return cwWire();
  return CW_BASE_OVERVIEW_HANDLER();
};

// Forensic "Cases": the case cards, then the opened case.
SECTIONS.cases = function(){
  const c = cwOpenCase();
  if(!c) CW.openId = null;
  return c ? cwCaseHTML(c) : `<div class="iod-head"><div><h2 class="font-head iod-h">${escapeHTML(t("nav_cases"))}</h2></div></div>` + cwCardGridHTML();
};
HANDLERS.cases = cwWire;
