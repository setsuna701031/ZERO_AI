from __future__ import annotations

import io
import random
import sys
import tkinter as tk
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import ttk
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

from core.persona.chat_shell import generate_rule_based_response
from core.persona.loader import load_default_persona
from core.persona.panel_renderer import render_persona_panel
from core.persona.state_manager import get_persona_state_manager
from core.persona.visual_profile import load_default_visual_profile


BG_MAIN = "#0b1220"
BG_CARD = "#121a2b"
BG_CHAT = "#0d1522"
FG_MAIN = "#e8eef8"
FG_MUTED = "#9fb0c7"
ACCENT = "#54d18f"
ACCENT_BLUE = "#6aa6ff"
ACCENT_WARN = "#ffb86b"
ACCENT_ERR = "#ff6b6b"
BORDER = "#243248"

# Blink remains disabled until all blink frames share the exact same transparent canvas,
# crop boundary, character scale, and anchor position.
ENABLE_BLINK = False


class PersonaRuntimeWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ZERO Persona Runtime")
        self.root.geometry("1460x920")
        self.root.minsize(1320, 840)
        self.root.configure(bg=BG_MAIN)

        self.persona = load_default_persona()
        self.visual_profile = load_default_visual_profile()
        self.state_manager = get_persona_state_manager()

        self.state_manager.set_idle(
            reason="ui_startup",
            source="persona_runtime_window",
            detail="persona runtime window boot completed",
            last_result="ui_ready",
        )

        self._visual_photo: Optional[object] = None
        self._blink_job: Optional[str] = None
        self._blink_active = False
        self._blink_sequence: list[str] = []
        self._blink_index = 0
        self._resize_job: Optional[str] = None
        self._panel_visible = False
        self.panel_popup: Optional[tk.Toplevel] = None

        self.current_state_var = tk.StringVar()
        self.reason_var = tk.StringVar()
        self.source_var = tk.StringVar()
        self.detail_var = tk.StringVar()
        self.last_capability_var = tk.StringVar()
        self.last_result_var = tk.StringVar()
        self.last_task_id_var = tk.StringVar()
        self.last_output_hint_var = tk.StringVar()
        self.image_path_var = tk.StringVar()
        self.persona_summary_var = tk.StringVar()
        self.runtime_summary_var = tk.StringVar()

        self._configure_styles()
        self._build_ui()
        self._refresh_all_views()
        self._append_message("ZERO", self.persona.greeting)

        if ENABLE_BLINK:
            self._schedule_next_blink()

        self.root.bind("<Configure>", self._on_window_resize)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=BG_MAIN, foreground=FG_MAIN, fieldbackground=BG_CARD)
        style.configure("Header.TLabel", background=BG_MAIN, foreground=FG_MAIN, font=("Segoe UI", 24, "bold"))
        style.configure("SubHeader.TLabel", background=BG_MAIN, foreground=FG_MUTED, font=("Segoe UI", 10))
        style.configure("Quick.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Send.TButton", font=("Segoe UI", 10, "bold"))

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG_MAIN, padx=14, pady=14)
        outer.pack(fill="both", expand=True)

        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=8)
        outer.grid_rowconfigure(1, weight=3)

        top = tk.Frame(outer, bg=BG_MAIN)
        top.grid(row=0, column=0, sticky="nsew")
        top.grid_columnconfigure(0, weight=5)
        top.grid_columnconfigure(1, weight=6)
        top.grid_rowconfigure(0, weight=1)

        bottom = tk.Frame(outer, bg=BG_MAIN)
        bottom.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=4)
        bottom.grid_columnconfigure(1, weight=4)
        bottom.grid_columnconfigure(2, weight=6)
        bottom.grid_rowconfigure(0, weight=1)

        self._build_left_visual(top)
        self._build_right_dashboard(top)
        self._build_bottom_area(bottom)

    def _build_left_visual(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=BG_MAIN)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        header = tk.Frame(left, bg=BG_MAIN)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="ZERO Persona Runtime", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="Local persona runtime window", style="SubHeader.TLabel").pack(anchor="w", pady=(2, 0))

        image_card = tk.Frame(left, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        image_card.grid(row=1, column=0, sticky="nsew")
        image_card.grid_rowconfigure(1, weight=1)
        image_card.grid_columnconfigure(0, weight=1)

        topbar = tk.Frame(image_card, bg=BG_CARD)
        topbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        tk.Label(topbar, text="Persona Visual", bg=BG_CARD, fg=FG_MAIN, font=("Segoe UI", 12, "bold")).pack(
            side="left"
        )

        self.state_badge = tk.Label(
            topbar,
            text="IDLE",
            bg="#1b2a41",
            fg=ACCENT_BLUE,
            padx=12,
            pady=6,
            font=("Segoe UI", 10, "bold"),
        )
        self.state_badge.pack(side="right")

        self.image_area = tk.Frame(image_card, bg=BG_CARD)
        self.image_area.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.image_area.grid_rowconfigure(0, weight=1)
        self.image_area.grid_columnconfigure(0, weight=1)

        self.visual_canvas = tk.Canvas(
            self.image_area,
            bg=BG_CHAT,
            highlightthickness=0,
            bd=0,
        )
        self.visual_canvas.grid(row=0, column=0, sticky="nsew")

    def _build_right_dashboard(self, parent: tk.Frame) -> None:
        right = tk.Frame(parent, bg=BG_MAIN)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        status_card = tk.Frame(right, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        status_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_card.grid_columnconfigure(1, weight=1)

        tk.Label(status_card, text="Current Status", bg=BG_CARD, fg=FG_MAIN, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 8)
        )
        self._add_status_row(status_card, 1, "State", self.current_state_var)
        self._add_status_row(status_card, 2, "Reason", self.reason_var)
        self._add_status_row(status_card, 3, "Source", self.source_var)
        self._add_status_row(status_card, 4, "Detail", self.detail_var)

        runtime_card = tk.Frame(right, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        runtime_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        runtime_card.grid_columnconfigure(1, weight=1)

        tk.Label(runtime_card, text="Runtime Summary", bg=BG_CARD, fg=FG_MAIN, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 8)
        )
        self._add_status_row(runtime_card, 1, "Last Capability", self.last_capability_var)
        self._add_status_row(runtime_card, 2, "Last Result", self.last_result_var)
        self._add_status_row(runtime_card, 3, "Last Task ID", self.last_task_id_var)
        self._add_status_row(runtime_card, 4, "Output Hint", self.last_output_hint_var)

        chat_card = tk.Frame(right, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        chat_card.grid(row=2, column=0, sticky="nsew")
        chat_card.grid_rowconfigure(1, weight=1)
        chat_card.grid_columnconfigure(0, weight=1)

        header = tk.Frame(chat_card, bg=BG_CARD)
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))
        tk.Label(header, text="Chat / Command", bg=BG_CARD, fg=FG_MAIN, font=("Segoe UI", 12, "bold")).pack(
            side="left"
        )

        toggle_text = tk.StringVar(value="Show Panel")
        self.panel_toggle_text = toggle_text
        ttk.Button(header, textvariable=toggle_text, style="Quick.TButton", command=self._toggle_panel_popup).pack(
            side="right"
        )

        self.chat_text = tk.Text(
            chat_card,
            wrap="word",
            font=("Segoe UI", 10),
            bg=BG_CHAT,
            fg="#d7e2f0",
            insertbackground="#d7e2f0",
            relief="flat",
            padx=12,
            pady=12,
        )
        self.chat_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.chat_text.configure(state="disabled")
        self._configure_chat_tags()

        input_frame = tk.Frame(chat_card, bg=BG_CARD)
        input_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        input_frame.grid_columnconfigure(0, weight=1)

        self.command_entry = ttk.Entry(input_frame, font=("Segoe UI", 10))
        self.command_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.command_entry.bind("<Return>", self._on_submit)

        ttk.Button(input_frame, text="Send", style="Send.TButton", command=self._on_submit).grid(
            row=0, column=1, sticky="ew", padx=(0, 8)
        )
        ttk.Button(
            input_frame,
            text="Status",
            style="Quick.TButton",
            command=self._on_status_button,
        ).grid(row=0, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(
            input_frame,
            text="Run Execution Demo",
            style="Quick.TButton",
            command=lambda: self._run_quick_command("run execution-demo"),
        ).grid(row=0, column=3, sticky="ew")

    def _build_bottom_area(self, parent: tk.Frame) -> None:
        persona_card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        persona_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(persona_card, text="Persona", bg=BG_CARD, fg=FG_MAIN, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=12, pady=(10, 6)
        )
        tk.Label(
            persona_card,
            textvariable=self.persona_summary_var,
            bg=BG_CARD,
            fg=FG_MAIN,
            justify="left",
            anchor="nw",
            font=("Segoe UI", 10),
        ).pack(fill="both", expand=True, padx=12, pady=(0, 12))

        snapshot_card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        snapshot_card.grid(row=0, column=1, sticky="nsew", padx=6)
        tk.Label(snapshot_card, text="Runtime Snapshot", bg=BG_CARD, fg=FG_MAIN, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=12, pady=(10, 6)
        )
        tk.Label(
            snapshot_card,
            textvariable=self.runtime_summary_var,
            bg=BG_CARD,
            fg=FG_MAIN,
            justify="left",
            anchor="nw",
            font=("Segoe UI", 10),
        ).pack(fill="both", expand=True, padx=12, pady=(0, 12))

        help_card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        help_card.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        tk.Label(help_card, text="Quick Help", bg=BG_CARD, fg=FG_MAIN, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=12, pady=(10, 6)
        )
        tk.Label(
            help_card,
            text=(
                "Commands:\n"
                "- status\n"
                "- panel\n"
                "- help\n"
                "- who are you\n"
                "- what can you do\n"
                "- run execution-demo"
            ),
            bg=BG_CARD,
            fg=FG_MAIN,
            justify="left",
            anchor="nw",
            font=("Segoe UI", 10),
        ).pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _add_status_row(self, parent: tk.Frame, row: int, label: str, var: tk.StringVar) -> None:
        tk.Label(parent, text=label, bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, sticky="nw", padx=(12, 10), pady=2
        )
        tk.Label(
            parent,
            textvariable=var,
            bg=BG_CARD,
            fg=FG_MAIN,
            justify="left",
            anchor="w",
            wraplength=440,
            font=("Segoe UI", 10),
        ).grid(row=row, column=1, sticky="w", pady=2)

    def _configure_chat_tags(self) -> None:
        self.chat_text.tag_configure("speaker_zero", foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("speaker_you", foreground=ACCENT_BLUE, font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("speaker_system", foreground=ACCENT_WARN, font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("speaker_panel", foreground=FG_MUTED, font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("message", foreground=FG_MAIN, font=("Segoe UI", 10))
        self.chat_text.tag_configure("status_title", foreground=ACCENT_BLUE, font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("status_body", foreground=FG_MAIN, font=("Consolas", 10))
        self.chat_text.tag_configure("divider", foreground=FG_MUTED, font=("Consolas", 9))

    def _set_text_widget(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _speaker_tag(self, speaker: str) -> str:
        normalized = speaker.upper()
        if normalized == "ZERO":
            return "speaker_zero"
        if normalized == "YOU":
            return "speaker_you"
        if normalized == "SYSTEM":
            return "speaker_system"
        if normalized == "PANEL":
            return "speaker_panel"
        return "message"

    def _append_message(self, speaker: str, message: str) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", f"{speaker}\n", (self._speaker_tag(speaker),))
        self.chat_text.insert("end", f"{message}\n\n", ("message",))
        self.chat_text.see("end")
        self.chat_text.configure(state="disabled")

    def _append_status_snapshot(self, text: str) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", "SYSTEM\n", ("speaker_system",))
        self.chat_text.insert("end", "Runtime Snapshot\n", ("status_title",))
        self.chat_text.insert("end", "----------------\n", ("divider",))
        self.chat_text.insert("end", text.rstrip() + "\n\n", ("status_body",))
        self.chat_text.see("end")
        self.chat_text.configure(state="disabled")

    def _format_runtime_status(self) -> str:
        snapshot = self.state_manager.get_state()
        current_image = self.image_path_var.get() or "-"

        return (
            "[CURRENT STATUS]\n"
            f"State             : {snapshot.state.value}\n"
            f"Reason            : {snapshot.reason or '-'}\n"
            f"Source            : {snapshot.source or '-'}\n"
            f"Detail            : {snapshot.detail or '-'}\n"
            "\n"
            "[LAST EXECUTION]\n"
            f"Last Capability   : {snapshot.last_capability or '-'}\n"
            f"Last Result       : {snapshot.last_result or '-'}\n"
            f"Last Task ID      : {snapshot.last_task_id or '-'}\n"
            f"Output Hint       : {snapshot.last_output_hint or '-'}\n"
            "\n"
            "[PERSONA]\n"
            f"Name              : {self.persona.name}\n"
            f"Role              : {self.persona.role}\n"
            f"Visual ID         : {self.visual_profile.visual_id}\n"
            f"Render Mode       : {self.visual_profile.render_mode}\n"
            f"Pillow Available  : {PIL_AVAILABLE}\n"
            f"Current Image     : {current_image}"
        )

    def _on_status_button(self) -> None:
        self._refresh_all_views()
        self._append_status_snapshot(self._format_runtime_status())

    def _get_current_portrait_path(self) -> Path:
        if ENABLE_BLINK and self._blink_active and self._blink_sequence:
            frame_name = self._blink_sequence[self._blink_index]
            return self.visual_profile.resolve_blink_frame(frame_name)

        snapshot = self.state_manager.get_state()
        return self.visual_profile.resolve_image_for_state(snapshot.state)

    def _get_background_path(self) -> Path:
        return REPO_ROOT / "assets" / "persona" / "zero_v1" / "circuit_bg.png"

    def _update_state_badge(self) -> None:
        state = self.state_manager.get_state().state.value
        color_map = {
            "IDLE": ACCENT_BLUE,
            "THINKING": ACCENT_WARN,
            "EXECUTING": ACCENT,
            "SUCCESS": ACCENT,
            "ERROR": ACCENT_ERR,
        }
        self.state_badge.configure(text=state, fg=color_map.get(state, FG_MAIN))

    def _resize_cover(self, image: Image.Image, target_w: int, target_h: int) -> Image.Image:
        src_w, src_h = image.size
        if src_w <= 0 or src_h <= 0:
            return Image.new("RGBA", (target_w, target_h), (8, 16, 30, 255))

        scale = max(target_w / src_w, target_h / src_h)
        resized_w = max(1, int(src_w * scale))
        resized_h = max(1, int(src_h * scale))

        image = image.resize((resized_w, resized_h), Image.LANCZOS)

        left = max(0, (resized_w - target_w) // 2)
        top = max(0, (resized_h - target_h) // 2)
        right = left + target_w
        bottom = top + target_h

        return image.crop((left, top, right, bottom))

    def _resize_contain(self, image: Image.Image, max_w: int, max_h: int) -> Image.Image:
        src_w, src_h = image.size
        if src_w <= 0 or src_h <= 0:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

        scale = min(max_w / src_w, max_h / src_h)
        resized_w = max(1, int(src_w * scale))
        resized_h = max(1, int(src_h * scale))

        return image.resize((resized_w, resized_h), Image.LANCZOS)

    def _compose_visual(self) -> object:
        portrait_path = self._get_current_portrait_path()
        bg_path = self._get_background_path()

        if not PIL_AVAILABLE:
            return tk.PhotoImage(file=str(portrait_path))

        canvas_w = max(self.visual_canvas.winfo_width(), 520)
        canvas_h = max(self.visual_canvas.winfo_height(), 640)

        if bg_path.exists():
            bg = Image.open(bg_path).convert("RGBA")
            bg = self._resize_cover(bg, canvas_w, canvas_h)
        else:
            bg = Image.new("RGBA", (canvas_w, canvas_h), (8, 16, 30, 255))

        composed = bg.copy()

        if not portrait_path.exists():
            return ImageTk.PhotoImage(composed)

        portrait = Image.open(portrait_path).convert("RGBA")

        max_persona_w = int(canvas_w * 0.66)
        max_persona_h = int(canvas_h * 0.96)
        portrait = self._resize_contain(portrait, max_persona_w, max_persona_h)

        portrait_w, portrait_h = portrait.size

        x = (canvas_w - portrait_w) // 2
        y = canvas_h - portrait_h + int(canvas_h * 0.025)

        x = max(0, min(x, canvas_w - portrait_w))
        y = max(0, min(y, canvas_h - portrait_h))

        shadow = Image.new("RGBA", (portrait_w, portrait_h), (0, 0, 0, 0))
        shadow_alpha = portrait.getchannel("A").point(lambda value: int(value * 0.22))
        shadow.putalpha(shadow_alpha)

        shadow_x = min(canvas_w - portrait_w, x + 10)
        shadow_y = min(canvas_h - portrait_h, y + 12)

        composed.alpha_composite(shadow, (shadow_x, shadow_y))
        composed.alpha_composite(portrait, (x, y))

        vignette = Image.new("RGBA", (canvas_w, canvas_h), (8, 16, 30, 28))
        composed = Image.alpha_composite(composed, vignette)

        return ImageTk.PhotoImage(composed)

    def _refresh_image(self) -> None:
        portrait_path = self._get_current_portrait_path()
        self.image_path_var.set(str(portrait_path))

        try:
            self._visual_photo = self._compose_visual()
            self.visual_canvas.delete("all")

            canvas_w = max(self.visual_canvas.winfo_width(), 520)
            canvas_h = max(self.visual_canvas.winfo_height(), 640)

            self.visual_canvas.create_image(
                canvas_w // 2,
                canvas_h // 2,
                image=self._visual_photo,
                anchor="center",
            )
        except Exception as exc:
            self.visual_canvas.delete("all")
            self.visual_canvas.create_text(
                40,
                40,
                text=f"Visual load failed:\n{exc}",
                fill=FG_MUTED,
                anchor="nw",
                font=("Segoe UI", 11),
            )
            self._visual_photo = None

    def _refresh_status_labels(self) -> None:
        snapshot = self.state_manager.get_state()
        self.current_state_var.set(snapshot.state.value)
        self.reason_var.set(snapshot.reason or "-")
        self.source_var.set(snapshot.source or "-")
        self.detail_var.set(snapshot.detail or "-")
        self.last_capability_var.set(snapshot.last_capability or "-")
        self.last_result_var.set(snapshot.last_result or "-")
        self.last_task_id_var.set(snapshot.last_task_id or "-")
        self.last_output_hint_var.set(snapshot.last_output_hint or "-")

        self.persona_summary_var.set(
            f"Name: {self.persona.name}\n"
            f"Role: {self.persona.role}\n"
            f"Visual: {self.visual_profile.visual_id}\n"
            f"Render Mode: {self.visual_profile.render_mode}"
        )

        self.runtime_summary_var.set(
            f"Current State: {snapshot.state.value}\n"
            f"Last Capability: {snapshot.last_capability or '-'}\n"
            f"Last Result: {snapshot.last_result or '-'}\n"
            f"Last Task ID: {snapshot.last_task_id or '-'}"
        )

        self._update_state_badge()

    def _refresh_panel_popup(self) -> None:
        if not self._panel_visible or not hasattr(self, "panel_popup") or self.panel_popup is None:
            return

        snapshot = self.state_manager.get_state()
        panel_text = render_persona_panel(self.persona, snapshot, self.visual_profile)
        self._set_text_widget(self.panel_text, panel_text)

    def _refresh_all_views(self) -> None:
        self._refresh_status_labels()
        self._refresh_image()
        self._refresh_panel_popup()

    def _schedule_next_blink(self) -> None:
        if not ENABLE_BLINK:
            return

        delay_ms = random.randint(3000, 6000)
        self._blink_job = self.root.after(delay_ms, self._start_blink)

    def _start_blink(self) -> None:
        if not ENABLE_BLINK:
            return

        if self._blink_active:
            return

        self._blink_active = True
        self._blink_sequence = ["open", "half", "closed", "half", "open"]
        self._blink_index = 0
        self._run_blink_step()

    def _run_blink_step(self) -> None:
        if not ENABLE_BLINK:
            self._blink_active = False
            self._blink_sequence = []
            self._blink_index = 0
            return

        if not self._blink_active:
            return

        self._refresh_image()
        self._blink_index += 1

        if self._blink_index >= len(self._blink_sequence):
            self._blink_active = False
            self._blink_sequence = []
            self._blink_index = 0
            self._refresh_image()
            self._schedule_next_blink()
            return

        self.root.after(90, self._run_blink_step)

    def _toggle_panel_popup(self) -> None:
        if self._panel_visible:
            self._close_panel_popup()
        else:
            self._open_panel_popup()

    def _open_panel_popup(self) -> None:
        if self._panel_visible:
            return

        self.panel_popup = tk.Toplevel(self.root)
        self.panel_popup.title("ZERO Persona Panel")
        self.panel_popup.geometry("520x640")
        self.panel_popup.configure(bg=BG_MAIN)
        self.panel_popup.protocol("WM_DELETE_WINDOW", self._close_panel_popup)

        frame = tk.Frame(self.panel_popup, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        tk.Label(frame, text="Persona Panel", bg=BG_CARD, fg=FG_MAIN, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 8)
        )

        self.panel_text = tk.Text(
            frame,
            wrap="word",
            font=("Consolas", 10),
            bg=BG_CHAT,
            fg="#d7e2f0",
            insertbackground="#d7e2f0",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.panel_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.panel_text.configure(state="disabled")

        self._panel_visible = True
        self.panel_toggle_text.set("Hide Panel")
        self._refresh_panel_popup()

    def _close_panel_popup(self) -> None:
        if not self._panel_visible:
            return

        try:
            if self.panel_popup is not None:
                self.panel_popup.destroy()
        except Exception:
            pass

        self.panel_popup = None
        self._panel_visible = False
        self.panel_toggle_text.set("Show Panel")

    def _execute_command(self, command: str) -> None:
        command = (command or "").strip()
        if not command:
            return

        normalized = command.lower()

        if normalized in {"status", "/status"}:
            self._append_message("YOU", command)
            self._on_status_button()
            return

        self._append_message("YOU", command)

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = generate_rule_based_response(self.persona, command)

        captured = buffer.getvalue().strip()
        if captured:
            self._append_message("SYSTEM", captured)

        self._append_message("ZERO", result.response)
        self._refresh_all_views()

        if result.should_exit:
            self.root.after(300, self.root.destroy)

    def _on_submit(self, _event: object | None = None) -> None:
        command = self.command_entry.get().strip()
        self.command_entry.delete(0, "end")
        self._execute_command(command)

    def _run_quick_command(self, command: str) -> None:
        self._execute_command(command)

    def _on_window_resize(self, _event: object | None = None) -> None:
        if self._resize_job:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass

        self._resize_job = self.root.after(120, self._refresh_image)


def main() -> int:
    root = tk.Tk()
    PersonaRuntimeWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())