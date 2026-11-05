/**
 * NangoConnectPanel — Gmail & Google Calendar connection UI via Nango.
 *
 * Security:
 * - Obtains a short-lived connect session token from the backend (never the secret key).
 * - The Nango frontend SDK uses that token to open the OAuth popup.
 * - No Google tokens are ever stored in the browser.
 * - Each user sees only their own connections.
 */
import React, { useCallback, useEffect, useState } from "react";
import Nango from "@nangohq/frontend";
import { Check, Loader2, Mail, Calendar, RefreshCw, X, AlertTriangle, ExternalLink } from "lucide-react";
import { getCurrentUser } from "./auth.js";

const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";

const NANGO_BASE = `${API_BASE}/api/integrations/nango`;

// These must match the integration IDs configured in your Nango workspace.
// Update these if your Nango workspace uses different IDs.
const DEFAULT_INTEGRATIONS = [
  {
    id: "gmail",
    label: "Gmail",
    description: "Read recruiter emails, draft replies, check calendar availability.",
    icon: Mail,
    color: "#EA4335",
  },
  {
    id: "google-calendar",
    label: "Google Calendar",
    description: "Create interview events and follow-up reminders.",
    icon: Calendar,
    color: "#4285F4",
  },
];

async function apiFetch(path, options = {}) {
  const res = await fetch(`${NANGO_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

function ConnectionBadge({ connection }) {
  if (!connection) return null;
  return (
    <span className="nango-badge nango-badge-ok">
      <Check size={12} /> Connected
    </span>
  );
}

function IntegrationCard({ integration, connection, onConnect, onDisconnect, busy }) {
  const Icon = integration.icon;
  const isConnected = Boolean(connection);
  const isBusy = busy === integration.id;

  return (
    <div className={`nango-card ${isConnected ? "nango-card-connected" : ""}`}>
      <div className="nango-card-header">
        <div className="nango-card-icon" style={{ color: integration.color }}>
          <Icon size={20} />
        </div>
        <div className="nango-card-info">
          <strong>{integration.label}</strong>
          <span className="nango-card-desc">{integration.description}</span>
        </div>
        {isConnected && <ConnectionBadge connection={connection} />}
      </div>

      {isConnected && connection && (
        <div className="nango-card-meta">
          <span className="nango-muted">
            Connected · ID: {connection.connection_id.slice(0, 16)}…
          </span>
          {connection.created_at && (
            <span className="nango-muted">
              Since {new Date(connection.created_at).toLocaleDateString()}
            </span>
          )}
        </div>
      )}

      <div className="nango-card-actions">
        {!isConnected ? (
          <button
            className="nango-btn nango-btn-primary"
            onClick={() => onConnect(integration.id)}
            disabled={isBusy}
          >
            {isBusy ? (
              <><Loader2 size={14} className="nango-spin" /> Connecting…</>
            ) : (
              <><ExternalLink size={14} /> Connect {integration.label}</>
            )}
          </button>
        ) : (
          <>
            <button
              className="nango-btn"
              onClick={() => onConnect(integration.id)}
              disabled={isBusy}
              title="Reconnect to refresh permissions"
            >
              {isBusy ? (
                <><Loader2 size={14} className="nango-spin" /> Reconnecting…</>
              ) : (
                <><RefreshCw size={14} /> Reconnect</>
              )}
            </button>
            <button
              className="nango-btn nango-btn-danger"
              onClick={() => onDisconnect(connection)}
              disabled={isBusy}
            >
              <X size={14} /> Disconnect
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function NangoConnectPanel({ onStatusChange }) {
  const [integrations, setIntegrations] = useState(DEFAULT_INTEGRATIONS);
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState(null);
  const [configured, setConfigured] = useState(true);

  const notify = useCallback((text, kind = "ok") => {
    setToast({ text, kind });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const data = await apiFetch("/status");
      setConfigured(data.configured !== false);
      setConnections(data.connections || []);
      onStatusChange?.(data.connections || []);
      const configured = await apiFetch("/integrations");
      const discovered = (configured.integrations || []).filter((item) => {
        const searchable = `${item.unique_key || ""} ${item.provider || ""} ${item.display_name || ""}`;
        return item.unique_key && !/github|microsoft|outlook/i.test(searchable);
      });
      if (discovered.length > 0) {
        const discoveredIntegrations = discovered.map((item) => ({
          id: item.unique_key,
          label: item.display_name || item.unique_key,
          description: `${item.provider || "Configured"} integration`,
          icon: /calendar/i.test(`${item.unique_key} ${item.display_name}`) ? Calendar : Mail,
          color: /calendar/i.test(`${item.unique_key} ${item.display_name}`) ? "#4285F4" : "#EA4335",
        }));
        setIntegrations(discoveredIntegrations);
      }
    } catch (err) {
      if (err.status === 503) {
        setConfigured(false);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [onStatusChange]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const handleConnect = async (integrationId) => {
    setBusy(integrationId);
    setError("");
    try {
      const user = getCurrentUser();
      const displayName = user?.full_name;
      // 1. Get a short-lived connect session token from our backend.
      const { session_token } = await apiFetch("/connect-session", {
        method: "POST",
        body: JSON.stringify({
          allowed_integrations: [integrationId],
          display_name: displayName || undefined,
          email: user?.email || undefined,
        }),
      });

      // 2. Open the Nango OAuth popup using the session token.
      //    The secret key is NEVER used here — only the session token.
      const nango = new Nango({ connectSessionToken: session_token });
      await nango.auth(integrationId);

      notify(`${integrationId} connected successfully.`, "ok");
      await loadStatus();
    } catch (err) {
      // Nango throws an AuthError if the user closes the popup.
      if (err?.type === "user_cancelled" || err?.message?.includes("cancelled")) {
        notify("Connection cancelled.", "info");
      } else {
        const msg = err?.message || "Connection failed. Please try again.";
        setError(msg);
        notify(msg, "error");
      }
    } finally {
      setBusy("");
    }
  };

  const handleDisconnect = async (connection) => {
    if (!window.confirm(`Disconnect ${connection.integration_id}? Cafy will lose access to this account.`)) return;
    setBusy(connection.integration_id);
    try {
      await apiFetch(
        `/connections/${encodeURIComponent(connection.connection_id)}?integration_id=${encodeURIComponent(connection.integration_id)}`,
        { method: "DELETE" }
      );
      notify(`${connection.integration_id} disconnected.`, "ok");
      await loadStatus();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy("");
    }
  };

  const getConnection = (integrationId) =>
    connections.find((c) => c.integration_id === integrationId) || null;

  if (loading) {
    return (
      <div className="nango-panel">
        <div className="nango-loading">
          <Loader2 size={16} className="nango-spin" /> Loading integrations…
        </div>
      </div>
    );
  }

  if (!configured) {
    return (
      <div className="nango-panel">
        <div className="nango-unconfigured">
          <AlertTriangle size={18} />
          <div>
            <strong>Nango is not configured</strong>
            <p>Add <code>NANGO_SECRET_KEY</code> to the backend environment to enable Gmail and Calendar connections.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="nango-panel">
      {toast && (
        <div className={`nango-toast nango-toast-${toast.kind}`} role="status">
          {toast.text}
          <button aria-label="Dismiss" onClick={() => setToast(null)}><X size={13} /></button>
        </div>
      )}

      {error && (
        <div className="nango-error">
          <AlertTriangle size={14} /> {error}
          <button onClick={() => setError("")}><X size={13} /></button>
        </div>
      )}

      <div className="nango-cards">
        {integrations.map((integration) => (
          <IntegrationCard
            key={integration.id}
            integration={integration}
            connection={getConnection(integration.id)}
            onConnect={handleConnect}
            onDisconnect={handleDisconnect}
            busy={busy}
          />
        ))}
      </div>
    </div>
  );
}
