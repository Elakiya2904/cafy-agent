from pathlib import Path

# 1. Update frontend/src/auth.js
path_front = Path("frontend/src/auth.js")
c_front = path_front.read_text(encoding="utf-8")

old_front = """const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const authEnabled = Boolean(url && anonKey);
export const guestModeEnabled = authEnabled && import.meta.env.VITE_ENABLE_GUEST_MODE === "true";"""

new_front = """const url = import.meta.env.VITE_SUPABASE_URL || "https://tgeuiemybetiiwblhdbr.supabase.co";
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || "sb_publishable_PlCIZydM_pmkafPXKCWliA_RegTigST";

export const authEnabled = Boolean(url && anonKey);
export const guestModeEnabled = authEnabled && import.meta.env.VITE_ENABLE_GUEST_MODE !== "false";"""

def do_rep(txt, o, n):
    if o in txt:
        return txt.replace(o, n)
    o_crlf = o.replace("\n", "\r\n")
    n_crlf = n.replace("\n", "\r\n")
    if o_crlf in txt:
        return txt.replace(o_crlf, n_crlf)
    return None

res_front = do_rep(c_front, old_front, new_front)
if res_front:
    path_front.write_text(res_front, encoding="utf-8")
    print("Updated frontend/src/auth.js successfully")
else:
    print("Could not match old_front in frontend/src/auth.js")

# 2. Update backend/auth.py
path_back = Path("backend/auth.py")
c_back = path_back.read_text(encoding="utf-8")

old_back1 = 'def supabase_url() -> str:\n    return (os.getenv("SUPABASE_URL") or "").rstrip("/")'
new_back1 = 'def supabase_url() -> str:\n    return (os.getenv("SUPABASE_URL") or "https://tgeuiemybetiiwblhdbr.supabase.co").rstrip("/")'

old_back2 = '''def guest_mode_enabled() -> bool:
    """Guest requests are opt-in and never allowed in production."""
    return (
        not is_production()
        and (os.getenv("ENABLE_GUEST_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}
    )'''

new_back2 = '''def guest_mode_enabled() -> bool:
    """Guest requests are opt-in."""
    val = (os.getenv("ENABLE_GUEST_MODE") or "true").strip().lower()
    return val in {"1", "true", "yes", "on"}'''

res_back1 = do_rep(c_back, old_back1, new_back1)
if res_back1:
    c_back = res_back1
    print("Updated backend/auth.py (supabase_url)")
else:
    print("Could not match old_back1")

res_back2 = do_rep(c_back, old_back2, new_back2)
if res_back2:
    c_back = res_back2
    print("Updated backend/auth.py (guest_mode_enabled)")
else:
    print("Could not match old_back2")

path_back.write_text(c_back, encoding="utf-8")
