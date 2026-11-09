let profileState = null;
let jobCache = {};
const tailoredCache = {};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = "toast show" + (isError ? " error" : "");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => (el.className = "toast"), 4500);
}

async function api(path, options = {}) {
  const opts = { headers: {}, ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, opts);
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    data = null;
  }
  if (!response.ok) {
    const detail = data && (data.detail || data.message);
    throw new Error(detail ? (typeof detail === "string" ? detail : JSON.stringify(detail)) : `HTTP ${response.status}`);
  }
  return data;
}

function fmtDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function scoreClass(score) {
  if (score >= 80) return "high";
  if (score >= 60) return "mid";
  return "low";
}

// ---------- navigation ----------
document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    const view = button.dataset.view;
    document.getElementById(`view-${view}`).classList.add("active");
    if (view === "dashboard") loadDashboard();
    if (view === "jobs") loadJobs();
    if (view === "applications") loadApplications();
    if (view === "outreach") loadOutreach();
    if (view === "profile") loadProfile();
    if (view === "settings") loadSettings();
  });
});

// ---------- dashboard ----------
async function loadDashboard() {
  try {
    const data = await api("/api/dashboard");
    const stat = (label, value, sub) => `
      <div class="card stat">
        <div class="label">${escapeHtml(label)}</div>
        <div class="value">${escapeHtml(value)}</div>
        ${sub ? `<div class="sub">${escapeHtml(sub)}</div>` : ""}
      </div>`;
    document.getElementById("stats").innerHTML = [
      stat("Jobs discovered", data.jobs_discovered, `${data.jobs_scored} scored`),
      stat("Strong matches", data.strong_matches, `score ≥ 80`),
      stat("Relevant jobs", data.relevant_jobs, `score ≥ 60`),
      stat("Applications", data.applications_submitted, `${data.pending_approvals} pending approvals`),
      stat("Interviews", data.interviews_scheduled, `${data.recruiter_responses} responses`),
      stat("Conversion", `${data.conversion_rate}%`, "submitted / discovered"),
    ].join("");

    document.getElementById("topMatches").innerHTML = data.top_matches.length
      ? `<table><thead><tr><th>Role</th><th>Company</th><th>Mode / Region</th><th>Score</th></tr></thead><tbody>${data.top_matches
          .map(
            (m) => `<tr><td><a href="#" onclick="openJob(${m.job_id});return false">${escapeHtml(m.title)}</a></td>
              <td>${escapeHtml(m.company)}</td><td>${escapeHtml(m.work_mode || "")} &middot; ${escapeHtml(m.region || "")}</td><td><span class="score ${scoreClass(m.score)}" style="min-width:auto;padding:3px 8px;font-size:13px">${m.score}</span></td></tr>`
          )
          .join("")}</tbody></table>`
      : `<div class="empty">No matches yet. Run discovery, then re-match.</div>`;

    const pipeline = data.applications || {};
    document.getElementById("pipeline").innerHTML = Object.keys(pipeline).length
      ? Object.entries(pipeline)
          .map(([status, count]) => `<div class="row" style="margin:6px 0"><span class="status ${status}">${escapeHtml(status)}</span><span class="spacer"></span><b>${count}</b></div>`)
          .join("")
      : `<div class="empty">No applications yet.</div>`;

    document.getElementById("recentApps").innerHTML = data.recent_applications.length
      ? data.recent_applications
          .map(
            (a) => `<div class="row" style="margin:8px 0"><div><b>${escapeHtml(a.title)}</b><div class="muted small">${escapeHtml(a.company)}</div></div><span class="spacer"></span><span class="status ${a.status}">${escapeHtml(a.status)}</span></div>`
          )
          .join("")
      : `<div class="empty">No applications yet.</div>`;

    document.getElementById("profileBadge").textContent = data.profile.name || "Profile";
    applyLlmInfo(data.llm || {});
  } catch (err) {
    toast(err.message, true);
  }
}

function applyLlmInfo(llm) {
  const badge = document.getElementById("llmBadge");
  if (badge) {
    badge.textContent = `LLM: ${llm.provider || "?"} / ${llm.model || "?"}`;
    badge.className = "badge " + (llm.usable && !llm.fallback ? "ok" : "warn");
  }
  const warning = document.getElementById("llmTailorWarning");
  if (warning) {
    if (llm.fallback) {
      warning.style.display = "block";
      warning.innerHTML = `<b>Template fallback active.</b> ${escapeHtml(llm.reason || "No LLM provider is configured")}. Add GEMINI_API_KEY or GROQ_API_KEY to .env and restart the server. Tailoring still uses your real profile, but wording will be template-based.`;
    } else {
      warning.style.display = "none";
    }
  }
  const box = document.getElementById("llmBox");
  if (!box) return;
  const chain = (llm.chain || []).filter((spec) => spec.provider);
  const rate = llm.rate_limit || {};
  box.innerHTML = `
    <div class="row" style="margin:6px 0">
      <span class="status ${llm.usable && !llm.fallback ? "submitted" : "draft"}">${llm.usable && !llm.fallback ? "active" : "fallback"}</span>
      <b>${escapeHtml(llm.provider || "template")} / ${escapeHtml(llm.model || "template-fallback")}</b>
      <span class="spacer"></span>
      <span class="muted small">${llm.fallback ? "template fallback" : "ready"}</span>
    </div>
    ${chain.map((spec) => `<div class="row" style="margin:6px 0">
      <span class="status ${spec.configured ? "submitted" : "draft"}">${spec.configured ? "configured" : "missing"}</span>
      <span class="muted small">${escapeHtml(spec.role)}</span>
      <b>${escapeHtml(spec.provider)}</b>
      <span class="muted small">${escapeHtml(spec.model || "model not set")}</span>
      <span class="spacer"></span>
      <span class="muted small">${spec.configured ? "ready" : escapeHtml(spec.error || "not configured")}</span>
    </div>`).join("")}
    <div class="muted small" style="margin-top:6px">Calls today: ${escapeHtml(rate.count ?? "?")} / ${escapeHtml(rate.daily_limit ?? "?")} (cached results do not consume quota)</div>
    ${llm.fallback ? `<div class="warning" style="margin-top:10px">${escapeHtml(llm.reason || "No usable provider")}</div>` : ""}
  `;
}

async function loadLlm() {
  try {
    const info = await api("/api/llm/info");
    applyLlmInfo(info);
    return info;
  } catch (err) {
    toast(err.message, true);
    return null;
  }
}

async function testLlm() {
  const button = document.getElementById("llmTestBtn");
  const resultsBox = document.getElementById("llmTestResults");
  if (button) {
    button.disabled = true;
    button.textContent = "Testing...";
  }
  if (resultsBox) resultsBox.innerHTML = `<div class="empty">Sending a tiny JSON prompt to each configured provider...</div>`;
  try {
    const data = await api("/api/llm/test", { method: "POST" });
    applyLlmInfo(data.info || {});
    const rows = (data.results || []).map((result) => `
      <div class="row" style="margin:6px 0">
        <span class="status ${result.ok ? "submitted" : "draft"}">${result.ok ? "PASS" : "FAIL"}</span>
        <b>${escapeHtml(result.role)}: ${escapeHtml(result.provider)}</b>
        <span class="muted small">${escapeHtml(result.model)}</span>
        <span class="spacer"></span>
        <span class="muted small">${escapeHtml(result.error || result.status || "")}</span>
      </div>`).join("");
    if (resultsBox) resultsBox.innerHTML = rows || `<div class="empty">No providers configured.</div>`;
    toast("LLM test finished");
  } catch (err) {
    if (resultsBox) resultsBox.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
    toast(err.message, true);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Test LLM";
    }
  }
}

// ---------- jobs ----------
async function loadJobs(query = null) {
  const q = query !== null ? query : document.getElementById("jobSearch").value;
  const min = document.getElementById("jobMinScore").value || 0;
  const remote = document.getElementById("jobRemote").value;
  const region = document.getElementById("jobRegion").value;
  const indiaEligible = document.getElementById("jobIndiaEligible").value;
  document.getElementById("jobList").innerHTML = `<div class="empty">Loading...</div>`;
  try {
    const params = new URLSearchParams({ limit: "60" });
    if (q) params.set("q", q);
    if (Number(min) > 0) params.set("min_score", min);
    if (remote) params.set("remote", remote);
    if (region) params.set("region", region);
    if (indiaEligible) params.set("india_eligible", indiaEligible);
    const showStale = document.getElementById("jobShowStale");
    if (showStale && showStale.checked) params.set("show_stale", "true");
    const data = await api(`/api/jobs?${params.toString()}`);
    jobCache = {};
    data.items.forEach((job) => (jobCache[job.id] = job));
    document.getElementById("jobList").innerHTML = data.items.length
      ? data.items.map(renderJob).join("")
      : `<div class="empty">No jobs found. Run discovery or import a job.</div>`;
  } catch (err) {
    toast(err.message, true);
  }
}

function renderJob(job) {
  const matched = (job.matched_skills || []).map((s) => `<span class="chip have">${escapeHtml(s)}</span>`).join("");
  const missing = (job.missing_skills || []).slice(0, 8).map((s) => `<span class="chip miss">${escapeHtml(s)}</span>`).join("");
  const score = job.score ?? null;
  const salary = job.salary_min || job.salary_max
    ? `${job.currency || ""} ${Math.round(job.salary_min || 0).toLocaleString()} – ${Math.round(job.salary_max || job.salary_min || 0).toLocaleString()}`
    : "Salary not listed";
  return `
    <div class="job" id="job-${job.id}">
      <div class="job-head">
        <div class="score ${scoreClass(score || 0)}">${score === null ? "–" : Math.round(score)}</div>
        <div style="flex:1">
          <div class="row"><b style="font-size:15px">${escapeHtml(job.title)}</b><span class="spacer"></span>
            <span class="chip">${escapeHtml(job.work_mode || (job.remote ? "Remote/WFH" : "Onsite/Hybrid"))}</span>
            <span class="chip">${escapeHtml(job.region || "Other")}</span>
            <span class="chip ${job.eligibility === "blocked" ? "miss" : job.eligibility === "unclear" ? "" : "have"}" title="${escapeHtml(job.eligibility_evidence || job.eligibility_reason || "")}">${escapeHtml(job.eligibility_badge || (job.eligibility === "allowed" ? "Yes" : job.eligibility === "blocked" ? "No" : "Unclear"))}</span>
          </div>
          <div class="muted small">${escapeHtml(job.company)} � ${escapeHtml(job.location || "Location n/a")} � ${escapeHtml(salary)}</div>
          <div style="margin-top:8px">${matched} ${missing}</div>
          ${job.rationale ? `<div class="muted small" style="margin-top:6px">${escapeHtml(job.rationale)}</div>` : ""}
          ${job.eligibility_reason ? `<div class="muted small">${escapeHtml(job.eligibility_reason)}</div>` : ""}
          <div class="row" style="margin-top:10px">
            <button onclick="toggleDetails(${job.id})">Details</button>
            <button onclick="tailorJob(${job.id})">Tailor resume</button>
            <button onclick="createApplication(${job.id})">Create application</button>
            <button onclick="draftOutreach(${job.id})">Draft outreach</button>
            ${job.url ? `<a class="btn ghost" href="${escapeHtml(job.url)}" target="_blank" rel="noopener">Open posting</a>` : ""}
          </div>
          <div id="details-${job.id}" style="display:none;margin-top:10px"></div>
          <div id="tailored-${job.id}" style="margin-top:10px"></div>
        </div>
      </div>
    </div>`;
}

async function toggleDetails(jobId) {
  const box = document.getElementById(`details-${jobId}`);
  if (box.style.display === "block") {
    box.style.display = "none";
    return;
  }
  box.style.display = "block";
  if (box.dataset.loaded) return;
  try {
    const job = await api(`/api/jobs/${jobId}`);
    const breakdown = job.score != null ? `
      <div style="margin:8px 0">
        <div class="small muted" style="margin-bottom:4px">Score breakdown (0–100 per dimension)</div>
        <div class="row" style="gap:6px;flex-wrap:wrap">
          <span class="chip ${scoreClass(job.score)}">Overall: ${Math.round(job.score)}</span>
          <span class="chip">Skills: ${Math.round(job.skill_score || 0)}</span>
          <span class="chip">Experience: ${Math.round(job.experience_score || 0)}</span>
          <span class="chip">Responsibilities: ${Math.round(job.responsibility_score || 0)}</span>
          <span class="chip">Salary: ${Math.round(job.salary_score || 0)}</span>
          <span class="chip">Location: ${Math.round(job.location_score || 0)}</span>
        </div>
      </div>` : "";
    box.innerHTML = `
      <div class="muted small">Posted ${fmtDate(job.posted_at)} · ${escapeHtml(job.location || "")}</div>
      ${breakdown}
      <div style="margin:8px 0">${(job.keywords || []).slice(0, 20).map((k) => `<span class="chip">${escapeHtml(k)}</span>`).join("")}</div>
      ${(job.missing_keywords || []).length ? `<div class="small muted">ATS gaps: ${job.missing_keywords.map(escapeHtml).join(", ")}</div>` : ""}
      <details style="margin-top:8px"><summary>Job description</summary><div class="muted small" style="white-space:pre-wrap;margin-top:8px;max-height:320px;overflow:auto">${escapeHtml(job.description || "No description")}</div></details>`;
    box.dataset.loaded = "1";
  } catch (err) {
    toast(err.message, true);
  }
}

async function openJob(jobId) {
  document.querySelector('nav button[data-view="jobs"]').click();
  await loadJobs("");
  const el = document.getElementById(`job-${jobId}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.style.outline = "1px solid var(--accent)";
    setTimeout(() => (el.style.outline = "none"), 2200);
  }
}

function renderLlmFallback(item) {
  const llm = (item.match_report || {}).llm || {};
  if (!llm.fallback) return "";
  const reason = llm.reason || "No LLM provider is configured";
  return `<div class="warning"><b>Template fallback used.</b> ${escapeHtml(reason)}. Add GEMINI_API_KEY or GROQ_API_KEY to .env and restart the server to use Gemini/Groq. The resume below was still built from your real profile.</div>`;
}

function renderDiff(diff) {
  if (!diff) return `<div class="empty">No diff data available.</div>`;
  const blocks = [];
  const list = (items) => `<ul style="margin:4px 0 8px 18px">${(items || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("")}</ul>`;
  if (diff.summary && diff.summary.before !== diff.summary.after) {
    blocks.push(`<div><b>Summary</b><div class="small diff-before">Before:</div><div>${escapeHtml(diff.summary.before || "(empty)")}</div><div class="small diff-after" style="margin-top:6px">After:</div><div>${escapeHtml(diff.summary.after || "(empty)")}</div></div>`);
  }
  (diff.experience || []).forEach((entry) => {
    const before = JSON.stringify(entry.before || []);
    const after = JSON.stringify(entry.after || []);
    if (before === after) return;
    blocks.push(`<div style="margin-top:10px"><b>${escapeHtml(entry.title || "")}${entry.company ? ` @ ${escapeHtml(entry.company)}` : ""}</b><div class="small diff-before">Before:</div>${list(entry.before)}<div class="small diff-after">After:</div>${list(entry.after)}</div>`);
  });
  (diff.projects || []).forEach((entry) => {
    const before = JSON.stringify(entry.before || []);
    const after = JSON.stringify(entry.after || []);
    if (before === after) return;
    blocks.push(`<div style="margin-top:10px"><b>${escapeHtml(entry.name || "Project")}</b><div class="small diff-before">Before:</div>${list(entry.before)}<div class="small diff-after">After:</div>${list(entry.after)}</div>`);
  });
  const skills = diff.skills || {};
  if (JSON.stringify(skills.before || []) !== JSON.stringify(skills.after || [])) {
    blocks.push(`<div style="margin-top:10px"><b>Skills order/grouping</b><div class="small muted">Only real profile skills are kept; ordering follows JD relevance.</div><div class="small diff-before">Before:</div><div>${(skills.before || []).map((s) => `<span class="chip">${escapeHtml(s)}</span>`).join(" ")}</div><div class="small diff-after">After:</div><div>${(skills.after || []).map((s) => `<span class="chip have">${escapeHtml(s)}</span>`).join(" ")}</div></div>`);
  }
  return blocks.length ? blocks.join("") : `<div class="empty">No wording changes detected.</div>`;
}

function renderMatchReport(item) {
  const report = item.match_report || {};
  const before = Number.isFinite(Number(report.before_score)) ? Number(report.before_score) : null;
  const after = Number.isFinite(Number(report.after_score)) ? Number(report.after_score) : null;
  const matched = report.matched || [];
  const missing = report.missing || [];
  const gaps = report.gaps || [];
  const target = Number(report.target_score) || 90;
  const targetMet = Boolean(report.target_met);
  const fixable = report.fixable_gaps || [];
  const unverified = report.unverified_gaps || [];
  const actions = report.gap_actions || [];
  const pages = report.estimated_pages || 1;
  return `<div class="match-report">
    <div class="row"><b>Match report</b><span class="spacer"></span><button onclick="toggleDiff(${item.id})">Show changes vs master</button></div>
    <div class="score-pair">
      <div><div class="muted small">Before</div><b>${before === null ? "-" : before + "%"}</b></div>
      <div><div class="muted small">After tailoring</div><b>${after === null ? "-" : after + "%"}</b></div>
      <div><div class="muted small">Target</div><b>${target}%</b></div>
      <div><div class="muted small">Length</div><b>${pages} page${pages === 1 ? "" : "s"}</b></div>
    </div>
    <div style="margin-top:6px">${targetMet ? `<span class="chip have">${target}% target met</span>` : `<span class="chip miss">Below ${target}% target</span>`}</div>
    ${!targetMet && actions.length ? `<div class="warning" style="margin-top:8px"><b>Verified target not met.</b><ul style="margin:4px 0 0 18px">${actions.map((a) => `<li>${escapeHtml(a)}</li>`).join("")}</ul></div>` : ""}
    ${pages > 1 ? `<div class="warning">This looks longer than one page. Trim older bullets before uploading if the portal expects a one-page resume.</div>` : ""}
    <div class="small" style="margin-top:6px">Matched keywords</div>
    <div>${matched.length ? matched.slice(0, 24).map((k) => `<span class="chip have">${escapeHtml(k)}</span>`).join(" ") : `<span class="muted small">None detected</span>`}</div>
    ${fixable.length ? `<div class="small" style="margin-top:8px">Verified in your resume but missing from this version</div><div>${fixable.slice(0, 24).map((k) => `<span class="chip miss">${escapeHtml(k)}</span>`).join(" ")}</div>` : ""}
    ${unverified.length ? `<div class="small" style="margin-top:8px">Unverified gaps — do not claim without evidence</div><div>${unverified.slice(0, 24).map((k) => `<span class="chip miss">${escapeHtml(k)}</span>`).join(" ")}</div>` : ""}
    ${(missing.length || gaps.length) && !fixable.length && !unverified.length ? `<div class="small" style="margin-top:8px">Missing keywords / gaps</div><div>${[...missing, ...gaps.filter((g) => !missing.includes(g))].slice(0, 24).map((k) => `<span class="chip miss">${escapeHtml(k)}</span>`).join(" ")}</div>` : ""}
    <div id="diff-${item.id}" class="diff-panel" style="display:none"><div class="small muted">Changes are shown against your master resume. Nothing was invented.</div>${renderDiff(report.diff)}</div>
  </div>`;
}

function tailorToText(item) {
  const lines = [];
  if (item.summary) lines.push(item.summary, "");
  if ((item.skills || []).length) {
    lines.push("CORE TECHNICAL SKILLS");
    item.skills.forEach((group) => lines.push(`${group.category || ""}: ${(group.items || []).join(", ")}`));
    lines.push("");
  }
  if ((item.experience || []).length) {
    lines.push("WORK EXPERIENCE");
    item.experience.forEach((entry) => {
      lines.push(`${entry.title || ""}${entry.company ? ` | ${entry.company}` : ""}${entry.dates ? ` | ${entry.dates}` : ""}`);
      (entry.bullets || []).forEach((bullet) => lines.push(`- ${bullet}`));
      lines.push("");
    });
  }
  if ((item.projects || []).length) {
    lines.push("KEY PROJECTS");
    item.projects.forEach((entry) => {
      lines.push(`${entry.name || ""}${entry.tech ? ` | ${entry.tech}` : ""}`);
      (entry.bullets || []).forEach((bullet) => lines.push(`- ${bullet}`));
      lines.push("");
    });
  }
  if (item.cover_letter) lines.push("COVER LETTER", item.cover_letter);
  return lines.join("\n").trim();
}

function toggleDiff(id) {
  const panel = document.getElementById(`diff-${id}`);
  if (!panel) return;
  panel.style.display = panel.style.display === "none" ? "block" : "none";
}

async function copyTailored(id) {
  const item = tailoredCache[id];
  if (!item) return;
  try {
    await navigator.clipboard.writeText(tailorToText(item));
    toast("Tailored resume copied as text");
  } catch (err) {
    toast("Clipboard unavailable - select and copy the preview instead", true);
  }
}

async function saveTailoredApplication(id) {
  const item = tailoredCache[id];
  if (!item) return;
  const jobId = (item.job && item.job.id) || item.job_id;
  if (!jobId) {
    toast("This tailored package has no job to save", true);
    return;
  }
  try {
    await api("/api/applications", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId, tailored_resume_id: id }),
    });
    toast("Application draft saved - review it in Applications");
    loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderTailoredPackage(item, heading = "Tailored package ready") {
  tailoredCache[item.id] = item;
  const job = item.job || {};
  const meta = [job.title, job.company].filter(Boolean).join(" at ");
  const download = (fmt) =>
    item[`has_${fmt}`]
      ? `<a class="btn" href="/api/tailored/${item.id}/download?fmt=${fmt}" target="_blank" rel="noopener">Download ${fmt.toUpperCase()}</a>`
      : "";
  const experienceEditor = (item.experience || []).map((e, index) => `
    <div style="margin-bottom:10px">
      <b>${escapeHtml(e.title || "")}</b>
      <div class="muted small">${escapeHtml(e.company || "")}${e.dates ? ` | ${escapeHtml(e.dates)}` : ""}</div>
      <textarea id="edit-exp-${item.id}-${index}" rows="4" style="width:100%" spellcheck="true">${escapeHtml((e.bullets || []).join("\n"))}</textarea>
    </div>`).join("");
  const projectEditor = (item.projects || []).map((e, index) => `
    <div style="margin-bottom:10px">
      <b>${escapeHtml(e.name || "")}</b>
      ${e.tech ? `<div class="muted small">${escapeHtml(e.tech)}</div>` : ""}
      <textarea id="edit-proj-${item.id}-${index}" rows="3" style="width:100%" spellcheck="true">${escapeHtml((e.bullets || []).join("\n"))}</textarea>
    </div>`).join("");
  return `
    <div class="card" id="tailor-card-${item.id}">
      <div class="row"><b>${escapeHtml(heading)}</b><span class="spacer"></span>${meta ? `<span class="muted small">${escapeHtml(meta)}</span>` : ""}</div>
      ${renderLlmFallback(item)}
      <p class="muted small" style="margin:8px 0">${escapeHtml(item.summary)}</p>
      ${renderMatchReport(item)}
      ${(item.experience || []).length ? `<details open><summary>Resume preview (newest first)</summary>
        <div style="margin-top:8px">${item.experience.map((e) => `
          <div style="margin-bottom:10px">
            <b>${escapeHtml(e.title || "")}</b>
            <div class="muted small">${escapeHtml(e.company || "")}${e.dates ? ` | ${escapeHtml(e.dates)}` : ""}</div>
            <ul style="margin:4px 0 0 18px">${(e.bullets || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("")}</ul>
          </div>`).join("")}</div>
      </details>` : ""}
      ${(item.projects || []).length ? `<details><summary>Projects</summary>
        <div style="margin-top:8px">${item.projects.map((e) => `
          <div style="margin-bottom:8px"><b>${escapeHtml(e.name || "")}</b>${e.tech ? `<div class="muted small">${escapeHtml(e.tech)}</div>` : ""}
            <ul style="margin:4px 0 0 18px">${(e.bullets || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("")}</ul>
          </div>`).join("")}</div>
      </details>` : ""}
      <details><summary>Edit summary, cover letter and bullets</summary>
        <div style="margin-top:8px">
          <label class="muted small">Summary</label>
          <textarea id="edit-summary-${item.id}" rows="4" style="width:100%">${escapeHtml(item.summary || "")}</textarea>
          <label class="muted small">Cover letter</label>
          <textarea id="edit-cover-${item.id}" rows="8" style="width:100%">${escapeHtml(item.cover_letter || "")}</textarea>
          ${experienceEditor}
          ${projectEditor}
          <div class="row" style="margin-top:8px">
            <button class="primary" onclick="saveTailoredEdits(${item.id})">Save edits and re-export</button>
            <button onclick="resetTailoredEditor(${item.id})">Reset editor</button>
            <button onclick="retailorJob(${item.job_id || item.job && item.job.id})">↺ Re-tailor from AI</button>
          </div>
        </div>
      </details>
      <details><summary>Cover letter</summary><pre class="letter">${escapeHtml(item.cover_letter)}</pre></details>
      ${(item.keywords || []).length ? `<div style="margin-top:8px">${item.keywords.slice(0, 18).map((k) => `<span class="chip">${escapeHtml(k)}</span>`).join("")}</div>` : ""}
      <div class="row" style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border, #e5e7eb)">
        <span class="muted small">Review the preview above, then save or download:</span>
        <span class="spacer"></span>
        <button onclick="copyTailored(${item.id})">Copy as text</button>
        <button onclick="saveTailoredApplication(${item.id})">Save to Applications</button>
        ${download("pdf")} ${download("docx")}
      </div>
    </div>`;
}

function resetTailoredEditor(id) {
  const item = tailoredCache[id];
  const card = document.getElementById(`tailor-card-${id}`);
  if (item && card) card.outerHTML = renderTailoredPackage(item);
}

async function saveTailoredEdits(id) {
  const item = tailoredCache[id];
  if (!item) return;
  const summary = document.getElementById(`edit-summary-${id}`).value;
  const coverLetter = document.getElementById(`edit-cover-${id}`).value;
  const experience = (item.experience || []).map((entry, index) => ({
    ...entry,
    bullets: document.getElementById(`edit-exp-${id}-${index}`).value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
  }));
  const projects = (item.projects || []).map((entry, index) => ({
    ...entry,
    bullets: document.getElementById(`edit-proj-${id}-${index}`).value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
  }));
  try {
    const updated = await api(`/api/tailored/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ summary, cover_letter: coverLetter, experience, projects }),
    });
    const card = document.getElementById(`tailor-card-${id}`);
    if (card) card.outerHTML = renderTailoredPackage(updated, "Edits saved - exports regenerated");
    toast("Edits saved and PDF/DOCX regenerated");
  } catch (err) {
    toast(err.message, true);
  }
}

async function retailorJob(jobId) {
  const box = document.getElementById(`tailored-${jobId}`);
  if (!box) return;
  box.innerHTML = `<div class="empty">Re-tailoring from AI (discarding manual edits)...</div>`;
  try {
    const item = await api(`/api/jobs/${jobId}/tailor`, { method: "POST" });
    if (!item.job) item.job = jobCache[jobId] || { id: jobId };
    box.innerHTML = renderTailoredPackage(item, "Re-tailored from AI");
    toast("Re-tailored from AI — manual edits discarded");
  } catch (err) {
    box.innerHTML = "";
    toast(err.message, true);
  }
}

async function tailorJob(jobId) {
  const box = document.getElementById(`tailored-${jobId}`);
  box.innerHTML = `<div class="empty">Generating tailored resume and cover letter...</div>`;
  try {
    const item = await api(`/api/jobs/${jobId}/tailor`, { method: "POST" });
    if (!item.job) item.job = jobCache[jobId] || { id: jobId };
    box.innerHTML = renderTailoredPackage(item);
    toast("Tailored resume generated");
  } catch (err) {
    box.innerHTML = "";
    toast(err.message, true);
  }
}

async function tailorManual() {
  const description = document.getElementById("manualJd").value.trim();
  const box = document.getElementById("manualResultCard");
  if (description.length < 40) {
    toast("Paste the full job description first", true);
    return;
  }
  box.innerHTML = `<div class="empty">Generating tailored resume from the pasted JD...</div>`;
  const payload = {
    title: document.getElementById("manualTitle").value.trim(),
    company: document.getElementById("manualCompany").value.trim(),
    location: document.getElementById("manualLocation").value.trim(),
    url: document.getElementById("manualUrl").value.trim(),
    remote: document.getElementById("manualRemote").checked,
    description,
  };
  try {
    const item = await api("/api/tailor/manual", { method: "POST", body: JSON.stringify(payload) });
    box.innerHTML = renderTailoredPackage(item, "Pasted JD tailored package ready");
    toast("Tailored resume generated - preview first, then download");
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    box.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
    toast(err.message, true);
  }
}

async function createApplication(jobId) {
  try {
    await api("/api/applications", { method: "POST", body: JSON.stringify({ job_id: jobId }) });
    toast("Application draft created — review it in Applications");
    loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

async function draftOutreach(jobId, channel = "email") {
  try {
    await api("/api/outreach", { method: "POST", body: JSON.stringify({ job_id: jobId, channel }) });
    toast("Outreach draft created — review it in Outreach");
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- applications ----------
async function loadApplications() {
  const box = document.getElementById("appList");
  box.innerHTML = `<div class="empty">Loading...</div>`;
  try {
    const data = await api("/api/applications");
    if (!data.items.length) {
      box.innerHTML = `<div class="empty">No applications yet. Tailor a resume from Jobs, then create an application.</div>`;
      return;
    }
    box.innerHTML = `<table><thead><tr><th>Role</th><th>Company</th><th>Status</th><th>Applied</th><th>Actions</th></tr></thead><tbody>${data.items
      .map((a) => {
        const job = a.job || {};
        const actions = [];
        if (a.status === "draft" || a.status === "pending_approval") {
          actions.push(`<button class="good" onclick="approveApplication(${a.id})">Approve</button>`);
        }
        if (a.status === "approved") {
          actions.push(`<button class="primary" onclick="submitApplication(${a.id})">Record submission</button>`);
        }
        if (a.tailored_resume_id) {
          actions.push(`<a class="btn ghost" href="/api/tailored/${a.tailored_resume_id}/download?fmt=pdf" target="_blank">Resume</a>`);
        }
        return `<tr><td>${escapeHtml(job.title || "")}</td><td>${escapeHtml(job.company || "")}</td>
          <td><span class="status ${a.status}">${escapeHtml(a.status)}</span></td>
          <td>${fmtDate(a.applied_at)}</td><td><div class="row">${actions.join("")}</div></td></tr>`;
      })
      .join("")}</tbody></table>`;
  } catch (err) {
    toast(err.message, true);
  }
}

async function approveApplication(id) {
  try {
    await api(`/api/applications/${id}/approve`, { method: "POST" });
    toast("Application approved");
    loadApplications();
    loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

async function submitApplication(id) {
  const confirmation = prompt("Paste the confirmation ID from the official portal (submission is done by you):");
  if (confirmation === null) return;
  try {
    await api(`/api/applications/${id}/submit`, {
      method: "POST",
      body: JSON.stringify({ confirmation_id: confirmation, authorized: true }),
    });
    toast("Submission recorded");
    loadApplications();
    loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- outreach ----------
async function loadOutreach() {
  loadRecruiters();
  const box = document.getElementById("outreachList");
  box.innerHTML = `<div class="empty">Loading...</div>`;
  try {
    const data = await api("/api/outreach");
    if (!data.items.length) {
      box.innerHTML = `<div class="empty">No outreach drafts. Add a recruiter and draft from a job card, or draft from a job.</div>`;
      return;
    }
    box.innerHTML = data.items
      .map((m) => {
        const recruiter = m.recruiter || {};
        const actions = [];
        if (m.status === "draft") actions.push(`<button class="good" onclick="approveOutreach(${m.id})">Approve</button>`);
        if (m.status === "approved" || m.status === "draft") actions.push(`<button onclick="sendOutreach(${m.id})">Send</button>`);
        actions.push(`<button class="ghost" onclick="followupOutreach(${m.id})">Draft follow-up</button>`);
        return `<div class="job"><div class="row"><b>${escapeHtml(m.subject || "(no subject)")}</b><span class="spacer"></span>
          <span class="status ${m.status}">${escapeHtml(m.status)}</span></div>
          <div class="muted small">${escapeHtml(m.channel)} · ${escapeHtml(recruiter.name || recruiter.email || "no recruiter")} ${recruiter.company ? "· " + escapeHtml(recruiter.company) : ""}</div>
          <details style="margin-top:8px"><summary>Message</summary><pre class="letter">${escapeHtml(m.body)}</pre></details>
          <div class="row" style="margin-top:8px">${actions.join("")}</div></div>`;
      })
      .join("");
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadRecruiters() {
  try {
    const data = await api("/api/recruiters");
    document.getElementById("recruiterList").innerHTML = data.items.length
      ? data.items
          .map(
            (r) => `<div class="row" style="margin:8px 0"><div><b>${escapeHtml(r.name || r.email || "Recruiter")}</b><div class="muted small">${escapeHtml(r.company || "")} ${r.email ? "· " + escapeHtml(r.email) : ""}</div></div><span class="spacer"></span>${r.linkedin_url ? `<a class="btn ghost" href="${escapeHtml(r.linkedin_url)}" target="_blank">LinkedIn</a>` : ""}</div>`
          )
          .join("")
      : `<div class="empty">No recruiters yet.</div>`;
  } catch (err) {
    toast(err.message, true);
  }
}

async function addRecruiter() {
  const payload = {
    name: document.getElementById("recName").value,
    company: document.getElementById("recCompany").value,
    email: document.getElementById("recEmail").value,
    linkedin_url: document.getElementById("recLinkedin").value,
    role: document.getElementById("recRole").value,
  };
  if (!payload.name && !payload.email) {
    toast("Enter a name or email", true);
    return;
  }
  try {
    await api("/api/recruiters", { method: "POST", body: JSON.stringify(payload) });
    ["recName", "recCompany", "recEmail", "recLinkedin", "recRole"].forEach((id) => (document.getElementById(id).value = ""));
    toast("Recruiter saved");
    loadRecruiters();
  } catch (err) {
    toast(err.message, true);
  }
}

async function approveOutreach(id) {
  try {
    await api(`/api/outreach/${id}/approve`, { method: "POST" });
    toast("Outreach approved");
    loadOutreach();
  } catch (err) {
    toast(err.message, true);
  }
}

async function sendOutreach(id) {
  try {
    await api(`/api/outreach/${id}/send`, { method: "POST" });
    toast("Outreach sent (or ready to copy for LinkedIn)");
    loadOutreach();
  } catch (err) {
    toast(err.message, true);
  }
}

async function followupOutreach(id) {
  try {
    await api(`/api/outreach/${id}/followup`, { method: "POST" });
    toast("Follow-up draft created");
    loadOutreach();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- profile ----------
async function loadProfile() {
  try {
    const profile = await api("/api/profile");
    profileState = profile;
    const skills = (profile.skills || []).map((s) => `<span class="chip have">${escapeHtml(s)}</span>`).join("");
    document.getElementById("profileSummary").innerHTML = `
      <div class="row"><div><b style="font-size:16px">${escapeHtml(profile.name)}</b>
        <div class="muted small">${escapeHtml(profile.headline || "")}</div></div></div>
      <div class="muted small" style="margin-top:8px">${escapeHtml(profile.email || "")} · ${escapeHtml(profile.phone || "")} · ${escapeHtml(profile.location || "")}</div>
      <div class="muted small" style="margin-top:4px">${profile.years_experience} years experience · ${(profile.skills || []).length} skills</div>
      <div style="margin-top:10px">${skills}</div>`;
    const prefs = profile.preferences || {};
    document.getElementById("prefRoles").value = (prefs.roles || []).join(", ");
    document.getElementById("prefLocations").value = (prefs.locations || []).join(", ");
    document.getElementById("prefSalary").value = prefs.min_salary || 0;
    document.getElementById("prefCurrency").value = prefs.currency || "INR";
    document.getElementById("prefRemote").checked = !!prefs.remote_ok;
    loadResumes();
    loadAts();
  } catch (err) {
    toast(err.message, true);
  }
}

async function savePreferences() {
  const current = (profileState && profileState.preferences) || {};
  const prefs = {
    ...current,
    roles: document.getElementById("prefRoles").value.split(",").map((s) => s.trim()).filter(Boolean),
    locations: document.getElementById("prefLocations").value.split(",").map((s) => s.trim()).filter(Boolean),
    min_salary: Number(document.getElementById("prefSalary").value || 0),
    currency: document.getElementById("prefCurrency").value || "INR",
    remote_ok: document.getElementById("prefRemote").checked,
  };
  try {
    await api("/api/profile", { method: "PUT", body: JSON.stringify({ preferences: prefs }) });
    toast("Preferences saved");
    loadProfile();
  } catch (err) {
    toast(err.message, true);
  }
}

async function uploadResume() {
  const input = document.getElementById("resumeFile");
  if (!input.files.length) {
    toast("Choose a resume file first", true);
    return;
  }
  const form = new FormData();
  form.append("file", input.files[0]);
  form.append("variant", document.getElementById("resumeVariant").value || "master");
  form.append("make_master", "true");
  try {
    toast("Parsing resume...");
    const result = await api("/api/profile/resume", { method: "POST", body: form });
    toast(`Resume parsed: ${result.skills_found} skills found`);
    input.value = "";
    loadProfile();
    loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadResumes() {
  try {
    const items = await api("/api/profile/resumes");
    document.getElementById("resumeList").innerHTML = items.length
      ? items
          .map(
            (r) => `<div class="row" style="margin:8px 0"><div><b>${escapeHtml(r.variant)}</b>${r.is_master ? ` <span class="chip have">master</span>` : ""}<div class="muted small">${escapeHtml(r.filename)} · ${r.chars} chars · ${fmtDate(r.uploaded_at)}</div></div><span class="spacer"></span>${r.is_master ? "" : `<button onclick="activateResume(${r.id})">Use as master</button>`}</div>`
          )
          .join("")
      : `<div class="empty">No resumes yet.</div>`;
  } catch (err) {
    toast(err.message, true);
  }
}

async function activateResume(id) {
  try {
    await api(`/api/profile/resumes/${id}/activate`, { method: "POST" });
    toast("Master resume updated");
    loadProfile();
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadAts() {
  try {
    const data = await api("/api/profile/ats");
    const groups = data.by_category || {};
    const keys = Object.keys(groups);
    document.getElementById("atsBox").innerHTML = keys.length
      ? keys.map((key) => `<div style="margin:8px 0"><div class="small muted">${escapeHtml(key)}</div>${groups[key].map((s) => `<span class="chip">${escapeHtml(s)}</span>`).join("")}</div>`).join("")
      : `<div class="empty">No skills detected. Check the uploaded resume.</div>`;
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- settings ----------
async function loadSettings() {
  loadSources();
  loadScheduler();
  loadGmail();
  loadLlm();
}

async function loadSources() {
  try {
    const data = await api("/api/sources");
    document.getElementById("sourceList").innerHTML = data.items
      .map(
        (s) => `<div class="job" style="margin-bottom:10px"><div class="row"><b>${escapeHtml(s.name)}</b>
          <span class="chip">${escapeHtml(s.kind)}</span><span class="spacer"></span>
          <button class="${s.enabled ? "good" : ""}" onclick="toggleSource(${s.id}, ${!s.enabled})">${s.enabled ? "Enabled" : "Disabled"}</button></div>
          <div class="muted small" style="margin-top:6px">${escapeHtml(s.notes || "")}</div>
          <div class="muted small" style="margin-top:4px">Last fetch: ${escapeHtml(s.last_status || "never")} &middot; fetched ${escapeHtml(s.last_fetched ?? 0)} &middot; added ${escapeHtml(s.last_added ?? 0)} &middot; ${escapeHtml(s.last_synced_at || "not synced")}</div>
          ${s.last_error ? `<div class="small" style="color:#b91c1c;margin-top:4px">${escapeHtml(s.last_error)}</div>` : ""}
          <details style="margin-top:6px"><summary>Config</summary><pre class="letter">${escapeHtml(JSON.stringify(s.config, null, 2))}</pre>
          <button onclick="editSource(${s.id})">Edit config JSON</button></details></div>`
      )
      .join("");
  } catch (err) {
    toast(err.message, true);
  }
}

async function toggleSource(id, enabled) {
  try {
    await api(`/api/sources/${id}`, { method: "PUT", body: JSON.stringify({ enabled }) });
    loadSources();
  } catch (err) {
    toast(err.message, true);
  }
}

const sourceCache = {};
async function editSource(id) {
  try {
    if (!sourceCache[id]) {
      const data = await api("/api/sources");
      data.items.forEach((s) => (sourceCache[s.id] = s));
    }
    const source = sourceCache[id];
    const raw = prompt("Source config JSON:", JSON.stringify(source.config || {}, null, 2));
    if (raw === null) return;
    const config = JSON.parse(raw);
    await api(`/api/sources/${id}`, { method: "PUT", body: JSON.stringify({ config }) });
    toast("Source config saved");
    loadSources();
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadScheduler() {
  try {
    const data = await api("/api/scheduler/status");
    document.getElementById("schedulerBadge").textContent = `Scheduler: ${data.running ? "running" : "stopped"}`;
    document.getElementById("schedulerBadge").className = "badge " + (data.running ? "ok" : "warn");
    document.getElementById("schedulerBox").innerHTML = `
      <div class="row"><span class="status ${data.running ? "submitted" : "draft"}">${data.running ? "running" : "stopped"}</span>
      <span class="muted small">Daily at ${escapeHtml(data.daily_at)} ${escapeHtml(data.timezone)}</span></div>
      <div class="muted small" style="margin-top:8px">${data.jobs.length ? data.jobs.map((j) => `${escapeHtml(j.id)} → ${escapeHtml(j.next_run)}`).join("<br>") : "No scheduled jobs"}</div>
      <details style="margin-top:8px"><summary>Last runs</summary><pre class="letter">${escapeHtml(JSON.stringify(data.last_runs, null, 2))}</pre></details>`;
  } catch (err) {
    toast(err.message, true);
  }
}

async function schedulerAction(action) {
  try {
    await api(`/api/scheduler/${action}`, { method: "POST" });
    toast(`Scheduler ${action} requested`);
    loadScheduler();
    if (action === "run") loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadGmail() {
  try {
    const data = await api("/api/gmail/status");
    document.getElementById("gmailBox").innerHTML = `
      <div class="row"><span class="status ${data.configured && data.libs_installed ? "submitted" : "draft"}">${data.configured ? "configured" : "not configured"}</span>
      <span class="muted small">Libraries: ${data.libs_installed ? "installed" : "missing"}</span></div>
      <div class="muted small" style="margin-top:8px">${escapeHtml(data.hint || "")}</div>`;
  } catch (err) {
    toast(err.message, true);
  }
}

async function connectGmail() {
  try {
    const data = await api("/api/gmail/auth-url");
    window.open(data.url, "_blank", "noopener");
  } catch (err) {
    toast(err.message, true);
  }
}

async function syncGmail() {
  try {
    const data = await api("/api/gmail/sync", { method: "POST" });
    toast(`Inbox synced: ${data.processed} messages, ${data.applications_updated} updated`);
    loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- global actions ----------
async function discoverNow() {
  toast("Running discovery across enabled sources...");
  try {
    const data = await api("/api/jobs/discover", { method: "POST" });
    const total = Object.values(data.sources || {}).reduce((sum, r) => sum + (r.added || 0), 0);
    toast(`Discovery finished: ${total} new jobs`);
    loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

async function rematchNow() {
  toast("Scoring jobs...");
  try {
    const data = await api("/api/matches/run", { method: "POST" });
    toast(`Scored ${data.scored} jobs`);
    loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- boot ----------
(async function boot() {
  try {
    const health = await api("/api/health");
    applyLlmInfo(health.llm || {});
    document.getElementById("schedulerBadge").textContent = `Scheduler: ${health.scheduler.running ? "running" : "stopped"}`;
    document.getElementById("schedulerBadge").className = "badge " + (health.scheduler.running ? "ok" : "warn");
  } catch (err) {
    toast("Backend not reachable", true);
  }
  loadDashboard();
})();
