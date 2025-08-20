#!/usr/bin/env python3
"""Minimal Streamlit GUI for EDU ASR.

This app wraps the CLI functionality with a simple form so that
non-technical users can batch-transcribe files from either:
- an rclone remote + path
- a local input folder
- a local scratch folder

Outputs are written to the chosen output folder. The app runs
locally and requires `streamlit` (added to requirements).
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import List, Optional

import streamlit as st


APP_STATE_DIR = Path.home() / ".eduasr"
APP_STATE_DIR.mkdir(parents=True, exist_ok=True)
HF_TOKEN_FILE_HOME = APP_STATE_DIR / "hf_token"
HF_TOKEN_FILE_LOCAL = Path("hf")


def read_text_safely(path: Path) -> Optional[str]:
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            return value or None
    except Exception:
        return None
    return None


def load_hf_token() -> Optional[str]:
    # Prefer environment variable
    env_token = os.environ.get("HF_TOKEN")
    if env_token:
        return env_token.strip()
    # Then user-level file
    token = read_text_safely(HF_TOKEN_FILE_HOME)
    if token:
        return token
    # Finally local project file (ignored by git)
    token = read_text_safely(HF_TOKEN_FILE_LOCAL)
    if token:
        return token
    return None


def save_hf_token(token: str, location: str) -> Path:
    target = HF_TOKEN_FILE_HOME if location == "home" else HF_TOKEN_FILE_LOCAL
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(token.strip() + "\n", encoding="utf-8")
        try:
            target.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
        except Exception:
            pass
    except Exception:
        pass
    return target


def list_rclone_remotes() -> List[str]:
    """Parse rclone.conf if available and return remote names."""
    config_path = Path.home() / ".config" / "rclone" / "rclone.conf"
    if not config_path.exists():
        return []
    remotes: List[str] = []
    try:
        for line in config_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                remotes.append(line[1:-1])
    except Exception:
        return []
    return remotes


def run_command(command: List[str], env: Optional[dict] = None) -> int:
    """Run a subprocess command, stream output to the UI, and return exit code."""
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env=env,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            st.write(line.rstrip())
        return proc.wait()


def build_cli_args(values: dict) -> List[str]:
    """Translate form values into CLI arguments for `python -m eduasr.cli transcribe`."""
    args: List[str] = [
        "python", "-m", "eduasr.cli", "transcribe",
        "--output_dir", values["output_dir"],
    ]

    # Source selection
    source_mode = values["source_mode"]
    if source_mode == "rclone":
        args += [
            "--rclone-remote", values["rclone_remote"],
            "--remote-path", values["remote_path"],
            "--scratch-dir", values["scratch_dir"],
        ]
    elif source_mode == "local_input":
        args += ["--input_dir", values["input_dir"]]
    else:  # scratch_only
        args += ["--scratch-dir", values["scratch_dir"]]

    # Optional fields
    if values["include_ext"]:
        args += ["--include-ext", values["include_ext"]]
    if values["max_files"]:
        args += ["--max-files", str(values["max_files"]) ]
    if values["config_path"]:
        args += ["--config", values["config_path"]]
    if values["model_size"]:
        args += ["--model", values["model_size"]]
    if values["force_reprocess"]:
        args += ["--force"]
    if values["wait_if_low_disk"]:
        args += ["--wait-if-low-disk"]
    if values["min_free_gb"]:
        args += ["--min-free-gb", str(values["min_free_gb"]) ]
    if values["run_log"]:
        args += ["--run-log", values["run_log"]]

    return args


def main() -> None:
    st.set_page_config(page_title="EDU ASR", layout="wide")
    st.title("EDU ASR – Transcription GUI")
    st.caption("A simple UI that wraps the CLI")

    with st.sidebar:
        st.header("Configuration")
        config_path = st.text_input("Config file (optional)", value="config.yaml")
        model_size = st.selectbox(
            "Model size",
            ["", "tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large", "large-v1", "large-v2", "large-v3"],
            index=3,
        )
        include_ext = st.text_input("Include extensions", value=".mov,.mp4,.m4a,.wav")
        max_files = st.number_input("Max files", min_value=0, step=1, value=0,
                                    help="0 means no limit")
        force_reprocess = st.checkbox("Force reprocess existing files", value=False)

        st.header("Disk safety")
        wait_if_low_disk = st.checkbox("Wait if low disk", value=True)
        min_free_gb = st.number_input("Minimum free GB", min_value=0.0, step=1.0, value=10.0)

        st.header("Logging")
        run_log = st.text_input("Run log CSV", value="out/run_log.csv")

        st.header("Hugging Face token")
        existing_token = load_hf_token() or ""
        hf_token = st.text_input("HF_TOKEN", value=existing_token, type="password",
                                 help="Personal access token starting with hf_…")
        save_loc = st.radio("Save token to", options=["home", "project"],
                            format_func=lambda v: "User profile (~/.eduasr/hf_token)" if v == "home" else "Project file (./hf)",
                            horizontal=False)
        if st.button("Save HF token"):
            if hf_token.strip():
                target = save_hf_token(hf_token, save_loc)
                st.success(f"Saved token to {target}")
            else:
                st.warning("Enter a token first")

    st.subheader("Source")
    source_mode = st.radio(
        "Choose source",
        options=["rclone", "local_input", "scratch_only"],
        format_func=lambda x: {
            "rclone": "Rclone remote",
            "local_input": "Local input folder",
            "scratch_only": "Scratch folder",
        }[x],
        horizontal=True,
    )

    cols = st.columns(3)
    with cols[0]:
        if "output_dir" not in st.session_state:
            st.session_state["output_dir"] = "out"
        output_dir = st.text_input("Output folder", key="output_dir")
        if st.button("Choose…", key="choose_output"):
            # Open a native folder chooser (local app only)
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                initial = st.session_state.get("output_dir") or os.getcwd()
                path = filedialog.askdirectory(initialdir=initial)
                root.destroy()
                if path:
                    st.session_state["output_dir"] = path
                    output_dir = path
            except Exception:
                st.warning("Folder chooser unavailable; enter a path manually.")
        config_output = st.text_input("Config file (again)", value=config_path, help="Optional; leave as-is")
    with cols[1]:
        if "input_dir" not in st.session_state:
            st.session_state["input_dir"] = ""
        if "scratch_dir" not in st.session_state:
            st.session_state["scratch_dir"] = "scratch"
        input_dir = st.text_input("Local input folder", key="input_dir")
        if st.button("Choose…", key="choose_input"):
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                initial = st.session_state.get("input_dir") or os.getcwd()
                path = filedialog.askdirectory(initialdir=initial)
                root.destroy()
                if path:
                    st.session_state["input_dir"] = path
                    input_dir = path
            except Exception:
                st.warning("Folder chooser unavailable; enter a path manually.")
        scratch_dir = st.text_input("Scratch folder", key="scratch_dir")
        if st.button("Choose…", key="choose_scratch"):
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                initial = st.session_state.get("scratch_dir") or os.getcwd()
                path = filedialog.askdirectory(initialdir=initial)
                root.destroy()
                if path:
                    st.session_state["scratch_dir"] = path
                    scratch_dir = path
            except Exception:
                st.warning("Folder chooser unavailable; enter a path manually.")
    with cols[2]:
        remotes = list_rclone_remotes()
        if remotes:
            rclone_remote = st.selectbox("Rclone remote name", options=[""] + remotes)
        else:
            rclone_remote = st.text_input("Rclone remote name", value="")
        remote_path = st.text_input("Remote path", value="")

    values = dict(
        output_dir=output_dir,
        input_dir=input_dir,
        scratch_dir=scratch_dir,
        rclone_remote=rclone_remote,
        remote_path=remote_path,
        include_ext=include_ext,
        max_files=int(max_files) if max_files else 0,
        config_path=config_output or config_path,
        model_size=model_size,
        force_reprocess=force_reprocess,
        wait_if_low_disk=wait_if_low_disk,
        min_free_gb=float(min_free_gb) if min_free_gb else 0.0,
        run_log=run_log,
        source_mode=source_mode,
    )

    st.divider()
    if st.button("Start Transcription", type="primary"):
        # Ensure output dir exists
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        if source_mode != "local_input":
            Path(scratch_dir).mkdir(parents=True, exist_ok=True)

        cmd = build_cli_args(values)
        st.code(" ".join(cmd))

        env = os.environ.copy()
        # Provide HF_TOKEN to the subprocess
        # Priority: user input > env > files
        if hf_token.strip():
            env["HF_TOKEN"] = hf_token.strip()
        elif os.environ.get("HF_TOKEN"):
            env["HF_TOKEN"] = os.environ["HF_TOKEN"].strip()
        else:
            token = load_hf_token()
            if token:
                env["HF_TOKEN"] = token

        exit_code = run_command(cmd, env=env)
        if exit_code == 0:
            st.success("Done!")
        else:
            st.error(f"Command exited with status {exit_code}")


if __name__ == "__main__":
    main()


