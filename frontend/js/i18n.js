/* =========================================================
   NyayVault — translations (English / Hindi)
   Applied via data-i18n="key" on any element's text content,
   and data-i18n-ph="key" for input placeholders.
   ========================================================= */

const I18N = {
  en: {
    brand_name: "NyayVault",
    brand_tagline: "DIGITAL EVIDENCE MANAGEMENT SYSTEM",
    identity_heading: "Chain of custody, held to the standard of the court.",
    identity_body: "A secure record for every file an investigation touches — hashed on upload, verified on access, and logged from first upload to courtroom review.",
    trust_hash: "SHA-256 verified",
    trust_audit: "Full audit trail",
    trust_rbac: "Role-based access",
    trust_scope: "State / district / unit jurisdiction scoping",
    identity_footer_left: "For authorised personnel only",
    identity_footer_right: "v1.0",

    login_eyebrow: "SECURE SIGN IN",
    login_heading: "Sign in to your account",
    login_lede: "Enter your credentials to access your case dashboard.",
    label_username: "Username or badge ID",
    ph_username: "e.g. IO-2291 or officer.sharma",
    label_password: "Password",
    label_role: "Sign in as",
    role_io: "Investigating Officer",
    role_forensic: "Forensic Specialist",
    role_judge: "Judge / Court",
    role_admin: "Administrator",
    role_hint: "Your dashboard and permissions are set according to the role selected here.",
    remember_me: "Keep me signed in",
    forgot_password: "Forgot password?",
    btn_signin: "Sign in securely",
    error_required: "Please enter a username and password to continue.",
    footer_note: "This system logs all access attempts, successful or not, with IP address and timestamp, in line with departmental evidence-handling policy.",
    demo_hint: "<b>Demo build —</b> any username and password will work. Choose a role above to preview that dashboard.",

    theme_light: "Light",
    theme_dark: "Dark",

    /* ---------- dashboard ---------- */
    nav_overview: "Overview",
    nav_cases: "Cases",
    nav_upload: "Smart Upload & Hash Engine",
    nav_redaction: "AI Redaction Studio",
    nav_audio: "Audio Transcriber",
    nav_search: "Search",
    nav_verify: "Integrity Verifier",
    nav_exif: "EXIF Metadata Inspector",
    nav_report: "Forensic Report Generator",
    nav_docket: "Case Docket",
    nav_timeline: "Chain of Custody Timeline",
    nav_courtroom: "Watermarked Courtroom View",
    nav_users: "Users",
    nav_auditlogs: "Audit Logs",

    sidebar_primary_work: "PRIMARY WORK",
    work_io: "Case filing, evidence upload, and privacy protection.",
    work_forensic: "Technical testing and file authenticity checks.",
    work_judge: "Evidence review and legal proceedings.",
    work_admin: "Security and access control.",

    logout: "Sign out",
    search_ph: "Search cases, evidence, hashes…",

    case_active: "ACTIVE",
    case_in_court: "IN COURT",
    case_closed: "CLOSED",
    docs_count: "documents",

    kpi_active_cases: "Active cases",
    kpi_pending_verify: "Pending verification",
    kpi_evidence_items: "Evidence items",
    kpi_audit_events: "Audit events (24h)",

    section_case_creation: "Case Creation",
    section_case_creation_desc: "Register a new case with FIR number, crime type, date and location.",
    btn_new_case: "New case",
    section_upload: "Smart Upload & Hash Engine",
    section_upload_desc: "Drag and drop a file — a SHA-256 hash is generated and shown on screen.",
    btn_upload: "Upload evidence",
    drop_hint: "Drag file here, or click to browse",
    hash_generated: "Hash generated",

    section_redaction: "AI Redaction Studio",
    redaction_pdf: "PDF Redaction",
    redaction_pdf_desc: "Aadhaar numbers, phone numbers and names are covered with automated black bars.",
    redaction_cctv: "CCTV Video Redaction",
    redaction_cctv_desc: "Faces and vehicle number plates are blurred automatically.",
    btn_run_redaction: "Run redaction",

    section_audio: "Audio Transcriber",
    section_audio_desc: "Call recordings are converted to text transcripts with timestamps.",
    btn_transcribe: "Transcribe recording",

    section_search: "Search",
    section_search_desc: "Find cases and evidence by FIR number, case title, file name or SHA-256 hash.",
    search_case_ph: "Search cases, file names, hashes…",

    section_verify: "Integrity Verifier",
    section_verify_desc: "One-click test that matches the original hash against the current hash and reports VERIFIED or TAMPERED.",
    btn_verify: "Verify integrity",
    verify_running: "Comparing hashes…",
    verify_ok: "VERIFIED",
    verify_bad: "TAMPERED",
    verify_pending: "PENDING",

    section_exif: "EXIF Metadata Inspector",
    section_exif_desc: "Hidden file data — device name, GPS coordinates, IMEI and creation time.",
    exif_device: "Device",
    exif_gps: "GPS coordinates",
    exif_imei: "IMEI",
    exif_created: "File created",

    section_report: "Forensic Report Generator",
    section_report_desc: "Export an automated PDF report for submission to the court.",
    btn_generate_report: "Generate report",

    section_docket: "Case Docket",
    section_docket_desc: "A read-only view of all documents and videos in the secure viewer.",

    section_timeline: "Chain of Custody Timeline",
    section_timeline_desc: "A visual record of when a file was uploaded, which officer viewed it, and when it was modified.",
    action_upload: "UPLOAD",
    action_view: "VIEW",
    action_verify: "VERIFY",
    action_download: "DOWNLOAD",
    action_tamper: "TAMPER",
    action_login: "LOGIN",
    action_login_failed: "LOGIN FAILED",
    action_logout: "LOGOUT",
    action_present: "PRESENT",
    action_approve: "APPROVE",
    action_revoke: "REVOKE",
    action_redact: "REDACT",
    action_transcribe: "TRANSCRIBE",
    action_report: "REPORT",
    action_search: "SEARCH",
    action_case_create: "CASE OPENED",
    action_user_create: "USER CREATED",
    action_blockchain_anchor: "ANCHORED",
    action_blockchain_anchor_failed: "ANCHOR FAILED",
    action_forensic_report_upload: "REPORT UPLOADED",
    timeline_loading: "Loading timeline…",
    timeline_empty: "No activity has been recorded for this case yet.",

    section_courtroom: "Watermarked Courtroom View",
    section_courtroom_desc: "Full-screen presentation view with a live timestamp and watermark.",
    btn_present: "Open presentation view",
    watermark_label: "CONFIDENTIAL · ACCESSED BY",

    section_users: "User Permission Control",
    section_users_desc: "Add new officers, assign badges, and approve or revoke access.",
    btn_add_user: "Add officer",
    th_name: "Name",
    th_role: "Role",
    th_badge: "Badge ID",
    th_status: "Status",
    th_action: "Action",
    status_approved: "Approved",
    status_pending: "Pending",
    btn_revoke: "Revoke",
    btn_approve: "Approve",

    section_auditlogs: "Global Audit Logs",
    section_auditlogs_desc: "A live security stream of the whole system — which IP address took which action.",
    th_time: "Time",
    th_user: "User",
    th_ip: "IP address",
    th_event: "Event",

    empty_select_case: "Select a case from the left to see its evidence vault.",
  },

  hi: {
    brand_name: "न्यायVault",
    brand_tagline: "डिजिटल साक्ष्य प्रबंधन प्रणाली",
    identity_heading: "साक्ष्य की श्रृंखला, अदालत के मानक पर सुरक्षित।",
    identity_body: "जाँच से जुड़ी हर फ़ाइल का सुरक्षित रिकॉर्ड — अपलोड पर हैश, एक्सेस पर सत्यापन, और पहले अपलोड से लेकर अदालत की समीक्षा तक पूरा लॉग।",
    trust_hash: "SHA-256 सत्यापित",
    trust_audit: "पूर्ण ऑडिट ट्रेल",
    trust_rbac: "भूमिका-आधारित अभिगम",
    trust_scope: "राज्य / जिला / यूनिट क्षेत्राधिकार सीमांकन",
    identity_footer_left: "केवल अधिकृत कर्मियों के लिए",
    identity_footer_right: "संस्करण 1.0",

    login_eyebrow: "सुरक्षित लॉगिन",
    login_heading: "अपने खाते में साइन इन करें",
    login_lede: "अपने केस डैशबोर्ड तक पहुँचने के लिए विवरण दर्ज करें।",
    label_username: "उपयोगकर्ता नाम या बैज आईडी",
    ph_username: "जैसे IO-2291 या officer.sharma",
    label_password: "पासवर्ड",
    label_role: "इस रूप में साइन इन करें",
    role_io: "जाँच अधिकारी",
    role_forensic: "फोरेंसिक विशेषज्ञ",
    role_judge: "न्यायाधीश / न्यायालय",
    role_admin: "प्रशासक",
    role_hint: "आपका डैशबोर्ड और अनुमतियाँ यहाँ चुनी गई भूमिका के अनुसार तय होती हैं।",
    remember_me: "मुझे साइन इन रखें",
    forgot_password: "पासवर्ड भूल गए?",
    btn_signin: "सुरक्षित साइन इन करें",
    error_required: "आगे बढ़ने के लिए कृपया उपयोगकर्ता नाम और पासवर्ड दर्ज करें।",
    footer_note: "यह प्रणाली विभागीय साक्ष्य-प्रबंधन नीति के अनुसार, सफल या असफल, सभी एक्सेस प्रयासों को IP पते और समय-मुहर सहित दर्ज करती है।",
    demo_hint: "<b>डेमो बिल्ड —</b> कोई भी उपयोगकर्ता नाम और पासवर्ड काम करेगा। उस डैशबोर्ड को देखने के लिए ऊपर एक भूमिका चुनें।",

    theme_light: "लाइट",
    theme_dark: "डार्क",

    nav_overview: "अवलोकन",
    nav_cases: "केस",
    nav_upload: "स्मार्ट अपलोड और हैश इंजन",
    nav_redaction: "एआई रिडैक्शन स्टूडियो",
    nav_audio: "ऑडियो ट्रांसक्राइबर",
    nav_search: "खोज",
    nav_verify: "इंटीग्रिटी वेरिफायर",
    nav_exif: "EXIF मेटाडेटा इंस्पेक्टर",
    nav_report: "फोरेंसिक रिपोर्ट जनरेटर",
    nav_docket: "केस डॉकेट",
    nav_timeline: "चेन ऑफ़ कस्टडी टाइमलाइन",
    nav_courtroom: "वॉटरमार्क कोर्टरूम व्यू",
    nav_users: "उपयोगकर्ता",
    nav_auditlogs: "ऑडिट लॉग",

    sidebar_primary_work: "मुख्य कार्य",
    work_io: "केस फाइलिंग, साक्ष्य अपलोड और गोपनीयता सुरक्षा।",
    work_forensic: "तकनीकी परीक्षण और फ़ाइल प्रामाणिकता जाँच।",
    work_judge: "साक्ष्य समीक्षा और कानूनी कार्यवाही।",
    work_admin: "सुरक्षा और अभिगम नियंत्रण।",

    logout: "साइन आउट",
    search_ph: "केस, साक्ष्य, हैश खोजें…",

    case_active: "सक्रिय",
    case_in_court: "न्यायालय में",
    case_closed: "बंद",
    docs_count: "दस्तावेज़",

    kpi_active_cases: "सक्रिय केस",
    kpi_pending_verify: "सत्यापन लंबित",
    kpi_evidence_items: "साक्ष्य आइटम",
    kpi_audit_events: "ऑडिट घटनाएँ (24घं)",

    section_case_creation: "केस निर्माण",
    section_case_creation_desc: "FIR नंबर, अपराध प्रकार, तिथि और स्थान के साथ नया केस दर्ज करें।",
    btn_new_case: "नया केस",
    section_upload: "स्मार्ट अपलोड और हैश इंजन",
    section_upload_desc: "फ़ाइल को यहाँ खींचें और छोड़ें — स्क्रीन पर SHA-256 हैश बनेगा और दिखेगा।",
    btn_upload: "साक्ष्य अपलोड करें",
    drop_hint: "फ़ाइल यहाँ खींचें, या ब्राउज़ करने के लिए क्लिक करें",
    hash_generated: "हैश जनरेट हुआ",

    section_redaction: "एआई रिडैक्शन स्टूडियो",
    redaction_pdf: "PDF रिडैक्शन",
    redaction_pdf_desc: "आधार नंबर, फ़ोन नंबर और नाम स्वचालित काली पट्टियों से ढक दिए जाते हैं।",
    redaction_cctv: "CCTV वीडियो रिडैक्शन",
    redaction_cctv_desc: "चेहरे और वाहन नंबर प्लेट स्वचालित रूप से धुंधले किए जाते हैं।",
    btn_run_redaction: "रिडैक्शन चलाएँ",

    section_audio: "ऑडियो ट्रांसक्राइबर",
    section_audio_desc: "कॉल रिकॉर्डिंग को टाइमस्टैम्प सहित टेक्स्ट ट्रांसक्रिप्ट में बदला जाता है।",
    btn_transcribe: "रिकॉर्डिंग ट्रांसक्राइब करें",

    section_search: "खोज",
    section_search_desc: "FIR नंबर, केस शीर्षक, फ़ाइल नाम या SHA-256 हैश से केस और साक्ष्य खोजें।",
    search_case_ph: "केस, फ़ाइल नाम, हैश खोजें…",

    section_verify: "इंटीग्रिटी वेरिफायर",
    section_verify_desc: "एक-क्लिक परीक्षण जो मूल हैश को वर्तमान हैश से मिलाकर VERIFIED या TAMPERED बताता है।",
    btn_verify: "इंटीग्रिटी सत्यापित करें",
    verify_running: "हैश की तुलना हो रही है…",
    verify_ok: "सत्यापित",
    verify_bad: "छेड़छाड़",
    verify_pending: "लंबित",

    section_exif: "EXIF मेटाडेटा इंस्पेक्टर",
    section_exif_desc: "छिपा हुआ फ़ाइल डेटा — डिवाइस नाम, GPS निर्देशांक, IMEI और निर्माण समय।",
    exif_device: "डिवाइस",
    exif_gps: "GPS निर्देशांक",
    exif_imei: "IMEI",
    exif_created: "फ़ाइल बनाई गई",

    section_report: "फोरेंसिक रिपोर्ट जनरेटर",
    section_report_desc: "न्यायालय में प्रस्तुति के लिए स्वचालित PDF रिपोर्ट निर्यात करें।",
    btn_generate_report: "रिपोर्ट बनाएँ",

    section_docket: "केस डॉकेट",
    section_docket_desc: "सुरक्षित व्यूअर में सभी दस्तावेज़ों और वीडियो का केवल-पठन दृश्य।",

    section_timeline: "चेन ऑफ़ कस्टडी टाइमलाइन",
    section_timeline_desc: "फ़ाइल कब अपलोड हुई, किस अधिकारी ने देखी, और कब बदली गई — इसका दृश्य रिकॉर्ड।",
    action_upload: "अपलोड",
    action_view: "देखा",
    action_verify: "सत्यापित",
    action_download: "डाउनलोड",
    action_tamper: "छेड़छाड़",
    action_login: "लॉगिन",
    action_login_failed: "लॉगिन विफल",
    action_logout: "लॉगआउट",
    action_present: "प्रस्तुत",
    action_approve: "स्वीकृत",
    action_revoke: "रद्द",
    action_redact: "रिडैक्ट",
    action_transcribe: "ट्रांसक्राइब",
    action_report: "रिपोर्ट",
    action_search: "खोज",
    action_case_create: "केस खोला गया",
    action_user_create: "उपयोगकर्ता बनाया गया",
    action_blockchain_anchor: "एंकर किया गया",
    action_blockchain_anchor_failed: "एंकरिंग विफल",
    action_forensic_report_upload: "रिपोर्ट अपलोड",
    timeline_loading: "टाइमलाइन लोड हो रही है…",
    timeline_empty: "इस केस के लिए अभी तक कोई गतिविधि दर्ज नहीं हुई है।",

    section_courtroom: "वॉटरमार्क कोर्टरूम व्यू",
    section_courtroom_desc: "लाइव टाइमस्टैम्प और वॉटरमार्क के साथ फ़ुल-स्क्रीन प्रस्तुति दृश्य।",
    btn_present: "प्रस्तुति दृश्य खोलें",
    watermark_label: "गोपनीय · द्वारा एक्सेस किया गया",

    section_users: "उपयोगकर्ता अनुमति नियंत्रण",
    section_users_desc: "नए अधिकारी जोड़ें, बैज असाइन करें, और अभिगम स्वीकृत या निरस्त करें।",
    btn_add_user: "अधिकारी जोड़ें",
    th_name: "नाम",
    th_role: "भूमिका",
    th_badge: "बैज आईडी",
    th_status: "स्थिति",
    th_action: "कार्रवाई",
    status_approved: "स्वीकृत",
    status_pending: "लंबित",
    btn_revoke: "निरस्त करें",
    btn_approve: "स्वीकृत करें",

    section_auditlogs: "वैश्विक ऑडिट लॉग",
    section_auditlogs_desc: "पूरी प्रणाली की लाइव सुरक्षा स्ट्रीम — किस IP पते ने कौन-सी कार्रवाई की।",
    th_time: "समय",
    th_user: "उपयोगकर्ता",
    th_ip: "IP पता",
    th_event: "घटना",

    empty_select_case: "साक्ष्य वॉल्ट देखने के लिए बाईं ओर से एक केस चुनें।",
  }
};

function applyI18n(lang){
  document.documentElement.setAttribute("lang", lang);
  const dict = I18N[lang] || I18N.en;
  document.querySelectorAll("[data-i18n]").forEach(el=>{
    const key = el.getAttribute("data-i18n");
    if(dict[key] !== undefined) el.innerHTML = dict[key];
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(el=>{
    const key = el.getAttribute("data-i18n-ph");
    if(dict[key] !== undefined) el.setAttribute("placeholder", dict[key]);
  });
  document.querySelectorAll(".lang-switch button").forEach(btn=>{
    btn.classList.toggle("active", btn.getAttribute("data-lang") === lang);
  });
  localStorage.setItem("nv_lang", lang);
}

function initI18n(){
  const saved = localStorage.getItem("nv_lang") || "en";
  applyI18n(saved);
  document.querySelectorAll(".lang-switch button").forEach(btn=>{
    btn.addEventListener("click", ()=> applyI18n(btn.getAttribute("data-lang")));
  });
}

function t(key){
  const lang = localStorage.getItem("nv_lang") || "en";
  return (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
}

document.addEventListener("DOMContentLoaded", initI18n);
