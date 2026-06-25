"""
k8sgpt-ui — airgap troubleshooting assistant for Helm / Kubernetes.

Two modes, one chat (context kept across both):
  1. Paste error  -> model explains + suggests fix, grounded in local runbooks.
  2. Scan cluster -> runs k8sgpt (detection only, JSON), feeds findings to model.

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
KUBECONFIG = os.environ.get("KUBECONFIG", "/root/.kube/config")
RUNBOOKS_DIR = Path(os.environ.get("RUNBOOKS_DIR", "/app/runbooks"))

SYSTEM_PROMPT = (
    "You are a Kubernetes and Helm troubleshooting assistant. "
    "A user gives you an error message or cluster findings. "
    "Identify the root cause and give concrete, copy-pasteable fix steps "
    "(kubectl / helm commands, manifest changes). Be concise. "
    "If runbook context is provided, prefer it. If unsure, say so and give "
    "the most likely fix plus how to confirm it."
)


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


# ---------- ollama chat (streaming) ----------
def stream_chat(messages):
    """Yield content chunks from Ollama /api/chat."""
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": MODEL, "messages": messages, "stream": True},
        stream=True,
        timeout=600,
    )
    resp.raise_for_status()
    for line in resp.iter_lines():
        if not line:
            continue
        data = json.loads(line)
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
    """Run k8sgpt analyze with JSON output. Returns (problems:list, raw:str, err:str)."""
    cmd = [
        "k8sgpt", "analyze",
        "--output", "json",
        "--kubeconfig", KUBECONFIG,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return [], "", "k8sgpt binary not found in image."
    except subprocess.TimeoutExpired:
        return [], "", "k8sgpt timed out (cluster unreachable?)."

    out = proc.stdout.strip()
    if not out:
        return [], "", proc.stderr.strip() or "no output from k8sgpt"
    try:
        data = json.loads(out)
        return data.get("results", []), out, ""
    except json.JSONDecodeError:
        return [], out, proc.stderr.strip()


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


def send_to_model(user_content, display_content=None):
    """Append user msg, stream assistant reply, keep context."""
    st.session_state.messages.append({"role": "user", "content": user_content})
    with st.chat_message("user"):
        st.markdown(display_content or user_content)
    with st.chat_message("assistant"):
        box = st.empty()
        acc = ""
        try:
            for chunk in stream_chat(st.session_state.messages):
                acc += chunk
                box.markdown(acc)
        except Exception as e:
            acc = f"⚠️ Model error: {e}"
            box.markdown(acc)
    st.session_state.messages.append({"role": "assistant", "content": acc})


# ---------- UI ----------
st.set_page_config(page_title="k8sgpt-ui", page_icon="⎈", layout="wide")
ensure_state()
docs = load_runbooks()

with st.sidebar:
    st.title("⎈ k8sgpt-ui")
    st.caption("Airgap Helm / k8s troubleshooting")
    st.markdown(f"**Model:** `{MODEL}`")
    st.markdown(f"**Ollama:** {'🟢 up' if ollama_up() else '🔴 down'}")
    st.markdown(f"**Runbooks:** {len(docs)} loaded")
    st.divider()

    st.subheader("Scan cluster")
    st.caption("For 'something's broken but I have no error text'.")
    if st.button("🔍 Scan with k8sgpt", use_container_width=True):
        with st.spinner("Running k8sgpt..."):
            problems, raw, err = run_k8sgpt()
        if err and not problems:
            st.error(err)
        else:
            summary = findings_to_text(problems)
            st.session_state.pending_scan = summary
            st.success(f"Found {len(problems)} issue(s). See chat.")

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
    hits = retrieve(summary, docs)
    ctx = ""
    if hits:
        ctx = "\n\n---\nRunbook context:\n" + "\n\n".join(t for _, _, t in hits)
    prompt = (
        "k8sgpt scanned the cluster and reported these findings. "
        "Explain the root cause(s) and give fix steps.\n\n"
        f"{summary}{ctx}"
    )
    send_to_model(prompt, display_content="🔍 **Cluster scan results:**\n\n" + summary)

# chat input (paste-error mode)
if user_input := st.chat_input("Paste a Helm/k8s error, or ask a question..."):
    hits = retrieve(user_input, docs)
    ctx = ""
    if hits:
        ctx = "\n\n---\nRunbook context (may help):\n" + "\n\n".join(
            t for _, _, t in hits
        )
    send_to_model(user_input + ctx, display_content=user_input)
