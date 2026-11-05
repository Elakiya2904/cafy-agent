const $ = (id) => document.getElementById(id);
chrome.storage.sync.get({ backendUrl: "http://127.0.0.1:8000", candidateId: "local", accessToken: "" }).then((s) => {
  $("url").value = s.backendUrl;
  $("cid").value = s.candidateId;
  $("tok").value = s.accessToken;
});
$("save").addEventListener("click", async () => {
  const backendUrl = $("url").value.trim().replace(/\/+$/, "");
  const candidateId = $("cid").value.trim() || "local";
  const accessToken = $("tok").value.trim();
  try {
    const origin = new URL(backendUrl).origin + "/*";
    if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//.test(origin)) {
      const ok = await chrome.permissions.request({ origins: [origin] });
      if (!ok) { $("msg").textContent = "Permission to reach that server was denied."; return; }
    }
    await chrome.storage.sync.set({ backendUrl, candidateId, accessToken });
    $("msg").textContent = "Saved.";
  } catch (e) {
    $("msg").textContent = `Invalid URL: ${e.message}`;
  }
});
