import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import os
from pathlib import Path
import yt_dlp

DEFAULT_DIR = str(Path.home() / "Downloads")

SUPPORTED_FORMATS = {
    # Audio
    "MP3 (audio)": "mp3",
    "WAV (audio)": "wav",
    "FLAC (audio)": "flac",
    "M4A (audio)": "m4a",
    "OPUS (audio)": "opus",

    # Video
    "MP4 (video)": "mp4",
    "MKV (video)": "mkv",
}

class DownloadJob:
    def __init__(self, url, fmt_name):
        self.url = url
        self.fmt_name = fmt_name
        self.ext = SUPPORTED_FORMATS[fmt_name]
        self.status = "Waiting..."
        self.percent = 0
        self.title = "Fetching title..."

class YouTubeTransformerApp:
    def __init__(self, root):
        self.root = root
        root.title("YouTube Transformer made by ToxicityOfOurCity")
        root.geometry("900x380")
        root.resizable(False, False)
        root.configure(bg="#13181c")

        self.output_dir = tk.StringVar(value=DEFAULT_DIR)
        self.format_var = tk.StringVar(value="MP3 (audio)")

        self.job_queue = queue.Queue()
        self.jobs = []
        self.worker_running = False

        self.build_ui()

    def build_ui(self):
        main = tk.Frame(self.root, bg="#13181c")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        left = tk.Frame(main, bg="#13181c")
        left.pack(side="left", fill="y")

        right = tk.Frame(main, bg="#1b2126")
        right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        # URL
        tk.Label(left, text="YouTube URL:", bg="#13181c", fg="white").pack(anchor="w")
        self.url_entry = tk.Entry(left, width=55)
        self.url_entry.pack(pady=5)

        # Format
        tk.Label(left, text="Output format:", bg="#13181c", fg="white").pack(anchor="w")
        ttk.Combobox(
            left,
            textvariable=self.format_var,
            values=list(SUPPORTED_FORMATS.keys()),
            state="readonly",
            width=30
        ).pack(pady=5)

        # Folder
        tk.Label(left, text="Output folder:", bg="#13181c", fg="white").pack(anchor="w")
        folder_frame = tk.Frame(left, bg="#13181c")
        folder_frame.pack(fill="x", pady=5)

        tk.Entry(folder_frame, textvariable=self.output_dir, width=40, state="readonly").pack(side="left")
        tk.Button(folder_frame, text="Browse", command=self.pick_folder).pack(side="left", padx=5)

        # Transform button
        tk.Button(
            left,
            text="Transform",
            bg="#4c9e88",
            fg="white",
            command=self.add_job
        ).pack(pady=10)

        # Queue panel
        tk.Label(right, text="Queue", bg="#1b2126", fg="white").pack(anchor="w", padx=5, pady=5)

        self.queue_list = tk.Listbox(
            right,
            bg="#0f1316",
            fg="white",
            width=60,
            height=16
        )
        self.queue_list.pack(fill="both", expand=True, padx=5, pady=5)

    def pick_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir.get())
        if folder:
            self.output_dir.set(folder)

    def add_job(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Enter a URL")
            return

        job = DownloadJob(url, self.format_var.get())
        self.jobs.append(job)
        self.job_queue.put(job)
        self.url_entry.delete(0, tk.END)

        self.refresh_queue()

        if not self.worker_running:
            threading.Thread(target=self.worker, daemon=True).start()

    def refresh_queue(self):
        self.queue_list.delete(0, tk.END)
        for job in self.jobs:
            line = f"{job.title} → {job.ext.upper()} [{job.status}]"
            if job.status == "Downloading":
                line += f" {job.percent:.1f}%"
            self.queue_list.insert(tk.END, line)

    def worker(self):
        self.worker_running = True
        while not self.job_queue.empty():
            job = self.job_queue.get()
            self.run_job(job)
        self.worker_running = False

    def progress_hook(self, job):
        def hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    job.percent = d.get("downloaded_bytes", 0) / total * 100
                    job.status = "Downloading"
                    self.root.after(0, self.refresh_queue)
            elif d["status"] == "finished":
                job.status = "Processing"
                self.root.after(0, self.refresh_queue)
        return hook

    def run_job(self, job):
        try:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(job.url, download=False)
                job.title = info["title"]

            job.status = "Downloading"
            self.root.after(0, self.refresh_queue)

            ydl_opts = {
                "outtmpl": os.path.join(self.output_dir.get(), "%(title)s.%(ext)s"),
                "quiet": True,
                "noplaylist": True,
                "progress_hooks": [self.progress_hook(job)],
            }

            if "audio" in job.fmt_name.lower():
                ydl_opts.update({
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": job.ext,
                        "preferredquality": "192",
                    }],
                })
            else:
                ydl_opts.update({
                    "format": "bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio",
                    "merge_output_format": job.ext,
                })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([job.url])

            job.status = "Done"
            job.percent = 100

        except Exception as e:
            job.status = "Error"

        self.root.after(0, self.refresh_queue)

if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeTransformerApp(root)
    root.mainloop()
