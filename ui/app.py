"""
k8sgpt-ui — airgap troubleshooting assistant for Helm / Kubernetes.

Two modes, one chat (context kept across both):
  1. Paste error  -> model explains + suggests fix.
  2. Scan cluster -> runs k8sgpt (detection only, JSON), feeds findings to model.

Runbooks are NOT injected automatically — browse them in the sidebar, or turn on
"Ground answers in runbooks" to let the model use the relevant ones as context.

Talks to a local Ollama for the model. k8sgpt runs as a subprocess (binary baked
into the image). No internet required at runtime.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import requests
import streamlit as st

# --- config (env-overridable) ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
MODEL = os.environ.get("MODEL", "qwen2.5-coder:7b")
RUNBOOKS_DIR = Path(os.environ.get("RUNBOOKS_DIR", "/app/runbooks"))
# where an uploaded kubeconfig is written (writable, survives reruns within session)
UPLOAD_KUBECONFIG = os.environ.get("UPLOAD_KUBECONFIG", "/tmp/uploaded-kubeconfig")
# Ollama tuning: bigger context avoids 500s on long scans; keep_alive avoids reloads.
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
# cap how many past messages we resend each turn (bounds latency + context growth)
MAX_HISTORY = int(os.environ.get("MAX_HISTORY_MESSAGES", "16"))

SYSTEM_PROMPT = (
    "You are a Kubernetes and Helm troubleshooting assistant. "
    "A user gives you an error message or cluster findings. "
    "Identify the root cause and give concrete, copy-pasteable fix steps "
    "(kubectl / helm commands, manifest changes). Be concise. "
    "If runbook context is provided, prefer it. If unsure, say so and give "
    "the most likely fix plus how to confirm it. "
    "Do NOT paste whole runbooks back to the user; answer their question directly."
)


# ---------- kubeconfig discovery ----------
def kubeconfig_candidates():
    """Common kubeconfig locations, in priority order. $KUBECONFIG may be a list."""
    cands = []
    env = os.environ.get("KUBECONFIG", "")
    for p in env.split(os.pathsep):
        if p.strip():
            cands.append(p.strip())
    home = os.path.expanduser("~")
    cands += [
        os.path.join(home, ".kube", "config"),
        "/root/.kube/config",
        "/home/user/.kube/config",
        "/etc/kubernetes/admin.conf",
    ]
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def discovered_kubeconfig():
    """First existing kubeconfig among the common locations, else None."""
    for c in kubeconfig_candidates():
        if os.path.isfile(c):
            return c
    return None


def active_kubeconfig():
    """Uploaded kubeconfig wins; else the first discovered default. Returns path or None."""
    up = st.session_state.get("kubeconfig_path")
    if up and os.path.isfile(up):
        return up
    return discovered_kubeconfig()


# ---------- runbook retrieval (naive keyword match, airgap-friendly) ----------
def load_runbooks():
    docs = []
    if RUNBOOKS_DIR.is_dir():
        for p in sorted(RUNBOOKS_DIR.glob("*.md")):
            docs.append((p.name, p.read_text(encoding="utf-8", errors="ignore")))
    return docs


def retrieve(query, docs, k=3):
    """Score docs by overlap of query word-stems with doc text. Cheap, no embeddings."""
    words = {w for w in re.findall(r"[a-zA-Z0-9.-]{3,}", query.lower())}
    scored = []
    for name, text in docs:
        low = text.lower()
        score = sum(low.count(w) for w in words)
        if score:
            scored.append((score, name, text))
    scored.sort(reverse=True)
    return scored[:k]


def runbook_context(query, docs):
    """Return (context_str, names) for the top runbooks, or ('', []) if none."""
    hits = retrieve(query, docs)
    if not hits:
        return "", []
    names = [n for _, n, _ in hits]
    ctx = "\n\n---\nRunbook context (reference only, do not echo verbatim):\n" + "\n\n".join(
        t for _, _, t in hits
    )
    return ctx, names


# ---------- ollama chat (streaming) ----------
def stream_chat(messages):
    """Yield content chunks from Ollama /api/chat. Raises RuntimeError with a useful
    message on HTTP errors (e.g. 500) instead of a bare status."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_ctx": NUM_CTX},
    }
    resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, stream=True, timeout=600)
    if resp.status_code != 200:
        try:
            msg = resp.json().get("error") or resp.text
        except Exception:
            msg = resp.text
        raise RuntimeError(f"Ollama HTTP {resp.status_code}: {msg.strip()[:500]}")
    for line in resp.iter_lines():
        if not line:
            continue
        data = json.loads(line)
        if data.get("error"):
            raise RuntimeError(f"Ollama: {data['error']}")
        chunk = data.get("message", {}).get("content", "")
        if chunk:
            yield chunk


def ollama_up():
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).raise_for_status()
        return True
    except Exception:
        return False


# ---------- k8sgpt scan (detection only, no AI backend) ----------
def run_k8sgpt():
    """Run k8sgpt analyze with JSON output.
    Returns (problems:list, raw:str, err:str). `err` carries stderr/diagnostics even
    when problems are found, so the UI can always surface it."""
    kubeconfig = active_kubeconfig()
    if not kubeconfig:
        return [], "", (
            "No kubeconfig found. Upload one in the sidebar, or mount it to a standard "
            "path (~/.kube/config, /root/.kube/config)."
        )
    cmd = ["k8sgpt", "analyze", "--output", "json", "--kubeconfig", kubeconfig]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return [], "", "k8sgpt binary not found in image."
    except subprocess.TimeoutExpired:
        return [], "", "k8sgpt timed out after 120s (cluster unreachable / token expired?)."

    out = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if not out:
        return [], "", stderr or f"k8sgpt produced no output (exit {proc.returncode})."
    try:
        data = json.loads(out)
        # stderr returned as non-fatal diagnostics (e.g. deprecation warnings)
        return data.get("results", []), out, stderr
    except json.JSONDecodeError:
        return [], out, stderr or "k8sgpt output was not valid JSON."


def findings_to_text(problems):
    if not problems:
        return "k8sgpt found no problems in the cluster."
    lines = []
    for r in problems:
        kind = r.get("kind", "?")
        name = r.get("name", "?")
        lines.append(f"### {kind}/{name}")
        for e in r.get("error", []):
            txt = e.get("Text") if isinstance(e, dict) else str(e)
            lines.append(f"- {txt}")
    return "\n".join(lines)


# ---------- chat plumbing ----------
def ensure_state():
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]


def visible_messages():
    return [m for m in st.session_state.messages if m["role"] != "system"]


def trimmed_messages():
    """System prompt + the last MAX_HISTORY non-system messages. Bounds prompt size
    so long sessions don't overflow context or crawl."""
    msgs = st.session_state.messages
    system = [m for m in msgs if m["role"] == "system"][:1]
    rest = [m for m in msgs if m["role"] != "system"]
    return system + rest[-MAX_HISTORY:]


def _stream_into(box, sent):
    acc = ""
    for chunk in stream_chat(sent):
        acc += chunk
        box.markdown(acc)
    return acc


def send_to_model(user_content, display_content=None, extra_context=None):
    """Append clean user msg to history, stream assistant reply.

    `extra_context` (e.g. runbook text) is attached to THIS request only and is never
    stored in history — keeps the conversation lean and stops it being resent forever.
    """
    st.session_state.messages.append({"role": "user", "content": user_content})
    with st.chat_message("user"):
        st.markdown(display_content or user_content)

    sent = trimmed_messages()
    if extra_context:
        last = sent[-1]
        sent = sent[:-1] + [{**last, "content": last["content"] + extra_context}]

    with st.chat_message("assistant"):
        box = st.empty()
        acc = ""
        try:
            acc = _stream_into(box, sent)
        except Exception:
            # one retry — covers cold model-load 500s and transient hiccups
            box.markdown("⏳ Model busy or loading — retrying once…")
            try:
                acc = _stream_into(box, sent)
            except Exception as e:
                acc = f"⚠️ Model error: {e}"
                box.markdown(acc)
    st.session_state.messages.append({"role": "assistant", "content": acc})


# ---------- UI ----------
st.set_page_config(page_title="k8sgpt-ui", page_icon="⎈", layout="wide")
ensure_state()
docs = load_runbooks()


@st.dialog("📖 Runbooks & docs", width="large")
def runbooks_dialog(all_docs):
    """Wide pop-up to browse and read runbooks comfortably (vs. the narrow sidebar)."""
    # Streamlit caps dialog width at "large" (~800px); widen it via CSS to ~90% viewport.
    st.markdown(
        "<style>div[role='dialog']{width:92vw !important;max-width:1500px !important;}</style>",
        unsafe_allow_html=True,
    )
    if not all_docs:
        st.info("No runbooks found.")
        return
    names = [n for n, _ in all_docs]
    sel = st.selectbox("Choose a runbook", names, key="rb_dialog_sel")
    st.divider()
    st.markdown(dict(all_docs).get(sel, ""))

with st.sidebar:
    st.title("⎈ k8sgpt-ui")
    st.caption("Airgap Helm / k8s troubleshooting")
    st.markdown(f"**Model:** `{MODEL}`")
    st.markdown(f"**Ollama:** {'🟢 up' if ollama_up() else '🔴 down'}")
    st.markdown(f"**Runbooks:** {len(docs)} loaded")
    st.divider()

    st.subheader("Kubeconfig")
    up = st.file_uploader(
        "Upload kubeconfig (overrides the default)",
        type=None,
        help="Used only by k8sgpt to read the cluster. If none is uploaded, common "
        "locations like ~/.kube/config are used automatically.",
    )
    if up is not None:
        with open(UPLOAD_KUBECONFIG, "wb") as f:
            f.write(up.getbuffer())
        os.chmod(UPLOAD_KUBECONFIG, 0o600)
        st.session_state.kubeconfig_path = UPLOAD_KUBECONFIG
        st.success(f"Loaded: {up.name}")

    active = active_kubeconfig()
    if active:
        src = "uploaded" if active == st.session_state.get("kubeconfig_path") else "auto-detected"
        st.caption(f"🟢 kubeconfig active ({src}): `{active}`")
    else:
        st.caption("⚪ no kubeconfig found — scan disabled, paste mode works")

    st.divider()

    st.subheader("Scan cluster")
    st.caption("Runs k8sgpt to auto-detect problems in the cluster (no error text needed).")
    if st.button("🔍 Scan with k8sgpt", use_container_width=True, disabled=active is None):
        with st.spinner("Running k8sgpt..."):
            problems, raw, err = run_k8sgpt()
        st.session_state.last_scan_raw = raw
        st.session_state.last_scan_err = err
        if not raw and err:
            st.error(f"k8sgpt failed:\n\n{err}")
        else:
            st.session_state.pending_scan = findings_to_text(problems)
            st.success(f"Found {len(problems)} issue(s). See chat.")
            if err:
                st.warning("k8sgpt reported warnings — see diagnostics below.")

    if st.session_state.get("last_scan_raw") or st.session_state.get("last_scan_err"):
        with st.expander("🛠️ Last scan diagnostics"):
            if st.session_state.get("last_scan_err"):
                st.caption("stderr / messages:")
                st.code(st.session_state["last_scan_err"])
            if st.session_state.get("last_scan_raw"):
                st.caption("raw k8sgpt JSON:")
                st.code(st.session_state["last_scan_raw"][:5000], language="json")

    st.divider()

    st.subheader("Runbooks")
    st.session_state.ground_runbooks = st.toggle(
        "Ground answers in runbooks",
        value=False,
        help="Off by default. When on, the most relevant runbook(s) are given to the "
        "model as background context for your question — they are not printed to chat.",
    )
    if st.button(f"📖 Open runbooks ({len(docs)})", use_container_width=True):
        runbooks_dialog(docs)

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.rerun()

st.title("Helm / Kubernetes troubleshooter")

# replay history
for m in visible_messages():
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# handle a queued cluster scan
if "pending_scan" in st.session_state:
    summary = st.session_state.pop("pending_scan")
    prompt = (
        "k8sgpt scanned the cluster and reported these findings. "
        "Explain the root cause(s) and give fix steps.\n\n"
        f"{summary}"
    )
    extra, used = ("", [])
    if st.session_state.get("ground_runbooks"):
        extra, used = runbook_context(summary, docs)
    send_to_model(
        prompt,
        display_content="🔍 **Cluster scan results:**\n\n" + summary,
        extra_context=extra or None,
    )
    if used:
        st.caption("📖 Grounded in runbooks: " + ", ".join(used))

# chat input (paste-error mode)
if user_input := st.chat_input("Paste a Helm/k8s error, or ask a question..."):
    extra, used = ("", [])
    if st.session_state.get("ground_runbooks"):
        extra, used = runbook_context(user_input, docs)
    send_to_model(user_input, display_content=user_input, extra_context=extra or None)
    if used:
        st.caption("📖 Grounded in runbooks: " + ", ".join(used))
