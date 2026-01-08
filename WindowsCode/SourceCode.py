import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import queue
import os
import re
from pathlib import Path
import yt_dlp

# ---------------- APPEARANCE ---------------- #
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

DEFAULT_DIR = str(Path.home() / "Downloads")

SUPPORTED_FORMATS = {
    "MP3 (audio)": "mp3",
    "WAV (audio)": "wav",
    "FLAC (audio)": "flac",
    "M4A (audio)": "m4a",
    "OPUS (audio)": "opus",
    "MP4 (video)": "mp4",
    "MKV (video)": "mkv",
}

STATUS_ICONS = {
    "Waiting": "⏳",
    "Downloading": "⬇",
    "Processing": "⚙",
    "Done": "✅",
    "Error": "❌",
}

# ---------------- HELPERS ---------------- #
def safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def smooth_progress(job):
    if not job.progress:
        return
    current = job.progress.get()
    delta = job.progress_target - current
    if abs(delta) < 0.002:
        job.progress.set(job.progress_target)
    else:
        job.progress.set(current + delta * 0.15)
        job.progress.after(16, smooth_progress, job)

# ---------------- JOB MODEL ---------------- #
class DownloadJob:
    def __init__(self, url, fmt_name):
        self.url = url
        self.fmt_name = fmt_name
        self.ext = SUPPORTED_FORMATS[fmt_name]

        self.title = "Fetching title..."
        self.status = "Waiting"
        self.progress_target = 0.0

        self.frame = None
        self.label = None
        self.progress = None

# ---------------- APP ---------------- #
class YouTubeTransformerApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("YouTube Transformer")
        self.geometry("980x460")
        self.minsize(980, 460)

        self.output_dir = ctk.StringVar(value=DEFAULT_DIR)
        self.format_var = ctk.StringVar(value="MP3 (audio)")

        self.jobs = []
        self.job_queue = queue.Queue()
        self.worker_running = False

        self.build_ui()

    # ---------------- UI ---------------- #
    def build_ui(self):
        main = ctk.CTkFrame(self, corner_radius=20)
        main.pack(fill="both", expand=True, padx=15, pady=15)

        # LEFT PANEL
        left = ctk.CTkFrame(main, width=320, corner_radius=15)
        left.pack(side="left", fill="y", padx=(0, 10))

        ctk.CTkLabel(left, text="YouTube URL").pack(anchor="w", padx=10, pady=(10,0))
        self.url_entry = ctk.CTkEntry(left, width=280)
        self.url_entry.pack(padx=10, pady=5)

        ctk.CTkLabel(left, text="Output format").pack(anchor="w", padx=10, pady=(10,0))
        ctk.CTkOptionMenu(left, variable=self.format_var,
                           values=list(SUPPORTED_FORMATS.keys())).pack(padx=10, pady=5)

        ctk.CTkLabel(left, text="Output folder").pack(anchor="w", padx=10, pady=(10,0))
        folder_frame = ctk.CTkFrame(left, fg_color="transparent")
        folder_frame.pack(padx=10, pady=5, fill="x")
        ctk.CTkEntry(folder_frame, textvariable=self.output_dir, state="readonly", width=200).pack(side="left")
        ctk.CTkButton(folder_frame, text="Browse", width=60, command=self.pick_folder).pack(side="left", padx=5)

        ctk.CTkButton(left, text="Transform", height=40, corner_radius=12,
                      command=self.add_job).pack(padx=10, pady=15, fill="x")

        # Light/Dark toggle
        ctk.CTkButton(left, text="☀ / 🌙 Theme", command=self.toggle_theme).pack(padx=10, pady=(0,15), fill="x")

        # RIGHT PANEL
        right = ctk.CTkFrame(main, corner_radius=15)
        right.pack(side="right", fill="both", expand=True)
        ctk.CTkLabel(right, text="Queue", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10,0))
        self.queue_frame = ctk.CTkScrollableFrame(right, corner_radius=10)
        self.queue_frame.pack(fill="both", expand=True, padx=10, pady=10)

    # ---------------- LOGIC ---------------- #
    def toggle_theme(self):
        ctk.set_appearance_mode("light" if ctk.get_appearance_mode()=="Dark" else "dark")

    def pick_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir.get())
        if folder:
            self.output_dir.set(folder)

    def add_job(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error","Enter a YouTube URL")
            return
        job = DownloadJob(url, self.format_var.get())
        self.jobs.append(job)
        self.job_queue.put(job)
        self.url_entry.delete(0,"end")
        self.create_job_widget(job)
        if not self.worker_running:
            threading.Thread(target=self.worker, daemon=True).start()

    def create_job_widget(self, job):
        frame = ctk.CTkFrame(self.queue_frame, corner_radius=12)
        frame.pack(fill="x", pady=6, padx=5)
        label = ctk.CTkLabel(frame, text=f"{STATUS_ICONS[job.status]} {job.title}", anchor="w")
        label.pack(fill="x", padx=10, pady=(8,0))
        progress = ctk.CTkProgressBar(frame)
        progress.set(0)
        progress.pack(fill="x", padx=10, pady=(5,10))
        job.frame = frame
        job.label = label
        job.progress = progress
        smooth_progress(job)

    def worker(self):
        self.worker_running = True
        while not self.job_queue.empty():
            self.run_job(self.job_queue.get())
        self.worker_running = False

    def progress_hook(self, job):
        def hook(d):
            if d["status"]=="downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    job.progress_target = d.get("downloaded_bytes",0)/total
                    # Update queue label dynamically
                    self.after(0, lambda: job.label.configure(
                        text=f"{job.title} -> [{job.ext.upper()}] [{job.progress_target*100:.1f}% Done]"
                    ))
            elif d["status"]=="finished":
                job.status="Processing"
                self.after(0, lambda: job.label.configure(
                    text=f"{job.title} -> [{job.ext.upper()}] [Processing]"
                ))
        return hook

    def run_job(self, job):
        try:
            with yt_dlp.YoutubeDL({"quiet":True}) as ydl:
                info = ydl.extract_info(job.url, download=False)
                job.title = safe_filename(info["title"])

            job.status="Downloading"
            self.after(0, lambda: job.label.configure(
                text=f"{job.title} -> [{job.ext.upper()}] [0.0% Done]"
            ))

            ydl_opts = {
                "outtmpl": os.path.join(self.output_dir.get(), "%(title)s.%(ext)s"),
                "quiet": True,
                "noplaylist": True,
                "progress_hooks": [self.progress_hook(job)],
                "js_runtime": "node"
            }

            # Fix: MP4 audio encoded as MP3 (for Windows)
            if "audio" in job.fmt_name.lower():
                ydl_opts.update({
                    "format":"bestaudio/best",
                    "postprocessors":[{
                        "key":"FFmpegExtractAudio",
                        "preferredcodec":job.ext,
                        "preferredquality":"192",
                    }],
                })
            else:
                # Video case: merge video+audio, audio as MP3
                ydl_opts.update({
                    "format": "bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio",
                    "merge_output_format": job.ext,
                    "postprocessors":[{
                        "key":"FFmpegExtractAudio",
                        "codec":"mp3",
                        "preferredquality":"192"
                    }] if job.ext.lower() != "mp4" else []
                })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([job.url])

            job.progress_target=1.0
            job.status="Done"
            self.after(0, lambda: job.label.configure(
                text=f"{job.title} -> [{job.ext.upper()}] [100.0% Done]"
            ))

        except Exception:
            job.status="Error"
            self.after(0, lambda: job.label.configure(
                text=f"{job.title} -> [{job.ext.upper()}] [Error]"
            ))

# ---------------- RUN ---------------- #
if __name__=="__main__":
    app = YouTubeTransformerApp()
    app.mainloop()