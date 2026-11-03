"""The application window (tkinter): start screen, the Ukrainian installer, the translator tool."""
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, VERSION, download, edition, game, i18n, install, project, repo, texts, toolcheck, validate
from . import scenery
from .player import Player

try:
    import sv_ttk  # modern Sun Valley theme (light/dark)
except ImportError:
    sv_ttk = None
from .i18n import _


DARK = False


def col(kind):
    """Text colors that read well in both the light and the dark theme."""
    return {"muted": "#9aa0a6" if DARK else "#5f6368", "warn": "#ff8a80" if DARK else "#b00020",
            "text": "#e8eaed" if DARK else "#1f1f1f"}[kind]


def system_dark():
    """Is Windows in dark mode? (registry: AppsUseLightTheme)"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            "Software" + chr(92) + "Microsoft" + chr(92) + "Windows" + chr(92) + "CurrentVersion" + chr(92) + "Themes" + chr(92) + "Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False

def local_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "D4LocToolkit")


def default_project():
    """Default project folder: "project" inside the application's data folder under %LOCALAPPDATA% (not Documents and not the .exe folder)."""
    return os.path.join(local_data_dir(), "project")


def settings_path():
    """Settings file: settings.json inside the application's data folder under %LOCALAPPDATA%."""
    return os.path.join(local_data_dir(), "settings.json")


def load_settings():
    try:
        import json
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(d):
    import json
    try:
        os.makedirs(os.path.dirname(settings_path()), exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def languages_unlocked():
    """Choosing the target language in the translator tool is locked by default (Ukrainian only). Anyone who wants to work with other languages
    enables it on their own: environment variable D4LOC_UNLOCK_LANGUAGES=1 or "unlock_languages": true in the settings file. This is not part of the project and is not supported."""
    return os.environ.get("D4LOC_UNLOCK_LANGUAGES") == "1" or load_settings().get("unlock_languages") is True


def default_pack_dir(project_dir=None):
    """The content and voice pack: the fork itself (it already has uk/loca_uk_texts.csv and uk/audio), and without such a project the legacy uk_pack folder inside the project folder."""
    pd = project_dir or default_project()
    if repo.is_content_project(pd):
        return pd
    return download.pack_dir_in(pd)


def local_pack(project_dir):
    """A ready content pack on this computer: the project folder of the translator tool if it contains a translation (we never delete it). Otherwise None:
    then the release files next to the program are used, or the pack is downloaded temporarily. The players' installer has no project: always None."""
    if not edition.TRANSLATOR:
        return None
    pd = project_dir or default_project()
    return pd if repo.is_content_project(pd) and install.has_content(pd) else None


def version_lines(game_dir, pack_dir=None, remote=None):
    """(user-facing string, matches?) about the game version and what the translation was made for: from the local pack's manifest.json or,
    before downloading, from the latest release's manifest.json (a separate release file)."""
    local = game.version_info(game_dir)
    lines = [_("Ваша гра: {0}").format(local['label'])]
    have = install.has_content(pack_dir)
    man = install.load_manifest(pack_dir) if have else (remote or {}).get("manifest")
    if not man:
        lines.append(_("Переклад ще не завантажено (потрібен інтернет або тека з контентом)."))
        return chr(10).join(lines), True
    pg = man.get("game") or {}
    label = ", ".join(x for x in ((pg.get("release") or ""), (_("збірка {0}").format(pg['build'][:8]) if pg.get("build") else ""),
                                  (f"Steam {pg['steam_buildid']}" if pg.get("steam_buildid") else "")) if x) or _("не вказано")
    lines.append(_("Переклад v{0} створено для гри: {1}").format(man.get('version', '?'), label))
    ok, msg = install.check_compat(game_dir, pack_dir) if have else game.compare_versions(pg, local)
    if not ok:
        lines.append("⚠ " + msg + _(" Установка можлива, але на власний ризик."))
    elif msg and not msg.startswith(_("Версія гри збігається")):
        lines.append("ℹ " + msg)
    return chr(10).join(lines), ok


class Worker:
    """Runs long actions in a thread; passes messages (log, progress) to the main thread through a queue."""

    def __init__(self, root, log_fn, progress_fn):
        self.root, self.log_fn, self.progress_fn = root, log_fn, progress_fn
        self.q = queue.Queue()
        self.busy = False

    def run(self, fn, done=None):
        if self.busy:
            return
        self.busy = True

        def target():
            try:
                res = fn(lambda m: self.q.put(("log", m)), lambda i, n, m: self.q.put(("progress", (i, n, m))))
                self.q.put(("done", (done, res, None)))
            except Exception as e:  # show the error to the user instead of hiding it
                self.q.put(("done", (done, None, e)))

        threading.Thread(target=target, daemon=True).start()
        self.root.after(100, self.poll)

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log_fn(val)
                elif kind == "progress":
                    self.progress_fn(*val)
                else:
                    self.busy = False
                    done, res, err = val
                    if err:
                        messagebox.showerror(APP_NAME, _("Помилка: {0}").format(err))
                    if done:
                        done(res, err)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def ask_apply(parent, text):
    """A dialog with three answers: 'apply' | 'discard' | 'cancel'."""
    dlg = tk.Toplevel(parent)
    dlg.title(APP_NAME)
    dlg.transient(parent)
    dlg.grab_set()
    ttk.Label(dlg, text=text, justify="left", padding=16).pack()
    answer = {"v": "cancel"}
    bar = ttk.Frame(dlg, padding=(16, 0, 16, 16))
    bar.pack(fill="x")
    for label, val in ((_("Зберегти"), "apply"), (_("Відкинути зміни"), "discard"), (_("Лишитись"), "cancel")):
        ttk.Button(bar, text=label, command=lambda v=val: (answer.update(v=v), dlg.destroy())).pack(side="left", padx=4)
    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
    parent.wait_window(dlg)
    return answer["v"]


class Backdrop(tk.Frame):
    """A container with a full-window background (scenery.py); the screens sit ABOVE it on opaque "cards"."""

    def __init__(self, app):
        super().__init__(app, bd=0, highlightthickness=0)
        self.app = app
        self._src, self._photo, self._after = None, None, None
        self.label = tk.Label(self, bd=0)
        self.label.place(x=0, y=0, relwidth=1, relheight=1)
        self._src = scenery.image()
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, _=None):
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(100, self.render)

    def render(self):
        if self._src is None or not self.winfo_exists():
            return
        try:
            from PIL import ImageTk
            w, h = max(self.winfo_width(), 200), max(self.winfo_height(), 200)
            iw, ih = self._src.size
            k = max(w / iw, h / ih)
            img = self._src.resize((int(iw * k) + 1, int(ih * k) + 1))
            left, top = (img.width - w) // 2, (img.height - h) // 2
            img = img.crop((left, top, left + w, top + h))
            self._photo = ImageTk.PhotoImage(img, master=self)
            self.label.config(image=self._photo)
        except Exception:
            pass


class StartFrame(ttk.Frame):
    """A card in the middle of the window; the game background stays visible around it (the screen itself does not fill the window)."""

    def __init__(self, app):
        super().__init__(app.host, padding=28)
        self.app = app
        card = self
        ttk.Label(card, text=edition.app_name(), font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(card, text=_("версія {0} · Community Edition · неофіційний інструмент для Dungeons 4").format(VERSION),
                  foreground=col("muted")).pack(anchor="w", pady=(0, 16))
        row = ttk.Frame(card)
        row.pack(fill="x")
        ttk.Label(row, text=_("Тека гри:")).pack(side="left")
        self.game_var = tk.StringVar(value=app.game_dir or "")
        big = ("Segoe UI", abs(int(tkfont.nametofont("TkDefaultFont").cget("size"))) + 2)
        ttk.Entry(row, textvariable=self.game_var, width=52, font=big).pack(side="left", padx=8, fill="both", expand=True, ipady=5)
        ttk.Button(row, text=_("Огляд…"), command=self.browse).pack(side="left", fill="y")
        self.status = ttk.Label(card, text="")
        self.status.pack(anchor="w", pady=(8, 2))
        self.ver = ttk.Label(card, text="", justify="left")
        self.ver.pack(anchor="w")
        self.game_var.trace_add("write", lambda *a: self.check())
        box = ttk.Frame(card)
        box.pack(fill="x", pady=(20, 0))
        self.b_install = ttk.Button(box, text=_("Встановити українську мову"), command=lambda: app.leave_to("install"))
        self.b_tool = None
        if edition.TRANSLATOR:        # the players' installer has no translator tool
            self.b_tool = ttk.Button(box, text=_("Інструмент перекладача"), command=app.open_tool)
            self.b_tool.pack(side="right", ipadx=14, ipady=8)
        self.b_install.pack(side="right", padx=(0, 12), ipadx=14, ipady=8)
        self.check()
        self._poll_remote()   # only after all widgets are created: check() touches the buttons

    def _poll_remote(self):
        """The release manifest is fetched in the background; as soon as it is ready, the version lines are refreshed."""
        if not self.winfo_exists():
            return
        if self.app.remote_done:
            self.check()
        else:
            self.after(400, self._poll_remote)

    def browse(self):
        d = filedialog.askdirectory(title=_("Оберіть теку Dungeons 4"))
        if d:
            self.game_var.set(os.path.normpath(d))

    def check(self):
        raw = self.game_var.get().strip().strip('"')
        path = game.resolve_game_dir(raw)
        ok, why = game.validate_game_dir(path)
        if ok and path != raw:
            self.game_var.set(path)   # a parent folder was given: substitute the real game folder (we work with it from now on)
        self.app.game_dir = path if ok else None
        if ok:
            st = load_settings()
            if st.get("game_dir") != path:
                st["game_dir"] = path
                save_settings(st)
        self.status.config(text=(_("Гру знайдено.") if ok else why + _(" Без правильної теки гри нічого не працює.")),
                           foreground=col("text") if ok else col("warn"))
        if ok:
            text, same = version_lines(path, local_pack(self.app.project_dir), self.app.remote)
            self.ver.config(text=text, foreground=col("text") if same else col("warn"))
        else:
            self.ver.config(text="")
        for b in (self.b_install, self.b_tool):
            if b is not None:
                b.state(["!disabled"] if ok else ["disabled"])

    def can_leave(self):
        return True


class InstallFrame(ttk.Frame):
    def __init__(self, app):
        super().__init__(app.host, padding=18)
        self.app = app
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(8, 4))
        ttk.Button(top, text=_("← Назад"), command=lambda: app.leave_to("start")).pack(side="left")
        ttk.Label(self, text=_("Встановлення української мови"), font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(10, 4))
        self.installed = ttk.Label(self, text="")
        self.installed.pack(anchor="w", pady=6)
        vt, same = version_lines(app.game_dir, local_pack(app.project_dir), app.remote)
        ttk.Label(self, text=vt, justify="left", foreground=col("text") if same else col("warn")).pack(anchor="w")
        self.voice_var = tk.BooleanVar(value=True)
        self.voice_cb = ttk.Checkbutton(self, text=_("Встановити озвучення"), variable=self.voice_var,
                                        command=self.update_voice)
        self.voice_cb.pack(anchor="w", pady=(12, 0))
        self.voice_hint = ttk.Label(self, text=_("Перевіряю наявність контенту й з'єднання…"), foreground=col("muted"))
        self.voice_hint.pack(anchor="w", padx=22)
        self.mix_var = tk.BooleanVar(value=True)
        self.mix_cb = ttk.Checkbutton(
            self, text=_("Тихо підмішати англійський оригінал під український голос (як закадровий переклад)"),
            variable=self.mix_var)
        self.mix_cb.pack(anchor="w", pady=4, padx=22)
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=8)
        self.b_inst = ttk.Button(bar, text=_("Встановити"), command=self.do_install)
        self.b_del = ttk.Button(bar, text=_("Видалити українізацію"), command=self.do_uninstall)
        self.b_inst.pack(side="right")
        self.b_del.pack(side="right", padx=(0, 8))
        self.prog = ttk.Progressbar(self, maximum=100)
        self.prog.pack(fill="x", pady=4)
        self.logbox = tk.Text(self, height=14, state="disabled")
        self.logbox.pack(fill="both", expand=True)
        self.worker = Worker(app, self.log, self.progress)
        self.manifest, self.net_checked = None, False
        self.refresh()
        self.check_net()

    def check_net(self):
        """Checks the connection to the release in the background so that the window does not freeze."""
        box = {}

        def run():
            box["m"] = download.fetch_release(timeout=4)
            box["done"] = True
        threading.Thread(target=run, daemon=True).start()

        def poll():
            if box.get("done"):
                self.manifest, self.net_checked = box.get("m"), True
                self.update_voice()
            else:
                self.after(200, poll)
        poll()

    def source(self):
        return local_pack(self.app.project_dir)

    def local_voice(self):
        return install.has_voice(self.source())

    def local_content(self):
        return install.has_content(self.source())

    def update_voice(self):
        """The voice checkbox is available if there is a local pack or one can be downloaded from the release."""
        if not self.net_checked:
            return
        asset = ((self.manifest or {}).get("assets") or {}).get(download.VOICE_ASSET)
        local = self.local_voice()
        net = asset is not None                                              # voice.zip is next to the program or can be downloaded
        next_to_program = download.is_local(asset)
        state, vmsg = install.verify_pack(self.source()) if local else ("empty", "")
        if state == "foreign":
            local = False
        if local:
            hint = ("" if state == "ok" else "⚠ ") + vmsg
        elif net and next_to_program:
            hint = _("Озвучення буде взято з файлу voice.zip поряд із програмою.")
        elif net:
            hint = (_("Озвучення буде завантажено з GitHub ({0:.0f} МБ).").format(
                download.asset_size(self.manifest, download.VOICE_ASSET) / 2**20))
        elif self.manifest is not None and self.manifest.get("local"):
            hint = _("Озвучення недоступне: voice.zip поряд із програмою нема, а завантажити його не вдалося. Можна встановити лише текст.")
        else:
            hint = _("Озвучення недоступне: немає з'єднання з інтернетом. Можна встановити лише текст.")
        available = local or net
        text_ok = self.local_content() or self.manifest is not None
        self.b_inst.state(["!disabled"] if text_ok and not self.worker.busy else ["disabled"])
        if not text_ok:
            hint = _("Немає перекладу: потрібне з'єднання з інтернетом.")
        if not available:
            self.voice_var.set(False)
        self.voice_cb.state(["!disabled"] if available else ["disabled"])
        self.mix_cb.state(["!disabled"] if (available and self.voice_var.get()) else ["disabled"])
        self.voice_hint.config(text=hint, foreground=col("warn") if hint.startswith("⚠") else col("muted"))

    def refresh(self):
        inst = install.is_installed(self.app.game_dir)
        self.installed.config(text=_("Українізація встановлена.") if inst else _("Українізація ще не встановлена."))
        self.b_del.state(["!disabled"] if inst else ["disabled"])
        self.b_inst.config(text=_("Перевстановити") if inst else _("Встановити"))

    def log(self, msg):
        self.logbox.config(state="normal")
        self.logbox.insert("end", msg + chr(10))
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    def progress(self, i, n, msg):
        self.prog.config(value=100 * i / max(n, 1))

    def do_install(self, confirm=True):
        with_voice = bool(self.voice_var.get())
        src = self.source()
        use_local = bool(src) and install.has_content(src) and (not with_voice or install.has_voice(src))
        pack = src if use_local else download.temp_dir()      # no ready pack: a temporary folder that the installation erases itself
        if use_local:
            ok_ver, msg_ver = install.check_compat(self.app.game_dir, pack)
        else:
            if self.manifest is None:
                messagebox.showerror(APP_NAME, _("Немає з'єднання з інтернетом: переклад не завантажити."))
                return
            pg = ((self.manifest or {}).get("manifest") or {}).get("game")
            ok_ver, msg_ver = game.compare_versions(pg, game.version_info(self.app.game_dir))
        if not ok_ver and not messagebox.askyesno(
                APP_NAME, msg_ver + chr(10) + chr(10) + _("Продовжити на власний ризик? (Можливі відсутні або невідповідні репліки.)"),
                default="no"):
            return
        text = _("Створити українські файли в теці гри? У кожен наявний мовний файл (loca_*_texts.csv) буде додано один рядок з назвою української мови для меню налаштувань; перед цим файли копіюються поряд як D4Loc_<ім'я>.bak. Тексти й озвучення інших мов не змінюються.")
        text += chr(10) + chr(10) + _("Застосунок надається «як є», без гарантій; усі наслідки, зокрема для файлів, системи чи обладнання, на вашій відповідальності (див. DISCLAIMER.md). Бажано мати власну копію збережень.")
        if not with_voice:
            text += chr(10) + chr(10) + _("Режим «лише текст»: українські тексти й субтитри, голоси залишаються англійськими.")
        if not use_local:
            size = download.download_size(self.manifest, with_voice)
            if self.manifest.get("local") and not size:
                text += chr(10) + chr(10) + _("Контент береться з файлів поряд із програмою.")
            elif self.manifest.get("local"):
                text += chr(10) + chr(10) + _("Текст береться з файлів поряд із програмою, озвучення ({0:.0f} МБ) буде завантажено з GitHub.").format(size / 2**20)
        if not use_local and not self.manifest.get("local"):
            text += (chr(10) + chr(10) + _("Буде завантажено контент: {0:.1f} МБ із GitHub ({1}).").format(
                size / 2**20, download.REPO))
        if confirm and not messagebox.askyesno(APP_NAME, text):
            return
        mix = -14.0 if (with_voice and self.mix_var.get()) else None
        game_dir, release = self.app.game_dir, self.manifest

        def job(log, prog):
            if not use_local:
                download.download_content(release, pack, with_voice, prog, log)
            install.install_pack(game_dir, pack, mix, prog, log, with_voice=with_voice)
            if not use_local and download.cleanup(pack):       # remove the temporary download; the translator project is left untouched
                log(_("Тимчасово завантажений контент видалено."))

        self.worker.run(job, lambda res, err: (self.refresh(), self.update_voice(),
                                               None if err else messagebox.showinfo(APP_NAME, _("Готово."))))

    def do_uninstall(self):
        if messagebox.askyesno(APP_NAME, _("Видалити українські файли з теки гри?")):
            install.uninstall(self.app.game_dir, log=self.log)
            self.refresh()
            self.update_voice()

    def can_leave(self):
        return not self.worker.busy


class ToolFrame(ttk.Frame):
    def __init__(self, app):
        super().__init__(app.host, padding=14)
        self.app = app
        self.project_dir = app.project_dir
        self.ref_lang, self.tgt_lang = "en", "uk"
        self.rows, self.ref_map = [], {}
        self.sort_col, self.sort_rev, self.sort_n = None, False, 0
        self.titles = {"name": _("Ключ"), "ref": _("Оригінал"), "tgt": _("Переклад"), "aref": _("♪о"), "atgt": _("♪п"), "chg": "✎"}
        self.pend_t, self.names = {}, []
        self.current = None
        self.worker = Worker(app, self.log, self.progress)
        self.pack_dir = default_pack_dir(app.project_dir)
        self.has_pack = install.has_content(self.pack_dir)
        self.has_voice = install.has_voice(self.pack_dir)
        langs = sorted(set(game.list_languages(app.game_dir)) | {"uk"})

        self._title = ttk.Label(self, text=_("Інструмент перекладача"), font=("Segoe UI", 18, "bold"))
        paths = ttk.Frame(self)
        paths.pack(fill="x", pady=(0, 2))
        ttk.Label(paths, text=_("Гра: {0}").format(app.game_dir), foreground=col("muted")).pack(side="left")
        self.status_lbl = ttk.Label(paths, text="", foreground=col("warn"))
        self.status_lbl.pack(side="right")
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text=_("← Назад"), command=lambda: app.leave_to("start")).pack(side="left")
        self.langs = langs
        self.unlocked = languages_unlocked()
        new_lang = _("(нова мова…)")
        ttk.Label(top, text=_("Оригінал:")).pack(side="left", padx=(12, 6))
        if self.unlocked:    # deliberately unlocked: any game language may be the original, and the one chosen as the original disappears from the list of translations
            self.ref_cb = ttk.Combobox(top, values=langs, width=8, state="readonly")
            self.ref_cb.set("en" if "en" in langs else (langs[0] if langs else ""))
            self.ref_cb.pack(side="left")
            self.ref_cb.bind("<<ComboboxSelected>>", self._ref_changed)
            ttk.Label(top, text=_("Переклад:")).pack(side="left", padx=(12, 6))
            targets = [l for l in langs if l != self.ref_cb.get()]
            self.tgt_cb = ttk.Combobox(top, values=targets + [new_lang], width=12, state="readonly")
            self.tgt_cb.set("uk" if "uk" in targets else (targets[0] if targets else ""))
            self.tgt_cb.pack(side="left")
            ttk.Button(top, text=_("Завантажити мови"), command=self.load_languages).pack(side="left", padx=12)
        else:   # by default: the original is English, the translation is Ukrainian; there is no language choice (the hidden fields remain for the code)
            self.ref_cb = ttk.Combobox(top, values=["en"], width=8, state="disabled")
            self.ref_cb.set("en")
            self.tgt_cb = ttk.Combobox(top, values=["uk"], width=12, state="disabled")
            self.tgt_cb.set("uk")
            ttk.Label(top, text="en", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 12))
            ttk.Label(top, text=_("Переклад:")).pack(side="left", padx=(12, 6))
            ttk.Label(top, text="uk", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 12))
        ttk.Label(top, text=_("Проєкт:")).pack(side="left", padx=(12, 4))
        self.proj_var = tk.StringVar(value=self.project_dir)
        ttk.Button(top, text="…", width=4, command=self.pick_project).pack(side="right")
        ttk.Entry(top, textvariable=self.proj_var).pack(side="left", fill="x", expand=True, padx=(0, 6))

        filt = ttk.Frame(self)
        filt.pack(fill="x", pady=(4, 8))
        self._top_frames = [self._title, paths, top, filt]
        ttk.Label(filt, text=_("Пошук:")).pack(side="left", padx=(0, 6))
        self.q_var = tk.StringVar()
        self.q_var.trace_add("write", lambda *a: self.fill())
        self.only_var = tk.BooleanVar()
        self.shown_label = ttk.Label(filt, text="")
        self.shown_label.pack(side="right", padx=(12, 0))
        ttk.Checkbutton(filt, text=_("Лише змінені"), variable=self.only_var, command=self.fill).pack(side="right", padx=(12, 0))
        ttk.Entry(filt, textvariable=self.q_var).pack(side="left", fill="x", expand=True)

        cols = ("name", "ref", "tgt", "aref", "atgt", "chg")
        tf = ttk.Frame(self)
        tf.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=14, selectmode="browse")
        for c, t, w in (("name", _("Ключ"), 260), ("ref", _("Оригінал"), 380), ("tgt", _("Переклад"), 380),
                        ("aref", _("♪о"), 56), ("atgt", _("♪п"), 56), ("chg", "✎", 48)):
            self.tree.heading(c, text=t, command=lambda c=c: self.sort_by(c))
            self.tree.column(c, width=w, anchor="w" if w > 70 else "center")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        det = ttk.Frame(self)
        det.pack(fill="x", pady=(10, 6))
        self.ref_text = tk.Text(det, height=2, wrap="word", state="disabled", font=("Segoe UI", 12), padx=8, pady=6)
        self.tgt_text = tk.Text(det, height=2, wrap="word", font=("Segoe UI", 12), padx=8, pady=6)
        ttk.Label(det, text=_("Оригінал")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(det, text=_("Переклад (редагується)")).grid(row=0, column=1, sticky="w", padx=(4, 0), pady=(0, 6))
        self.ref_text.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.tgt_text.grid(row=1, column=1, sticky="ew", padx=(4, 0))
        det.columnconfigure(0, weight=1, uniform="txt")
        det.columnconfigure(1, weight=1, uniform="txt")
        self.tgt_text.bind("<<Modified>>", self.on_text_modified)

        au = ttk.Frame(self)
        au.pack(fill="x", pady=(6, 4))
        src = ttk.Frame(au)
        src.pack(fill="x")
        ttk.Label(src, text=_("Слухати:")).pack(side="left")
        self.src_var = tk.StringVar(value="tgt")
        self.rb = {}
        for key, txt in (("ref", _("оригінал")), ("tgt", _("переклад"))):
            rb = ttk.Radiobutton(src, text=txt, value=key, variable=self.src_var, command=self.on_source)
            rb.pack(side="left", padx=6)
            self.rb[key] = rb
        ttk.Button(src, text=_("Завантажити аудіо…"), command=self.load_audio).pack(side="right", padx=4)
        tr = ttk.Frame(au)
        tr.pack(fill="x", pady=(8, 6))
        self.b_prev = ttk.Button(tr, text="⏮", width=4, command=lambda: self.step(-1))
        self.b_play = ttk.Button(tr, text="▶", width=4, command=self.toggle_play)
        self.b_stop = ttk.Button(tr, text="⏹", width=4, command=self.stop)
        self.b_next = ttk.Button(tr, text="⏭", width=4, command=lambda: self.step(1))
        for b in (self.b_prev, self.b_play, self.b_stop, self.b_next):
            b.pack(side="left", padx=2)
        self.seek_var = tk.DoubleVar(value=0)
        self.seek = ttk.Scale(tr, from_=0, to=1000, variable=self.seek_var, command=self.on_seek_drag)
        self.seek.pack(side="left", fill="x", expand=True, padx=10)
        self.seek.bind("<ButtonPress-1>", lambda e: setattr(self, "seeking", True))
        self.seek.bind("<ButtonRelease-1>", self.on_seek_release)
        self.time_lbl = ttk.Label(tr, text="0:00 / 0:00", width=11)
        self.time_lbl.pack(side="left")
        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tr, text=_("Повтор"), variable=self.loop_var).pack(side="left", padx=(8, 0))
        self.audio_info = ttk.Label(au, text="", foreground=col("muted"))
        self.audio_info.pack(anchor="w")
        self.player = Player()
        self.seeking = False
        self._was_playing = False
        self._autoplay = False
        self.playing_src = "tgt"
        self.after(150, self._tick)

        foot = ttk.Frame(self)
        foot.pack(fill="x", pady=(10, 0))
        self.chg_label = ttk.Label(foot, text=_("Змін немає"))
        self.chg_label.pack(side="left")
        self.b_save_install = ttk.Button(foot, text=_("Зберегти й встановити"), command=lambda: self.save(install_after=True))
        self.b_save = ttk.Button(foot, text=_("Зберегти"), command=self.save)
        self.b_disc = ttk.Button(foot, text=_("Скасувати"), command=self.discard)
        self.b_save_install.pack(side="right")
        self.b_save.pack(side="right", padx=4)
        self.b_disc.pack(side="right", padx=4)
        self.prog = ttk.Progressbar(self, maximum=100)
        self.prog.pack(fill="x", pady=4)
        self.logbox = tk.Text(self, height=3, state="disabled", font=("Segoe UI", 11), padx=8, pady=2)
        self._layout()
        self.update_buttons()
        self.loading = False
        self.after(200, self.auto_start)

    def _layout(self):
        """pack gives space to the widgets in packing order: first the bottom (log, progress, buttons, player, text boxes),
        then the top rows, and only then the table gets the remaining space, so the log never disappears off the edge."""
        for w in self.pack_slaves():
            w.pack_forget()
        top_widgets = [w for w in self.winfo_children()]
        # find the containers through their children
        bottom = [self.logbox, self.prog, self.b_save.master, self.b_play.master.master, self.tgt_text.master]
        for w in bottom:
            w.pack(side="bottom", fill="x", pady=(10, 0))
        self.logbox.pack_configure(pady=(10, 0))
        for w, gap in zip(self._top_frames, (6, 10, 12, 12)):    # fields and rows do not stick together: equal spacing between all blocks
            w.pack(side="top", fill="x", pady=(0, gap))
        self.tree.master.pack(side="top", fill="both", expand=True)

    # ---------- locking the interface while loading ----------
    def lock(self, on):
        self.loading = on
        self.status_lbl.config(text=_("Завантаження… зачекайте") if on else "")

        def walk(w):
            for c in w.winfo_children():
                if c in (self.prog, self.status_lbl, self.logbox) or isinstance(c, ttk.Scrollbar):
                    continue
                try:
                    c.state(["disabled"] if on else ["!disabled"])
                except (tk.TclError, AttributeError):
                    try:
                        c.configure(state="disabled" if on else "normal")
                    except tk.TclError:
                        pass
                walk(c)
        walk(self)
        if not on:
            self.ref_text.config(state="disabled")
            self.update_buttons()
            self.on_select()

    def auto_start(self):
        """On entry: if the project has no translation or voice-over, download the full pack without asking (this is a translation tool and needs everything),
        then unpack the English from the game and connect the Ukrainian. The tool writes nothing to the game: installation happens only in the installer window."""
        self.ref_lang, self.tgt_lang = "en", "uk"
        self.lock(True)
        pack = self.pack_dir
        if install.has_content(pack) and install.has_voice(pack):
            self._after_content()
            return

        def fetch(log, prog):
            release = download.fetch_release(timeout=15)
            if not release:
                log(_("Немає з'єднання з інтернетом: переклад і озвучення не завантажено."))
                return None
            download.download_content(release, pack, True, prog, log)
            return True
        self.worker.run(fetch, lambda res, err: self._after_content())

    def _after_content(self):
        gd, proj = self.app.game_dir, self.proj_var.get()
        self.has_pack = install.has_content(self.pack_dir)
        self.has_voice = install.has_voice(self.pack_dir)

        def job(log, prog):
            for lg in ("en", "uk"):
                if lg == "uk" and repo.is_content_project(proj):
                    self.ensure_uk(proj, log, prog)
                    continue
                project.ensure_language(gd, lg, proj, prog, log)
            return True

        def done(res, err):
            self.lock(False)
            if not err:
                self.reload_rows()

        self.worker.run(job, done)

    def ensure_uk(self, proj, log, prog):
        """In a fork project the Ukrainian is already unpacked (uk/loca_uk_texts.csv, uk/audio): nothing needs to be unpacked or built."""
        log(_("Мова {0}: беремо з репозиторію контенту (uk/), без перетворень.").format("uk"))

    # ---------- service ----------
    def log(self, msg):
        self.logbox.config(state="normal")
        self.logbox.insert("end", msg + "\n")
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    def progress(self, i, n, msg):
        self.prog.config(value=100 * i / max(n, 1))
        self.status_lbl.config(text=f"{msg}  {100 * i / max(n, 1):.0f}%" if self.loading else "")

    def dirty(self):
        return bool(self.pend_t) or bool(project.list_pending_audio(self.proj_var.get(), self.tgt_lang))

    def update_buttons(self):
        s = project.summary(self.proj_var.get(), self.tgt_lang) if self.tgt_lang else {"texts": 0, "audio": 0}
        has = s["texts"] or s["audio"] or self.pend_t
        self.chg_label.config(text=_("Змін: текстів {0}, кліпів {1}").format(len(self.pend_t), s['audio']) if has else _("Змін немає"))
        for b in (self.b_save, self.b_disc):
            b.state(["!disabled"] if has else ["disabled"])
        self.b_save_install.state(["!disabled"])      # the project can be installed into the game even without new changes

    def pick_project(self):
        d = filedialog.askdirectory(title=_("Тека проєкту"))
        if not d or not self.guard():
            return
        d = self.app.prepare_project_folder(d)
        if not d:
            return
        self.proj_var.set(d)
        self.app.project_dir = d
        st = load_settings()
        st["project_dir"] = d
        save_settings(st)
        self.pack_dir = default_pack_dir(d)
        self.has_pack = install.has_content(self.pack_dir)
        self.has_voice = install.has_voice(self.pack_dir)
        self.auto_start()

    def _ref_changed(self, _event=None):
        """The language chosen as the original disappears from the list of translations (so that there is no "English -> English")."""
        ref = self.ref_cb.get()
        targets = [l for l in self.langs if l != ref]
        self.tgt_cb.configure(values=targets + [_("(нова мова…)")])
        if self.tgt_cb.get() == ref or self.tgt_cb.get() not in targets + [_("(нова мова…)")]:
            self.tgt_cb.set("uk" if "uk" in targets else (targets[0] if targets else ""))

    # ---------- loading languages ----------
    def load_languages(self):
        if not self.guard():
            return
        self.ref_lang = self.ref_cb.get() if self.unlocked else "en"
        tgt = self.tgt_cb.get() if self.unlocked else "uk"
        if tgt == _("(нова мова…)"):
            from tkinter import simpledialog
            tgt = (simpledialog.askstring(APP_NAME, _("Код нової мови (латиницею, напр. 'ro'):")) or "").strip().lower()
            if not tgt:
                return
        if tgt == self.ref_lang:
            messagebox.showwarning(APP_NAME, _("Оригінал і переклад мають бути різними мовами."))
            return
        self.tgt_lang = tgt
        proj, gd = self.proj_var.get(), self.app.game_dir
        self.app.project_dir = proj
        langs = [self.ref_lang] + ([self.tgt_lang] if self.tgt_lang != self.ref_lang else [])

        def job(log, prog):
            have = game.list_languages(gd)
            for i, lg in enumerate(langs):
                if lg == "uk" and repo.is_content_project(proj):
                    self.ensure_uk(proj, log, prog)
                elif project.is_unpacked(proj, lg):
                    log(_("Мова {0}: уже в проєкті.").format(lg))
                elif lg in have:
                    log(_("Розпаковую мову {0} у проєкт…").format(lg))
                    project.unpack_language(gd, lg, proj, prog, log)
                else:
                    log(_("Мова {0}: нової мови в грі нема, створюється порожня таблиця для перекладу.").format(lg))
                    project.new_language(proj, lg, self.ref_lang)
                prog(i + 1, len(langs), _("Мова {0} готова").format(lg))
            log(_("Готово: усі вибрані мови завантажено."))
            return True

        self.worker.run(job, lambda res, err: None if err else self.reload_rows())

    def reload_rows(self):
        proj = self.proj_var.get()
        self.pend_t = project.load_pending_texts(proj, self.tgt_lang)
        ref = {r["name"]: r for r in project.load_rows(proj, self.ref_lang)}
        tgt = {r["name"]: r for r in project.load_rows(proj, self.tgt_lang)}
        self.ref_map = ref
        self.rows = [{"name": n, "ref": ref.get(n, {}).get("wording", ""), "tgt": tgt.get(n, {}).get("wording", ""),
                      "wav_ref": ref.get(n, {}).get("wav", ""), "wav_tgt": tgt.get(n, {}).get("wav", "")}
                     for n in dict.fromkeys(list(ref) + list(tgt))]
        self.fill()
        self.update_buttons()
        n_ref = sum(1 for r in self.rows if r["wav_ref"])
        n_tgt = sum(1 for r in self.rows if r["wav_tgt"])
        missing = sum(1 for r in self.rows if r["wav_ref"] and not r["wav_tgt"])
        self.log(_("Таблиця: {0} рядків; озвучено — {1}: {2}, {3}: {4}.").format(len(self.rows), self.ref_lang, n_ref, self.tgt_lang, n_tgt))
        if not n_ref:
            self.log(_("⚠ Для оригіналу ({0}) немає жодного аудіофайлу.").format(self.ref_lang))
        if not n_tgt:
            self.log(_("⚠ Для перекладу ({0}) немає жодного аудіофайлу (прослуховування недоступне, нове аудіо можна додати вручну).").format(self.tgt_lang))
        elif missing:
            self.log(_("⚠ Без озвучення в перекладі ({0}), хоча в оригіналі воно є: {1} рядків.").format(self.tgt_lang, missing))
        else:
            self.log(_("Усі озвучені рядки оригіналу озвучені й у перекладі ({0}).").format(self.tgt_lang))

    def sort_by(self, col):
        """Click on a header: the 1st click sorts one way, the 2nd the other way, the 3rd removes the sorting.
        For ♪ and ✎ the first click lifts the rows that have the flag."""
        seq = [True, False, None] if col in ("aref", "atgt", "chg") else [False, True, None]
        n = (self.sort_n + 1) % 3 if self.sort_col == col else 0
        self.sort_n = n
        state = seq[n]
        if state is None:
            self.sort_col, self.sort_rev = None, False
        else:
            self.sort_col, self.sort_rev = col, state
        for c, t in self.titles.items():
            arrow = (" ▼" if self.sort_rev else " ▲") if c == self.sort_col else ""
            self.tree.heading(c, text=t + arrow)
        self.fill()

    def fill(self):
        q = self.q_var.get().lower()
        pending_audio = set(project.list_pending_audio(self.proj_var.get(), self.tgt_lang))
        items = []
        for r in self.rows:
            n = r["name"]
            changed = n in self.pend_t or n in pending_audio
            if self.only_var.get() and not changed:
                continue
            tgt = self.pend_t.get(n, r["tgt"])
            if q and q not in n.lower() and q not in r["ref"].lower() and q not in tgt.lower():
                continue
            items.append((n, r["ref"], tgt, bool(r["wav_ref"]), bool(r["wav_tgt"] or n in pending_audio), changed))
        if self.sort_col:
            idx = {"name": 0, "ref": 1, "tgt": 2, "aref": 3, "atgt": 4, "chg": 5}[self.sort_col]
            if idx >= 3:
                # columns ♪o, ♪t, ✎: first by the flag (the direction changes with a click), inside the groups the keys are alphabetical
                items.sort(key=lambda it: it[0].lower())
                items.sort(key=lambda it: it[idx], reverse=self.sort_rev)
            else:
                items.sort(key=lambda it: it[idx].lower(), reverse=self.sort_rev)
        self.tree.delete(*self.tree.get_children())
        for n, ref, tgt, a_ref, a_tgt, changed in items:
            nl = chr(10)
            self.tree.insert("", "end", iid=n, values=(n, ref[:80].replace(nl, " "), tgt[:80].replace(nl, " "),
                                                      "♪" if a_ref else "", "♪" if a_tgt else "", "✎" if changed else ""))
        total = len(self.rows)
        self.shown_label.config(text=_("Рядків: {0}").format(len(items)) + (_(" з {0}").format(total) if len(items) != total else ""))

    # ---------- editing ----------
    def row_of(self, name):
        return next((r for r in self.rows if r["name"] == name), None)

    def on_select(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        self.commit_text()
        self.current = sel[0]
        r = self.row_of(self.current)
        self.ref_text.config(state="normal")
        self.ref_text.delete("1.0", "end")
        self.ref_text.insert("1.0", r["ref"])
        self.ref_text.config(state="disabled")
        self.tgt_text.delete("1.0", "end")
        self.tgt_text.insert("1.0", self.pend_t.get(self.current, r["tgt"]))
        self.tgt_text.edit_modified(False)
        self.refresh_audio_info()
        if self._autoplay:
            self._autoplay = False
            self.start_play()
        else:
            self.stop()

    def on_text_modified(self, _=None):
        self.tgt_text.edit_modified(False)

    def commit_text(self):
        if not self.current:
            return
        r = self.row_of(self.current)
        new = self.tgt_text.get("1.0", "end").rstrip("\n")
        if r is not None and new != r["tgt"] and new != self.pend_t.get(self.current, r["tgt"]):
            self.pend_t[self.current] = new
            project.save_pending_texts(self.proj_var.get(), self.tgt_lang, self.pend_t)
            self.update_buttons()
            if self.tree.exists(self.current):
                self.tree.set(self.current, "tgt", new[:80].replace("\n", " "))
                self.tree.set(self.current, "chg", "✎")
        elif r is not None and new == r["tgt"] and self.current in self.pend_t:
            del self.pend_t[self.current]
            project.save_pending_texts(self.proj_var.get(), self.tgt_lang, self.pend_t)
            self.update_buttons()

    # ---------- audio ----------
    def has_audio(self, r, which):
        if which == "ref":
            return bool(r["wav_ref"])
        return bool(r["wav_tgt"]) or self.has_pending(r)

    def has_pending(self, r):
        return os.path.isfile(project.pending_audio_path(self.proj_var.get(), self.tgt_lang, r["name"]))

    def audio_path(self, r, which):
        """The target audio is the newly loaded one (if any), otherwise the one unpacked from the game."""
        if which == "ref":
            return r["wav_ref"]
        return project.pending_audio_path(self.proj_var.get(), self.tgt_lang, r["name"]) if self.has_pending(r) else r["wav_tgt"]

    def refresh_audio_info(self):
        r = self.row_of(self.current) if self.current else None
        if not r:
            self.audio_info.config(text="")
            for rb in self.rb.values():
                rb.state(["disabled"])
            self.update_transport()
            return
        avail = {k: self.has_audio(r, k) for k in ("ref", "tgt")}
        for k, rb in self.rb.items():
            rb.state(["!disabled"] if avail[k] else ["disabled"])
        if not avail[self.src_var.get()]:
            for k in ("tgt", "ref"):
                if avail[k]:
                    self.src_var.set(k)
                    break
        d_ref = project.duration(r["wav_ref"]) if r["wav_ref"] else 0
        d_tgt = project.duration(self.audio_path(r, "tgt")) if avail["tgt"] else 0
        txt = _("оригінал {0:.2f} с · переклад {1:.2f} с").format(d_ref, d_tgt) + (_(" (завантажене нове)") if self.has_pending(r) else "")
        limit = d_ref
        if self.has_pending(r) and limit and d_tgt > limit + 0.05:
            txt += _("  ⚠ довше за оригінал")
        self.audio_info.config(text=txt)
        self.update_transport()

    def update_transport(self):
        r = self.row_of(self.current) if self.current else None
        can = bool(r) and self.has_audio(r, self.src_var.get())
        mode = self.player.mode()
        self.b_play.state(["!disabled"] if can else ["disabled"])
        self.b_stop.state(["!disabled"] if mode in ("playing", "paused") else ["disabled"])
        has_rows = bool(self.tree.get_children())
        for b in (self.b_prev, self.b_next):
            b.state(["!disabled"] if has_rows else ["disabled"])
        self.b_play.config(text="⏸" if mode == "playing" else "▶")

    def on_source(self):
        """Switching the source (original/target/new): the previous one stops, and if it was playing the new one starts at once (A/B comparison)."""
        was = self.player.mode() == "playing"
        self.stop()
        if was:
            self.start_play()
        self.update_transport()

    def fmt(self, ms):
        s = int(ms // 1000)
        return f"{s // 60}:{s % 60:02d}"

    def start_play(self, from_ms=None):
        r = self.row_of(self.current) if self.current else None
        if not r or not self.has_audio(r, self.src_var.get()) or not self.player.ok:
            return False
        self.player.close()
        path = project.playable(self.audio_path(r, self.src_var.get()))
        if not self.player.load(path):
            self.log(_("Не вдалося відкрити аудіо для відтворення."))
            return False
        self.player.play(from_ms)
        self.playing_src = self.src_var.get()
        self._was_playing = True
        self.update_transport()
        return True

    def toggle_play(self):
        mode = self.player.mode()
        if mode == "playing":
            self.player.pause()
        elif mode == "paused":
            self.player.resume()
        else:
            self.start_play(self.player.position() if mode == "stopped" and self.player.position() else None)
        self.update_transport()

    def stop(self):
        self._was_playing = False
        self.player.stop()
        self.seek_var.set(0)
        self.time_lbl.config(text="0:00 / " + self.fmt(self.player.length()))
        self.update_transport()

    def step(self, d, wrap=True):
        """The next/previous table row that has voice-over of the selected kind, and plays it at once.
        wrap=False (auto-advance after playback ends): at the end of the table we stop instead of looping around."""
        kids = list(self.tree.get_children())
        if not kids:
            return
        # the seek bar and stop refer to the file that is playing; next/previous follow the column of exactly that file
        which = self.playing_src if self.player.mode() in ("playing", "paused") or self._was_playing else self.src_var.get()
        self.src_var.set(which)
        i = kids.index(self.current) if self.current in kids else (-1 if d > 0 else len(kids))
        n = len(kids)
        for _i in range(n):
            i += d
            if not wrap and not 0 <= i < n:
                return
            i %= n
            r = self.row_of(kids[i])
            if r and self.has_audio(r, which):
                self._autoplay = True
                self.tree.selection_set(kids[i])
                self.tree.see(kids[i])
                self.after(10, self._finish_step)
                return

    def _finish_step(self):
        if self._autoplay:  # <<TreeviewSelect>> may not have fired if the row was already selected
            self._autoplay = False
            self.start_play()

    def on_seek_drag(self, value):
        n = self.player.length()
        self.time_lbl.config(text=f"{self.fmt(float(value) / 1000 * n)} / {self.fmt(n)}")

    def on_seek_release(self, _=None):
        self.seeking = False
        if self.player.mode() == "closed":
            r = self.row_of(self.current) if self.current else None
            if not r or not self.has_audio(r, self.src_var.get()):
                return
            if not self.player.load(project.playable(self.audio_path(r, self.src_var.get()))):
                return
        n = self.player.length()
        ms = float(self.seek_var.get()) / 1000 * n
        was = self.player.mode() == "playing"
        self.player.seek(ms, keep_playing=was)
        self._was_playing = was
        self.update_transport()

    def _tick(self):
        """Every 100 ms: the seek bar position, the Play/Pause icon, auto-advance after playback finishes."""
        try:
            mode = self.player.mode()
            if mode in ("playing", "paused") and not self.seeking:
                n = max(self.player.length(), 1)
                pos = self.player.position()
                self.seek_var.set(1000 * pos / n)
                self.time_lbl.config(text=f"{self.fmt(pos)} / {self.fmt(n)}")
            if self._was_playing and mode == "stopped":
                self._was_playing = False
                self.seek_var.set(0)
                if self.loop_var.get():
                    self.start_play()      # repeat the same track
                else:
                    self.step(1, wrap=False)   # playlist: the next row by the column of the file that is playing
            self.update_transport()
        finally:
            self.after(100, self._tick)

    def destroy(self):
        try:
            self.player.close()
        finally:
            super().destroy()

    def load_audio(self):
        if not self.current:
            return
        p = filedialog.askopenfilename(title=_("Нове аудіо для ") + self.current,
                                       filetypes=[(_("Аудіо"), "*.wav *.ogg *.flac *.mp3"), (_("Усі файли"), "*.*")])
        if not p:
            return
        try:
            project.stage_audio(self.proj_var.get(), self.tgt_lang, self.current, p)
        except Exception as e:
            messagebox.showerror(APP_NAME, _("Не вдалося прочитати файл: {0}").format(e))
            return
        self.refresh_audio_info()
        self.update_buttons()
        self.tree.set(self.current, "chg", "✎")
        self.tree.set(self.current, "atgt", "♪")

    # ---------- saving ----------
    def guard(self):
        """Before changing the project or exiting: if there are unsaved changes, ask."""
        self.commit_text()
        if not self.dirty():
            return True
        s = project.summary(self.proj_var.get(), self.tgt_lang)
        choice = ask_apply(self.app, _("Є незбережені зміни: текстів {0}, кліпів {1}.\nЗберегти їх у проєкті перед переходом?").format(len(self.pend_t), s['audio']))
        if choice == "apply":
            return self.save(wait=True)
        if choice == "discard":
            self.discard(ask=False)
            return True
        return False

    def save(self, install_after=False, wait=False):
        """Saves the changes into the project (text and recordings), validates the translation and writes toolcheck.json. "And install": then opens the installer window."""
        self.commit_text()
        s = project.summary(self.proj_var.get(), self.tgt_lang)
        if not (s["texts"] or s["audio"] or self.pend_t):
            if install_after:
                self._go_install()
            return True
        found = validate.check_rows([(n, w, "", "") for n, w in self.pend_t.items()])
        if found:
            lines = [("❌ " if k == "error" else "⚠ ") + f"{n}: {m}" for n, k, m in found[:8]]
            if len(found) > 8:
                lines.append("…")
            if any(k == "error" for _n, k, _m in found) and not messagebox.askyesno(
                    APP_NAME, _("Перевірка перекладу знайшла проблеми у змінених рядках:\n\n{0}\n\nУсе одно записати?").format("\n".join(lines)),
                    default="no"):
                return False
        proj, lang = self.proj_var.get(), self.tgt_lang

        def job(log, prog):
            project.save(proj, lang, log)
            if lang == repo.LANG and repo.is_content_project(proj):      # verification stamp for the pull request
                try:
                    data = toolcheck.write(proj)
                    log(_("Штамп перевірки записано: toolcheck.json (файлів {0}).").format(len(data["files"])))
                except toolcheck.ToolcheckError as e:
                    log(_("Штамп перевірки не записано: {0}").format(e))

        def done(res, err):
            self.reload_rows()
            if install_after and not err:
                self._go_install()
        self.worker.run(job, done)
        if wait:
            while self.worker.busy:
                self.app.update()
            return not self.dirty()
        return True

    def _go_install(self):
        """Go to the installer window and install at once (the button click is already the command): no confirmation; the saved project is installed."""
        self.app.leave_to("install")
        fr = self.app.frame
        if isinstance(fr, InstallFrame):
            fr.after(600, lambda: fr.do_install(confirm=False))

    def discard(self, ask=True):
        if ask and not messagebox.askyesno(APP_NAME, _("Відкинути всі незбережені зміни?")):
            return
        project.discard_pending(self.proj_var.get(), self.tgt_lang)
        self.pend_t = {}
        self.reload_rows()

    def can_leave(self):
        return not self.worker.busy and self.guard()


def error_log_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "D4LocToolkit")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "error.log")


class App(tk.Tk):
    def setup_fonts(self):
        """Readable fonts and sizes that take the screen scaling (DPI) into account."""
        import tkinter.font as tkfont
        scale = max(self.winfo_fpixels("1i") / 96.0, 1.0)
        self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
        self._font_size, self._scale = 12, scale
        size = 12
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=size)
            except tk.TclError:
                pass
        self._configure_styles()

    def _configure_styles(self):
        """Fonts and widget padding; ttk styles apply only to the current theme, so we call this again after it changes."""
        size, scale = self._font_size, self._scale
        st = ttk.Style()
        st.configure(".", font=("Segoe UI", size))
        st.configure("TLabel", font=("Segoe UI", size))   # sv_ttk sets a smaller font for labels on its own
        st.configure("TButton", font=("Segoe UI", size), padding=(12, 6))
        st.configure("Treeview", font=("Segoe UI", size), rowheight=int(32 * scale))
        st.configure("Treeview.Heading", font=("Segoe UI", size + 1, "bold"), padding=(8, 8))
        st.configure("TEntry", font=("Segoe UI", size), padding=(8, 6))      # same height as the buttons (41 px)
        st.configure("TCombobox", font=("Segoe UI", size), padding=(8, 6))
        st.configure("TCheckbutton", font=("Segoe UI", size))
        st.configure("TRadiobutton", font=("Segoe UI", size))

    # ---------- Windows theme on the fly ----------
    def apply_theme(self, dark):
        global DARK
        old = {k: col(k) for k in ("muted", "warn", "text")}
        DARK = dark
        if sv_ttk:
            sv_ttk.set_theme("dark" if dark else "light")
        self._configure_styles()
        mapping = {old[k]: col(k) for k in old}
        st = ttk.Style()
        bg, fg = st.lookup("TEntry", "fieldbackground") or ("#1c1c1c" if dark else "#fdfdfd"), st.lookup("TEntry", "foreground") or col("text")
        self._recolor(self, mapping, bg, fg)
        if hasattr(self, "_flag_frames"):
            self._style_flags()
        if getattr(self, "host", None) is not None:
            self.host.render()

    def _recolor(self, w, mapping, bg, fg):
        """Recolors what ttk does not update itself: labels with an explicit color and plain tk.Text widgets."""
        for c in w.winfo_children():
            if isinstance(c, ttk.Label):
                cur = str(c.cget("foreground"))
                if cur in mapping:
                    c.configure(foreground=mapping[cur])
            elif isinstance(c, tk.Text):
                c.configure(bg=bg, fg=fg, insertbackground=fg)
            self._recolor(c, mapping, bg, fg)

    def _check_theme(self):
        d = system_dark()
        if d != DARK:
            self.apply_theme(d)

    def _poll_theme(self):
        """Fallback in case the Windows message did not arrive: an occasional registry check."""
        try:
            self._check_theme()
        finally:
            self.after(30000, self._poll_theme)

    def _install_theme_hook(self, attempt=0):
        """We subscribe as soon as the window gets an outer shell (the top-level HWND): before that the subscription would attach to the wrong window."""
        self._theme_hooked = self._hook_theme_events()
        if not self._theme_hooked and attempt < 40:
            self.after(250, lambda: self._install_theme_hook(attempt + 1))

    def _hook_theme_events(self):
        """Windows itself reports a theme change with the WM_SETTINGCHANGE message ("ImmersiveColorSet"):
        we subscribe to it through a window subclass, so no registry polling is needed."""
        try:
            import ctypes
            from ctypes import wintypes
            user32, comctl = ctypes.windll.user32, ctypes.windll.comctl32
            WM_SETTINGCHANGE = 0x001A
            proc_t = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
                                        ctypes.c_size_t, ctypes.c_size_t)
            comctl.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
            comctl.DefSubclassProc.restype = ctypes.c_ssize_t
            comctl.SetWindowSubclass.argtypes = [wintypes.HWND, proc_t, ctypes.c_size_t, ctypes.c_size_t]
            comctl.SetWindowSubclass.restype = wintypes.BOOL

            def proc(hwnd, msg, wparam, lparam, uid, ref):
                if msg == WM_SETTINGCHANGE and lparam:
                    try:
                        if ctypes.wstring_at(lparam) == "ImmersiveColorSet":
                            self.after_idle(self._check_theme)
                    except (OSError, ValueError):
                        pass
                return comctl.DefSubclassProc(hwnd, msg, wparam, lparam)

            self._theme_proc = proc_t(proc)   # keep a reference, otherwise the garbage collector destroys the callback
            user32.GetParent.restype = wintypes.HWND
            hwnd = user32.GetParent(self.winfo_id())
            if not hwnd:
                return False
            return bool(comctl.SetWindowSubclass(hwnd, self._theme_proc, 1, 0))
        except (AttributeError, OSError, ImportError):
            return False

    def report_callback_exception(self, exc, val, tb):
        """Exceptions in Tk buttons and timers: in a console-less .exe they are invisible, so we write them to a file and show a dialog."""
        import traceback
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(error_log_path(), "a", encoding="utf-8") as f:
                f.write(text + chr(10))
        except OSError:
            pass
        messagebox.showerror(APP_NAME, _("Помилка: {0}").format(val) + chr(10) + chr(10) + _("Подробиці записано в {0}").format(error_log_path()))

    def __init__(self):
        super().__init__()
        self.title(f"{edition.app_name()} {VERSION} · for Dungeons 4")
        global DARK
        DARK = system_dark()
        if sv_ttk:
            sv_ttk.set_theme("dark" if DARK else "light")
        self.setup_fonts()
        self._theme_hooked = False
        self.after(300, self._install_theme_hook)
        self.after(30000, self._poll_theme)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1500, int(sw * 0.85)), min(1150, int(sh * 0.88))     # there is enough room: the table and fields are not squeezed
        self.geometry("%dx%d+%d+%d" % (w, h, max((sw - w) // 2, 0), max((sh - h) // 3, 0)))
        self.minsize(1000, 820)
        self.game_dir = game.find_game_dir(load_settings().get("game_dir"))
        self.project_dir = load_settings().get("project_dir") or default_project()
        self.frame = None
        self.host = None
        self.screen = "start"
        saved = load_settings().get("ui_lang")
        if saved in i18n.SUPPORTED and not os.environ.get("D4LOC_LANG"):
            i18n.set_language(saved)
        self._build_lang_bar()
        self.remote, self.remote_done = None, False
        threading.Thread(target=self._fetch_remote, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show("start")

    def _build_lang_bar(self):
        """Two flags (Britain for English, Ukraine for Ukrainian); a frame around the active one.
        Deliberately not a drop-down, unlike the target language choice."""
        from PIL import ImageTk
        from .flags import flag_image
        self.lang_bar = ttk.Frame(self, padding=(10, 6))
        self.lang_bar.pack(side="top", fill="x")
        self.lang_var = tk.StringVar(value=i18n.LANG)
        box = ttk.Frame(self.lang_bar)
        box.pack(side="right")
        self._flags, self._flag_frames = {}, {}
        for code in ("en", "uk"):
            self._flags[code] = ImageTk.PhotoImage(flag_image(code, 44, 30), master=self)
            fr = tk.Frame(box, bd=0, highlightthickness=3, cursor="hand2")
            lab = tk.Label(fr, image=self._flags[code], bd=0, cursor="hand2")
            lab.pack()
            for w in (fr, lab):
                w.bind("<Button-1>", lambda e, c=code: self.set_ui_language(c))
            fr.pack(side="left", padx=3)
            self._flag_frames[code] = (fr, lab)
        self._style_flags()

    def _style_flags(self):
        """Frame colors: the active one bright, the inactive one blends into the background. Also called after the theme changes."""
        bg = "#1c1c1c" if DARK else "#fafafa"
        accent = "#60cdff" if DARK else "#0067c0"
        for code, (fr, lab) in self._flag_frames.items():
            on = code == i18n.LANG
            fr.configure(bg=bg, highlightbackground=accent if on else bg, highlightcolor=accent if on else bg)
            lab.configure(bg=bg)

    def set_ui_language(self, lang):
        """Switches the interface language and rebuilds the current screen (the translator's unsaved edits live in the project on disk)."""
        if lang == i18n.LANG:
            return
        busy = getattr(getattr(self, "frame", None), "worker", None)
        if busy is not None and busy.busy:
            messagebox.showinfo(APP_NAME, _("Дочекайтесь завершення поточної дії."))
            self.lang_var.set(i18n.LANG)
            return
        i18n.set_language(lang)
        self.lang_var.set(i18n.LANG)
        self._style_flags()
        st = load_settings()
        st["ui_lang"] = i18n.LANG
        save_settings(st)
        self.show(self.screen)

    def _fetch_remote(self):
        self.remote = download.fetch_release(timeout=4)
        self.remote_done = True

    def show(self, name):
        if name in ("install", "tool") and not game.validate_game_dir(self.game_dir)[0]:
            name = "start"
        self.screen = name
        if getattr(self, "host", None) is not None:
            self.host.destroy()
        self.host = Backdrop(self)
        self.host.pack(fill="both", expand=True)
        self.frame = {"start": StartFrame, "install": InstallFrame, "tool": ToolFrame}[name](self)
        if name == "start":
            self.frame.place(relx=0.5, rely=0.5, anchor="center")
        else:  # a card above the background with margins at the edges
            self.frame.place(relx=0.5, rely=0.5, relwidth=0.97, relheight=0.96, anchor="center")

    def prepare_project_folder(self, path):
        """Checks that the given folder is a fork of the content repository; an empty (or new) one is filled with the latest release with the user's consent.
        Returns the normalized path, or None if the folder was not accepted."""
        if not path:
            return None
        path = os.path.normpath(path)
        kind, msg = ("empty", "") if not os.path.exists(path) else repo.inspect_folder(path)
        if kind == "content":
            repo.ensure_git_exclude(path)
            if msg:
                messagebox.showwarning(APP_NAME, msg)
            return path
        if kind == "empty":
            if not messagebox.askyesno(APP_NAME, _("Тека порожня. Завантажити в неї останній реліз контенту й працювати з нею?\n\nТека не буде підключена до git. Щоб пропонувати правки через pull request, зробіть fork репозиторію контенту, клонуйте його й вкажіть клон як теку проєкту.")):
                return None
            self.config(cursor="watch")
            self.update_idletasks()
            try:
                repo.populate_from_release(path)
            except Exception as e:
                messagebox.showerror(APP_NAME, _("Помилка: {0}").format(e))
                return None
            finally:
                self.config(cursor="")
            return path
        messagebox.showerror(APP_NAME, msg)
        return None

    def open_tool(self):
        """The translator tool: the first thing is choosing the project folder (the languages are unpacked there and the voice pack is stored)."""
        if not game.validate_game_dir(self.game_dir)[0]:
            self.leave_to("tool")  # will show a warning
            return
        st = load_settings()
        saved = st.get("project_dir")
        if saved and repo.inspect_folder(saved)[0] == "content":   # the project folder was already chosen: we no longer ask (it can be changed in the tool itself)
            repo.ensure_git_exclude(saved)
            self.project_dir = saved
            self.leave_to("tool")
            return
        init = saved or self.project_dir
        os.makedirs(init, exist_ok=True) if not os.path.isdir(init) and os.path.isdir(os.path.dirname(init)) else None
        messagebox.showinfo(APP_NAME, _("Оберіть теку проєкту.\n\nЦе має бути ваш fork репозиторію контенту (клон fork) або порожня тека: тоді інструмент завантажить туди останній реліз. Поруч з uk/ (вона вже в репозиторії) він розпакує англійську з вашої гри в теку en/, яка не потрапляє в git, і складатиме правки прямо в uk/, щоб ви могли зробити commit і pull request."))
        d = filedialog.askdirectory(title=_("Тека проєкту перекладача"), initialdir=init if os.path.isdir(init) else os.path.dirname(init),
                                    mustexist=False)
        d = self.prepare_project_folder(d)
        if not d:
            return
        self.project_dir = d
        st["project_dir"] = self.project_dir
        save_settings(st)
        self.leave_to("tool")

    def leave_to(self, name):
        if name in ("install", "tool") and not game.validate_game_dir(self.game_dir)[0]:
            messagebox.showwarning(APP_NAME, _("Спершу вкажіть правильну теку з грою Dungeons 4. Без неї установка й інструмент недоступні.\n\n") + game.validate_game_dir(self.game_dir)[1])
            return
        if self.frame is None or self.frame.can_leave():
            self.show(name)

    def on_close(self):
        if self.frame is None or self.frame.can_leave():
            self.destroy()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # a crisp interface on scaled screens
    except (AttributeError, OSError):
        pass
    App().mainloop()
