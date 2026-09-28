const NV_API = {
  token(){ return localStorage.getItem("nv_token"); },
  headers(extra={}){
    const h = {...extra};
    const token = this.token();
    if(token) h.Authorization = `Bearer ${token}`;
    return h;
  },
  async request(path, options={}){
    const raw = options.raw; delete options.raw;      // raw: hand back the Response untouched (file downloads)
    options.headers = this.headers(options.headers || {});
    const res = await fetch(path, options);
    if(res.status === 401){
      localStorage.removeItem("nv_token");
      localStorage.removeItem("nv_role");
      localStorage.removeItem("nv_user");
      if(!location.pathname.endsWith("login.html") && location.pathname !== "/") location.href = "/login.html";
    }
    if(!res.ok){
      let message = `Request failed (${res.status})`;
      try {
        const body = await res.json();
        const d = body.detail;
        // FastAPI validation errors (422) arrive as a list of {msg, ...}.
        if(Array.isArray(d)) message = d.map(e => String((e && e.msg) || e).replace(/^Value error,\s*/i, "")).join(" ") || message;
        else if(d) message = d;
      } catch(_) {}
      throw new Error(message);
    }
    if(raw) return res;
    const type = res.headers.get("content-type") || "";
    return type.includes("application/json") ? res.json() : res;
  },
  login(username,password,role){
    return this.request("/api/auth/login", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({username,password,role})});
  },
  me(){ return this.request("/api/auth/me"); },
  cases(){ return this.request("/api/cases"); },
  createCase(payload){ return this.request("/api/cases", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)}); },
  caseDetail(id){ return this.request(`/api/cases/${encodeURIComponent(id)}`); },
  overview(){ return this.request("/api/cases/overview/summary"); },
  users(){ return this.request("/api/users"); },
  lifecycle(caseId, docId){ return this.request(`/api/cases/${encodeURIComponent(caseId)}/lifecycle${docId ? `?document_id=${encodeURIComponent(docId)}` : ""}`); },
  audit(caseId){ return this.request(`/api/audit-logs${caseId ? `?case_id=${encodeURIComponent(caseId)}` : ""}`); },
  search(q){ return this.request(`/api/search?q=${encodeURIComponent(q)}`); },
  document(id){ return this.request(`/api/documents/${encodeURIComponent(id)}`); },
  verify(id){ return this.request(`/api/documents/${encodeURIComponent(id)}/verify`, {method:"POST"}); },
  signatureVerify(id){ return this.request(`/api/documents/${encodeURIComponent(id)}/signature/verify`); },
  approveUser(id){ return this.request(`/api/users/${encodeURIComponent(id)}/approve`, {method:"POST"}); },
  revokeUser(id){ return this.request(`/api/users/${encodeURIComponent(id)}/revoke`, {method:"POST"}); },
  present(id){ return this.request(`/api/cases/${encodeURIComponent(id)}/present`, {method:"POST"}); },
  closeCase(id){ return this.request(`/api/cases/${encodeURIComponent(id)}/close`, {method:"POST"}); },
  async upload(caseId,file){ const fd=new FormData(); fd.append("file",file); return this.request(`/api/cases/${encodeURIComponent(caseId)}/documents`, {method:"POST",body:fd}); },
  async uploadForensicReport(caseId,file){ const fd=new FormData(); fd.append("file",file); return this.request(`/api/cases/${encodeURIComponent(caseId)}/forensic-reports`, {method:"POST",body:fd}); },
  async uploadCourtOrder(caseId,file){ const fd=new FormData(); fd.append("file",file); return this.request(`/api/cases/${encodeURIComponent(caseId)}/court-orders`, {method:"POST",body:fd}); },
  // Authenticated download (a plain <a href> cannot send the bearer token).
  async download(id, filename){
    const res = await this.request(`/api/documents/${encodeURIComponent(id)}/download`, {raw:true});
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename || "download";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 10000);
  },
  async logout(){ try { await this.request("/api/auth/logout", {method:"POST"}); } catch(_) {} },
};
