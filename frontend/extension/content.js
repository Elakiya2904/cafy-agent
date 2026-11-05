/* Cafy Application Assistant – content script.
 *
 * Responsibilities (pipeline_2.md §4): detect the form, identify fields/labels/required/
 * dropdowns/file inputs, talk to the Cafy backend, fill fields, upload the stored résumé
 * (only with permission) and report what actually happened.
 *
 * It NEVER submits on its own: the submit button is only clicked after the candidate has
 * approved the application in Cafy AND clicks "Submit application" in this panel.
 * It does not try to solve or bypass CAPTCHAs.
 */
(function (root) {
  "use strict";

  const ATS = [
    ["greenhouse", /greenhouse\.io$/], ["lever", /lever\.co$/], ["ashby", /ashbyhq\.com$/],
    ["workday", /myworkdayjobs\.com$|workday\.com$/], ["workable", /workable\.com$/],
    ["oracle", /oraclecloud\.com$/], ["breezy", /breezy\.hr$/], ["pinpoint", /pinpointhq\.com$/],
  ];
  const PANEL_ID = "cafy-assistant-panel";

  function detectAts(hostname) {
    const hit = ATS.find(([, rx]) => rx.test(hostname || ""));
    return hit ? hit[0] : "generic";
  }

  const cssEsc = (v) => (root.CSS && root.CSS.escape ? root.CSS.escape(v) : String(v).replace(/["\\]/g, "\\$&"));
  const clean = (t) => (t || "").replace(/\s+/g, " ").replace(/\(?\brequired\b\)?/gi, "").replace(/\*/g, "").trim();

  function isVisible(el) {
    if (!el || el.closest("#" + PANEL_ID)) return false;
    if (el.type === "hidden") return false;
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    // jsdom has no layout engine, so only enforce the layout check in real browsers.
    const inJsdom = /jsdom/i.test(root.navigator?.userAgent || "");
    return inJsdom || el.getClientRects().length > 0;
  }

  function labelText(el) {
    const doc = el.ownerDocument;
    const ids = (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean);
    const fromIds = ids.map((id) => doc.getElementById(id)?.textContent || "").join(" ");
    if (clean(fromIds)) return clean(fromIds);
    if (el.id) {
      const l = doc.querySelector(`label[for="${cssEsc(el.id)}"]`);
      if (l && clean(l.textContent)) return clean(l.textContent);
    }
    const wrap = el.closest("label");
    if (wrap) {
      const copy = wrap.cloneNode(true);
      copy.querySelectorAll("input,select,textarea").forEach((n) => n.remove());
      if (clean(copy.textContent)) return clean(copy.textContent);
    }
    if (el.getAttribute("aria-label")) return clean(el.getAttribute("aria-label"));
    const group = el.closest("fieldset");
    if (group?.querySelector("legend") && (el.type === "radio" || el.type === "checkbox")) return clean(group.querySelector("legend").textContent);
    const container = el.closest("[class*='field'], [class*='question'], [class*='form-group'], [data-field], li, .row");
    const near = container?.querySelector("label, [class*='label'], legend");
    if (near && clean(near.textContent)) return clean(near.textContent);
    return clean(el.placeholder || el.name || el.id || "");
  }

  /** A radio group is described by its legend/group label, not by the first option's own label. */
  function groupLabel(el) {
    const legend = el.closest("fieldset")?.querySelector("legend");
    if (legend && clean(legend.textContent)) return clean(legend.textContent);
    const grp = el.closest("[role=radiogroup]");
    if (grp) {
      const ids = (grp.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean);
      const t = clean(ids.map((id) => el.ownerDocument.getElementById(id)?.textContent || "").join(" ")) || clean(grp.getAttribute("aria-label"));
      if (t) return t;
    }
    return labelText(el);
  }

  function isRequired(el) {
    if (el.required || el.getAttribute("aria-required") === "true") return true;
    const doc = el.ownerDocument;
    const l = (el.id && doc.querySelector(`label[for="${cssEsc(el.id)}"]`)) || el.closest("label");
    return !!(l && /\*|\brequired\b/i.test(l.textContent));
  }

  /** Find the fillable form on the page and describe every input. Returns {fields, elements}. */
  function collectFields(doc) {
    const scope = [...doc.forms].sort((a, b) => b.elements.length - a.elements.length)[0] || doc.body;
    const nodes = [...scope.querySelectorAll("input, textarea, select")];
    const fields = [];
    const elements = {};
    const seenGroups = new Set();
    const taken = new Set();
    const uniqueKey = (base) => {
      let k = base || "field", n = 1;
      while (taken.has(k)) k = `${base || "field"}-${++n}`;
      taken.add(k);
      return k;
    };
    nodes.forEach((el) => {
      const type = el.tagName === "SELECT" ? "select" : el.tagName === "TEXTAREA" ? "textarea" : (el.type || "text").toLowerCase();
      if (["hidden", "submit", "button", "image", "reset", "password", "search"].includes(type)) return;
      if (!isVisible(el) && type !== "file") return; // file inputs are often visually hidden behind a button
      if (type === "radio") {
        const gid = el.name || el.id;
        if (seenGroups.has(gid)) return;
        seenGroups.add(gid);
        const group = [...scope.querySelectorAll(`input[type=radio]`)].filter((r) => r.name === el.name);
        const key = uniqueKey(el.name || el.id);
        const options = group.map((r) => labelText(r) || r.value);
        fields.push({ key, name: el.name, id: el.id, label: groupLabel(el), type: "radio", required: group.some(isRequired), options, autocomplete: el.autocomplete || "" });
        elements[key] = group;
        return;
      }
      const key = uniqueKey(el.name || el.id || `${type}-${fields.length}`);
      const field = { key, name: el.name || "", id: el.id || "", label: labelText(el), type, required: isRequired(el),
                      placeholder: el.placeholder || "", autocomplete: el.getAttribute("autocomplete") || "" };
      if (type === "select") field.options = [...el.options].filter((o) => o.value !== "" && !/^(select|choose|please)/i.test(o.text.trim())).map((o) => clean(o.text));
      fields.push(field);
      elements[key] = el;
    });
    return { fields, elements };
  }

  function setNative(el, value) {
    const proto = el.tagName === "TEXTAREA" ? root.HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? root.HTMLSelectElement.prototype : root.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    ["input", "change", "blur"].forEach((t) => el.dispatchEvent(new root.Event(t, { bubbles: true })));
  }

  /** Fill one field. Returns true when something was written. Never overwrites text the user typed. */
  function fillField(target, field, value) {
    if (value == null || value === "") return false;
    if (field.type === "radio") {
      const idx = (field.options || []).findIndex((o) => o.toLowerCase() === String(value).toLowerCase());
      if (idx < 0 || target.some((r) => r.checked)) return false;
      target[idx].click();
      return true;
    }
    if (field.type === "checkbox" || field.type === "file") return false;
    if (field.type === "select") {
      const opt = [...target.options].find((o) => clean(o.text).toLowerCase() === String(value).toLowerCase() || o.value === value);
      if (!opt || (target.value && target.value !== "")) return false;
      setNative(target, opt.value);
      return true;
    }
    if (target.value && target.value.trim() !== "") return false;
    setNative(target, String(value));
    return true;
  }

  async function attachFile(input, base64, filename, contentType) {
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const dt = new root.DataTransfer();
    dt.items.add(new root.File([bytes], filename, { type: contentType || "application/pdf" }));
    input.files = dt.files;
    input.dispatchEvent(new root.Event("input", { bubbles: true }));
    input.dispatchEvent(new root.Event("change", { bubbles: true }));
    return input.files.length === 1 && input.files[0].name === filename;
  }

  function detectCaptcha(doc) {
    return !!doc.querySelector("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='turnstile'], .g-recaptcha, .h-captcha, [data-sitekey], .cf-turnstile");
  }

  function findSubmitButton(doc) {
    const form = [...doc.forms].sort((a, b) => b.elements.length - a.elements.length)[0] || doc;
    const btns = [...form.querySelectorAll("button, input[type=submit], [role=button]")].filter((b) => !b.closest("#" + PANEL_ID));
    return btns.find((b) => b.type === "submit" && /submit|apply|send/i.test(b.textContent || b.value || ""))
      || btns.find((b) => /^(submit|apply|send)\b/i.test((b.textContent || b.value || "").trim()))
      || btns.find((b) => b.type === "submit") || null;
  }

  const inJsdomEnv = () => /jsdom/i.test(root.navigator?.userAgent || "");

  function collectSignals(doc, url) {
    const errors = [...doc.querySelectorAll("[aria-invalid='true'], .error, .field-error, [role='alert'], .invalid-feedback")]
      .filter((e) => !e.closest("#" + PANEL_ID)).map((e) => clean(e.textContent)).filter((t) => t && t.length < 200);
    const body = clean(doc.body?.innerText || doc.body?.textContent || "").slice(0, 1500);
    return { confirmation_text: body, confirmation_url: url, page_title: doc.title, validation_errors: [...new Set(errors)].slice(0, 6),
             form_still_present: !!findSubmitButton(doc) && [...doc.forms].some((f) => f.querySelector("input:not([type=hidden]), textarea") && (inJsdomEnv() || f.getClientRects().length > 0)),
             captcha: detectCaptcha(doc) };
  }

  const api = { detectAts, labelText, collectFields, fillField, detectCaptcha, findSubmitButton, collectSignals, attachFile, clean };

  // ---------------------------------------------------------------- tests
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  if (typeof chrome === "undefined" || !chrome.runtime?.id || root.__cafyLoaded) return;
  root.__cafyLoaded = true;

  // -------------------------------------------------------------- runtime
  const call = (path, method, body, binary) => new Promise((resolve) => chrome.runtime.sendMessage({ type: "api", path, method, body, binary }, resolve));
  const state = { app: null, review: null, elements: {}, fields: [], busy: false, message: "", poll: null, submitted: false };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function panel() {
    let host = document.getElementById(PANEL_ID);
    if (host) return host.shadowRoot;
    host = document.createElement("div");
    host.id = PANEL_ID;
    host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;";
    const sr = host.attachShadow({ mode: "open" });
    sr.innerHTML = `<style>
      .box{font:13px system-ui,sans-serif;background:#fff;color:#0f172a;border:1px solid #cbd5e1;border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.18);width:320px;padding:14px;max-height:70vh;overflow:auto}
      h4{margin:0 0 4px;font-size:14px} .m{color:#475569;margin:4px 0} ul{padding-left:16px;margin:6px 0}
      li.b{color:#991b1b} button{margin:6px 6px 0 0;padding:6px 10px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;cursor:pointer}
      button.p{background:#0f172a;color:#fff;border-color:#0f172a} button:disabled{opacity:.5;cursor:not-allowed}
    </style><div class="box" id="box"></div>`;
    document.documentElement.appendChild(host);
    return sr;
  }

  function render() {
    const box = panel().getElementById("box");
    const r = state.review;
    const blockers = r?.blockers || [];
    const gate = state.gate;
    box.innerHTML = `
      <h4>Cafy Application Assistant</h4>
      <div class="m">${state.app ? `${esc(state.app.company)} – ${esc(state.app.job_title)}` : "No Cafy application matches this page."}</div>
      ${state.app ? `<div class="m">Status: <b>${esc((r?.application || state.app).status.replace(/_/g, " "))}</b></div>` : ""}
      ${state.message ? `<div class="m">${esc(state.message)}</div>` : ""}
      ${blockers.length ? `<ul>${blockers.slice(0, 6).map((b) => `<li class="b">${esc(b)}</li>`).join("")}</ul>` : ""}
      ${state.app && !state.submitted ? `
        <button class="p" id="fill" ${state.busy ? "disabled" : ""}>Fill form</button>
        <button id="perm" ${state.busy || !state.hasResumeField ? "disabled" : ""}>Allow résumé upload</button>
        <button id="open">Review in Cafy</button>
        <button class="p" id="submit" ${gate?.allowed && !state.busy ? "" : "disabled"} title="${esc(gate?.reason || "")}">Submit application</button>
        <div class="m">${gate?.allowed ? "Approved – you can submit." : esc(gate?.reason || "Approve the application in Cafy to enable submit.")}</div>` : ""}`;
    const on = (id, fn) => box.querySelector("#" + id)?.addEventListener("click", fn);
    on("fill", fillAll); on("perm", grantResume); on("submit", submit);
    on("open", async () => { const s = await new Promise((r2) => chrome.runtime.sendMessage({ type: "settings" }, r2)); window.open(`${s.backendUrl}/?application=${state.app.id}`, "_blank", "noopener"); });
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const say = (m) => { state.message = m; render(); };
  const errMsg = (res) => res?.data?.detail?.message || res?.data?.detail || `Request failed (${res?.status})`;

  async function detectAndMap() {
    const { fields, elements } = collectFields(document);
    if (fields.length < 2) { say("No application form detected on this page."); return false; }
    state.fields = fields; state.elements = elements;
    state.hasResumeField = fields.some((f) => f.type === "file");
    const res = await call(`/${state.app.id}/form`, "POST", { url: location.href.split("#")[0], ats: detectAts(location.hostname), fields });
    if (!res.ok) { say(errMsg(res)); if (res.status === 422) await call(`/${state.app.id}/events`, "POST", { event: "unsupported_form", detail: location.href }); return false; }
    state.review = res.data;
    return true;
  }

  async function fillAll() {
    state.busy = true; say("Reading the form…");
    try {
      if (!(await detectAndMap())) return;
      let filled = 0;
      for (const f of state.review.fields) {
        const target = state.elements[f.field_key];
        const spec = state.fields.find((x) => x.key === f.field_key);
        if (!target || !spec || f.field_source === "unknown" || !f.field_value) continue;
        if (fillField(target, spec, f.field_value)) filled++;
      }
      await uploadResumeIfPermitted();
      say(`Filled ${filled} field(s). Review them, then approve in Cafy.`);
      await refresh();
    } finally { state.busy = false; render(); }
  }

  async function uploadResumeIfPermitted() {
    const doc = state.review.documents.find((d) => d.document_type === "resume");
    if (!doc || !doc.permission_granted || doc.upload_status === "uploaded") return;
    const input = state.elements[doc.field_key];
    if (!input) return;
    const file = await call(`/${state.app.id}/documents/resume/file`, "GET", undefined, true);
    if (!file.ok) { await call(`/${state.app.id}/events`, "POST", { event: "upload_failed", detail: errMsg(file) }); return say(`Résumé not uploaded: ${errMsg(file)}`); }
    const name = doc.filename || "resume.pdf";
    let ok = false;
    try { ok = await attachFile(input, file.base64, name, file.contentType); } catch (e) { ok = false; }
    const rep = await call(`/${state.app.id}/documents/${doc.id}/status`, "POST", { status: ok ? "uploaded" : "failed", detail: ok ? null : "The page did not accept the file." });
    if (rep.ok) state.review = rep.data;
  }

  async function grantResume() {
    state.busy = true; render();
    const res = await call(`/${state.app.id}/documents/permission`, "POST", { document_type: "resume", granted: true });
    if (res.ok) { state.review = res.data; await uploadResumeIfPermitted(); say("Résumé upload allowed for this application."); } else say(errMsg(res));
    state.busy = false; await refresh();
  }

  async function refresh() {
    if (!state.app || state.submitted) return;
    const [rev, gate] = await Promise.all([call(`/${state.app.id}/review`, "GET"), call(`/${state.app.id}/submit-permission`, "GET")]);
    if (rev.ok) state.review = rev.data;
    if (gate.ok) state.gate = gate.data;
    render();
  }

  async function submit() {
    state.busy = true; render();
    try {
      const gate = await call(`/${state.app.id}/submit-permission`, "GET");
      if (!gate.ok || !gate.data.allowed) { state.gate = gate.data; return say("Not approved yet – approve the application in Cafy first."); }
      if (detectCaptcha(document)) {
        await call(`/${state.app.id}/events`, "POST", { event: "captcha", detail: "CAPTCHA present before submit" });
        return say("A CAPTCHA/verification is on this page. Please complete it yourself, then approve again in Cafy.");
      }
      const btn = findSubmitButton(document);
      if (!btn) return say("Could not find the site's submit button. Submit it manually, then confirm in Cafy.");
      const clickedAt = new Date().toISOString();
      const startUrl = location.href;
      btn.click();
      say("Submitted – waiting for the website's confirmation…");
      let signals = {};
      for (let i = 0; i < 24; i++) { // up to ~12 s
        await sleep(500);
        signals = collectSignals(document, location.href);
        if (signals.captcha || signals.validation_errors.length || (location.href !== startUrl && !signals.form_still_present) ||
            /thank you for applying|application (has been )?(submitted|received)|successfully submitted/i.test(signals.confirmation_text)) break;
      }
      const res = await call(`/${state.app.id}/submission`, "POST", { ...signals, clicked_at: clickedAt });
      if (!res.ok) return say(errMsg(res));
      if (res.data.paused) return say("Paused: complete the verification on the page, then approve again in Cafy.");
      if (res.data.result === "submitted") { state.submitted = true; state.review = { ...state.review, application: res.data.application, blockers: [] }; return say(`Submission confirmed${res.data.reference ? ` (ref ${res.data.reference})` : ""}.`); }
      say(res.data.result === "submission_failed" ? `Submission failed: ${res.data.error}` : `Not confirmed: ${res.data.error} Check your email, then confirm in Cafy.`);
    } finally { state.busy = false; render(); }
  }

  async function init() {
    const res = await call(`/lookup?url=${encodeURIComponent(location.href)}`, "GET");
    if (!res.ok || !Array.isArray(res.data) || !res.data.length) {
      if (res.network) { /* backend unreachable: stay quiet on unrelated sites */ }
      return; // no Cafy application for this page: do nothing
    }
    state.app = res.data[0];
    render();
    await refresh();
    state.poll = setInterval(refresh, 4000);
  }

  init();
})(typeof window !== "undefined" ? window : globalThis);
