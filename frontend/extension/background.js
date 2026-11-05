// Service worker: all calls to the Cafy backend go through here so the content
// script (which runs inside the employer's page) never holds the settings.
const DEFAULTS = { backendUrl: "http://127.0.0.1:8000", candidateId: "local", accessToken: "" };

async function settings() {
  const s = await chrome.storage.sync.get(DEFAULTS);
  return { backendUrl: (s.backendUrl || DEFAULTS.backendUrl).replace(/\/+$/, ""), candidateId: s.candidateId || DEFAULTS.candidateId, accessToken: s.accessToken || "" };
}

function toBase64(buf) {
  let bin = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

async function api({ path, method = "GET", body, binary }) {
  const { backendUrl, candidateId, accessToken } = await settings();
  try {
    const res = await fetch(`${backendUrl}/api/job-applications${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        // Signed-in servers identify you from the token; X-Candidate-Id only applies to a local dev server.
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : { "X-Candidate-Id": candidateId }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (binary) {
      if (!res.ok) return { ok: false, status: res.status, data: await res.json().catch(() => ({})) };
      return { ok: true, status: res.status, base64: toBase64(await res.arrayBuffer()), contentType: res.headers.get("content-type") };
    }
    return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
  } catch (err) {
    return { ok: false, status: 0, network: true, data: { detail: { message: `Cannot reach Cafy at ${backendUrl}: ${err.message}` } } };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "api") {
    api(msg).then(sendResponse);
    return true; // async response
  }
  if (msg && msg.type === "settings") {
    settings().then(sendResponse);
    return true;
  }
  return false;
});

// Generic forms: the user clicks the toolbar button to activate Cafy on the current page.
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
});
