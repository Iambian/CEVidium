import tkinter as tk
from tkinter import ttk, filedialog, Toplevel, Label, Tk
from tkinter.ttk import Progressbar
from tktooltip import ToolTip
from PIL import Image, ImageTk
from tkinterdnd2 import TkinterDnD, DND_FILES
import traceback
from itertools import chain
import os
import threading
import queue
import ast

from . import cev_in, cev_proc, cev_out

# Set to None to ignore. Set to valid filepath to autoload media file on startup.
DEBUG_FILE_INIT = "tests/fdumpster.mp4"
DEBUG_FILE_INIT = None

# Debug variable to immediately show the trim toolbar on startup
DEBUG_INSPECT_TRIM_TOOLBAR = False

def _flatten(iterable):
    return list(chain.from_iterable(iterable))

class CevencoderUI:
    def __init__(self, master):
        self.master:TkinterDnD.Tk = master
        master.title("CEVidium Media Encoder")

        self.media_file:cev_in.MediaFile = None
        self.current_frame = None
        self.is_playing = False
        self.cevideolist_cache: dict[cev_proc.Cevideomode, cev_proc.Cevideolist] = {}
        self.active_cevideolist: cev_proc.Cevideolist = None
        self.status_update_job = None
        self.sync_gamma_var = tk.BooleanVar(value=True)

        # Row layout constants
        VIDEOFRAME_ROW = 1
        MEDIA_TOOLBAR_ROW = 2
        SCROLLBAR_ROW = 3
        EXPORT_DETAILS_ROW = 4
        STATUS_BAR_ROW = 5

        # Video Display Area
        self.canvas_width = 640
        self.canvas_height = 480
        self.video_canvas = tk.Canvas(master, width=self.canvas_width, height=self.canvas_height, bg="black")
        self.video_canvas.grid(row=VIDEOFRAME_ROW, column=0, columnspan=5)
        self.video_canvas.create_rectangle(0, 0, self.canvas_width, self.canvas_height, fill="purple")
        self.default_frame = ImageTk.PhotoImage(Image.new("RGB", (1, 1), "purple"))
        self.canvas_image_object_id = self.video_canvas.create_image(0, 0, anchor=tk.NW, image=self.default_frame)
        self.video_canvas.drop_target_register(DND_FILES)
        self.video_canvas.dnd_bind('<<Drop>>', self.drag_and_drop)

        # Scrollbar and Playback Controls
        self.scrollframe = tk.Frame(master)
        self.scrollframe.grid(row=SCROLLBAR_ROW, columnspan=5, sticky='ew')
        self.frame_slider = tk.Scale(self.scrollframe, orient=tk.HORIZONTAL, command=self.update_frame)
        self.frame_slider.pack(side="left", fill=tk.X, expand=True)
        self.play_pause_button = tk.Button(self.scrollframe, text="Play", command=self.toggle_play, width=10)
        self.play_pause_button.pack(side="right", padx=10)

        # Video Info Input Frame
        self.video_info_frame = tk.Frame(master)
        self.video_info_frame.grid(row=EXPORT_DETAILS_ROW, column=0, columnspan=5, sticky="ew", pady=5)
        self.video_name_label = tk.Label(self.video_info_frame, text="Filename:")
        self.video_name_label.pack(side='left')

        # Toolbar Areas
        self.toolbar_frame = tk.Frame(master, height=50, bg="lightgray")
        self.toolbar_frame.grid(row=MEDIA_TOOLBAR_ROW, column=0, columnspan=5, sticky="ew")
        self.toolbar_frame.grid_columnconfigure(4, weight=1) # Configure column 4 to expand

        self.trim_toolbar_frame = tk.Frame(master, height=50, bg="lightgray")
        self.trim_toolbar_frame.grid(row=MEDIA_TOOLBAR_ROW, column=0, columnspan=5, sticky="ew")
        self.trim_toolbar_frame.grid_remove()


        # Trim Toolbar Groups
        TRIM_TOOLBAR_RESET_GROUP = 0
        TRIM_TOOLBAR_FRAME_BOUNDARY_GROUP = 1   #wide. uses 2 slots
        TRIM_TOOLBAR_MEMORY_LIMIT_GROUP = 3
        TRIM_TOOLBAR_EXPORT_GROUP = 4

        # Trim Toolbar Group
        self.trim_toolbar_group = tk.Frame(self.trim_toolbar_frame, bg="lightgray")
        self.trim_toolbar_group.grid(row=0, column=TRIM_TOOLBAR_RESET_GROUP, padx=5)
        self.trim_toolbar_toggle_button = tk.Button(self.trim_toolbar_group, text="▲", width=2, command=self.toggle_toolbars)
        self.trim_toolbar_toggle_button.grid(row=0, column=0, padx=2, pady=2)
        self.clear_button = tk.Button(self.trim_toolbar_group, text="Reset Limits", width=10, command=self.clear_button_action)
        self.clear_button.grid(row=0, column=1, columnspan=2, padx=2, pady=2)

        # Frame Boundary Group
        self.frame_boundary_group = tk.Frame(self.trim_toolbar_frame, bg="lightgray")
        self.frame_boundary_group.grid(row=0, column=TRIM_TOOLBAR_FRAME_BOUNDARY_GROUP, columnspan=2, padx=3)
        # Frame Bound Start Subgroup
        self.frame_boundary_start_group = tk.Frame(self.frame_boundary_group)
        self.frame_boundary_start_group.pack(padx=4, fill='x', side='left')
        ToolTip(self.frame_boundary_start_group, msg="Set video starting frame. You may input the frame number directly, or use the video slider to find a frame then push the set button to set the frame number.")
        self.frame_boundary_start_set = tk.Button(self.frame_boundary_start_group, width=3, text="Set", command=lambda: self.set_frame_spinbox_value("start"))
        self.frame_boundary_start_set.pack(side='left')
        self.frame_boundary_start_spinbox = tk.Spinbox(self.frame_boundary_start_group, from_=0, to=100, width=5, command=lambda: self.set_frame_spinbox_value("start", value=self.frame_boundary_start_spinbox.get(), from_spinbox=True), state='readonly')
        self.frame_boundary_start_spinbox.pack(side='right')
        # Frame Bound End Subgroup
        self.frame_boundary_end_group = tk.Frame(self.frame_boundary_group)
        self.frame_boundary_end_group.pack(padx=4, fill='x', side='right')
        ToolTip(self.frame_boundary_end_group, msg="Set video ending frame. You may input the frame number directly, or use the video slider to find a frame then push the set button to set the frame number. This number can also be autofilled by setting a memory limit. Setting a memory limit also sets this number. You should set a starting number before setting this number.")
        self.frame_boundary_end_set = tk.Button(self.frame_boundary_end_group, width=3, text="Set", command=lambda: self.set_frame_spinbox_value("end"))
        self.frame_boundary_end_set.pack(side='left')
        self.frame_boundary_end_spinbox = tk.Spinbox(self.frame_boundary_end_group, from_=0, to=100, width=5, command=lambda: self.set_frame_spinbox_value("end", value=self.frame_boundary_end_spinbox.get(), from_spinbox=True), state='readonly')
        self.frame_boundary_end_spinbox.pack(side='right')
        # Memory Limit Group
        self.memory_limit_group = tk.Frame(self.trim_toolbar_frame, bg="lightgray")
        self.memory_limit_group.grid(row=0, column=TRIM_TOOLBAR_MEMORY_LIMIT_GROUP, padx=7)
        self.kb_label = tk.Label(self.memory_limit_group, text="KB")
        self.kb_label.grid(row=0, column=1, padx=0, pady=2)
        self.memory_limit_textvar = tk.StringVar()
        self.memory_limit_input = tk.Entry(self.memory_limit_group, justify='right', width=5, textvariable=self.memory_limit_textvar)
        self.memory_limit_input.grid(row=0, column=0, padx=0, pady=2)
        self.memory_limit_input.insert(0, "0")
        memory_limit_tooltip_text = "Input memory limit (in KB). The encoder will estimate the maximum length of the video based on encoding settings and memory limit. Set this to 0 to disable limits"
        ToolTip(self.kb_label, msg=memory_limit_tooltip_text)
        ToolTip(self.memory_limit_input, msg=memory_limit_tooltip_text)
        validation = (self.master.register(self.validate_number_input), '%P')
        self.memory_limit_input.config(validate="key", validatecommand=validation)

        # Main Toolbar Groups
        MAIN_TOOLBAR_IMPORT_GROUP = 0
        MAIN_TOOLBAR_RATIO_GROUP = 1
        MAIN_TOOLBAR_FILTER_GROUP = 2
        MAIN_TOOLBAR_DITHER_GROUP = 3

        # Color Settings Button
        self.color_settings_button = tk.Button(self.toolbar_frame, text="⚙️", command=self.open_color_settings_modal)
        self.color_settings_button.grid(row=0, column=4, padx=2, pady=2, sticky="e") # Column 4 for right alignment

        # Import Media Group
        self.import_media_group = tk.Frame(self.toolbar_frame, bg="lightgray")
        self.import_media_group.grid(row=0, column=MAIN_TOOLBAR_IMPORT_GROUP, padx=5)
        self.toolbar_toggle_button = tk.Button(self.import_media_group, text="▼", width=2, command=self.toggle_toolbars)
        self.toolbar_toggle_button.grid(row=0, column=0, padx=2, pady=2)
        self.import_button = tk.Button(self.import_media_group, text="Import Media", command=self.import_media)
        self.import_button.grid(row=0, column=1, padx=2, pady=2)

        # Ratio Group
        self.ratio_group = tk.Frame(self.toolbar_frame, bg="lightgray")
        self.ratio_group.grid(row=0, column=MAIN_TOOLBAR_RATIO_GROUP, padx=5)
        self.ratio_var = tk.IntVar(value=1)
        self.ratio_buttons = {}
        def set_ratio(ratio):
            self.ratio_var.set(ratio)
            self.update_export_button_state()
            for r, button in self.ratio_buttons.items():
                button.config(relief=tk.SUNKEN if r == ratio else tk.RAISED)
            self.update_frame(self.frame_slider.get())
        self.ratio_1_button = tk.Button(self.ratio_group, text="/1", width=2, height=1, command=lambda: set_ratio(1))
        self.ratio_2_button = tk.Button(self.ratio_group, text="/2", width=2, height=1, command=lambda: set_ratio(2))
        self.ratio_3_button = tk.Button(self.ratio_group, text="/3", width=2, height=1, command=lambda: set_ratio(3))
        self.ratio_buttons = {1: self.ratio_1_button, 2: self.ratio_2_button, 3: self.ratio_3_button}
        self.ratio_1_button.grid(row=0, column=0, padx=2, pady=2)
        self.ratio_2_button.grid(row=0, column=1, padx=2, pady=2)
        self.ratio_3_button.grid(row=0, column=2, padx=2, pady=2)
        set_ratio(1)

        # Filter Group
        self.filter_group = tk.Frame(self.toolbar_frame, bg="lightgray")
        self.filter_group.grid(row=0, column=MAIN_TOOLBAR_FILTER_GROUP, padx=5)
        self.filter_var = tk.IntVar(value=0)
        self.filter_buttons = {}
        filter_options = ["N/A", "B/W", "GS:4", "GS:16", "C:16", "Adaptive"]
        def set_filter(filter_type):
            self.filter_var.set(filter_type)
            for f, button in self.filter_buttons.items():
                button.config(relief=tk.SUNKEN if f == filter_type else tk.RAISED)
            self.update_export_button_state()
            self.update_frame(self.frame_slider.get())
        for i, option in enumerate(filter_options):
            button = tk.Button(self.filter_group, text=option, width=5, height=1, command=lambda i=i: set_filter(i))
            button.grid(row=0, column=i, padx=2, pady=2)
            self.filter_buttons[i] = button
        set_filter(0)

        # Dither Group
        self.dither_group = tk.Frame(self.toolbar_frame, bg="lightgray")
        self.dither_group.grid(row=0, column=MAIN_TOOLBAR_DITHER_GROUP, padx=5)
        self.dither_var = tk.BooleanVar(value=False)
        def toggle_dither():
            self.update_frame(self.frame_slider.get())
        self.dither_checkbutton = tk.Checkbutton(self.dither_group, text="Dither", bg="lightgray", variable=self.dither_var, command=toggle_dither)
        self.dither_checkbutton.grid(row=0, column=0, padx=2, pady=2)

        # Adaptive Restriction Toggle (hidden from user)
        self.adaptive_restriction_var = tk.BooleanVar(value=False)
        # The checkbutton is created but not packed/gridded, making it hidden.
        # Its command is still linked to update_export_button_state for internal logic.
        tk.Checkbutton(self.dither_group, text="Adaptive Export Restriction", bg="lightgray", variable=self.adaptive_restriction_var, command=self.update_export_button_state)

        # Video Name Entry and Tooltip
        self.video_name_entry = tk.Entry(self.video_info_frame, font='TkFixedFont', width=9) 
        self.video_name_entry.pack(side='left')
        self.video_name_entry.insert(0, "UNTITLED")
        ToolTip(self.video_name_entry, msg="Video name must be 1-8 alphanumeric characters, uppercase only, and the first character cannot be a digit.")

        # Video Title Input
        self.video_title_label = tk.Label(self.video_info_frame, text=" Title:")
        self.video_title_label.pack(side='left')
        self.video_title_entry = tk.Entry(self.video_info_frame)
        self.video_title_entry.pack(side='left')

        # Video Author Input
        self.video_author_label = tk.Label(self.video_info_frame, text=" Author:")
        self.video_author_label.pack(side='left')
        self.video_author_entry = tk.Entry(self.video_info_frame)
        self.video_author_entry.pack(side='left')

        # Export Video Button
        self.export_button = tk.Button(self.video_info_frame, text="Export Video", command=lambda: self.export_video(
            self.video_name_entry.get(),
            self.video_title_entry.get(),
            self.video_author_entry.get()
        ), state=tk.DISABLED)
        self.export_button.pack(side='right', padx=10)
        ToolTip(self.export_button, msg=self._get_export_tooltip_message)
        self.video_name_entry.bind("<KeyRelease>", lambda event: self.update_export_button_state())
        self.toolbar_toggle_button_tooltip = ToolTip(self.toolbar_toggle_button, msg=self._get_toolbar_toggle_tooltip_message)

        # Status Bar
        self.status_bar = tk.Label(master, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=STATUS_BAR_ROW, column=0, columnspan=5, sticky="ew")

        # Debugging init
        if DEBUG_FILE_INIT and os.path.exists(DEBUG_FILE_INIT):
            self.import_media(filepath=DEBUG_FILE_INIT)
        
        self.update_export_button_state() # Set initial state of buttons

        # Ensure trim toolbar is visible if debug flag is set, overriding other initializations
        if DEBUG_INSPECT_TRIM_TOOLBAR:
            self.toolbar_frame.grid_remove()
            self.trim_toolbar_frame.grid()

    def _get_export_tooltip_message(self):
        messages = []
        if self.media_file is None:
            messages.append("Import a media file.")
        if not self.validate_video_name(self.video_name_entry.get()):
            messages.append("Video name must be 1-8 uppercase alphanumeric characters, first character not a digit.")
        if self.filter_var.get() == 0:
            messages.append("Select a filter (N/A is not allowed for export).")
        if self.ratio_var.get() == 1:
            messages.append("Cannot export with /1 ratio selected.")
        if self.filter_var.get() == 5 and self.adaptive_restriction_var.get(): # 5 is the index for "Adaptive"
            messages.append("Cannot export with 'Adaptive' filter selected (restriction enabled).")

        if not messages:
            return "Export video to a .8xv file."
        else:
            return "Export button disabled:\n" + "\n".join(messages)

    def _get_toolbar_toggle_tooltip_message(self):
        messages = []
        if self.media_file is None:
            messages.append("Import a media file.")
        if not self.validate_video_name(self.video_name_entry.get()):
            messages.append("Video name must be 1-8 uppercase alphanumeric characters, first character not a digit.")
        if self.filter_var.get() == 0:
            messages.append("Select a filter (N/A is not allowed for export).")
        if self.ratio_var.get() == 1:
            messages.append("Cannot use trim toolbar with /1 ratio selected.")
        if self.filter_var.get() == 5 and self.adaptive_restriction_var.get(): # 5 is the index for "Adaptive"
            messages.append("Cannot use trim toolbar with 'Adaptive' filter selected (restriction enabled).")

        if not messages:
            return "Switch to trim toolbar."
        else:
            return "Trim toolbar button disabled:\n" + "\n".join(messages)

    def drag_enter(self, event):
        event.widget.focus_set()
        return 'break'

    def drag_and_drop(self, event):
        filepath:str = event.data
        # Handle Windows-specific filepath formatting and special characters
        if filepath.count(":") > 1:
            print("Error: You may only drag and drop one file at a time.")
            return 'break'
        if filepath[0] == "{" and filepath[-1] == "}":
            filepath = filepath.replace('{', '').replace('}', '')
        if any(c in filepath for c in "{}!?*@#%"):
            print("Error: Filename or path contains special characters.")
            return 'break'
        self.import_media(filepath)
        return 'break'

    def clear_button_action(self):
        self.set_frame_spinbox_value("start", 0)
        if self.media_file:
            self.set_frame_spinbox_value("end", self.media_file.get_frame_count() - 1)
        else:
            self.set_frame_spinbox_value("end", 0) # Reset to 0 if no media file
        self.memory_limit_input.delete(0, tk.END)
        self.memory_limit_input.insert(0, "0")
            
    def validate_number_input(self, new_value):
        self.remove_lead_zero = False
        if new_value == "":
            return True
        if len(new_value) > 4:
            return False
        try:
            int(new_value)
            return True
        except ValueError:
            return False
        
    def toggle_toolbars(self):
        if self.toolbar_frame.winfo_ismapped():
            self.toolbar_frame.grid_remove()
            self.trim_toolbar_frame.grid()
        else:
            self.toolbar_frame.grid()
            self.trim_toolbar_frame.grid_remove()

    def update_export_button_state(self):
        # Update export button state based on video name validity, filter selection, media file load status, ratio, and adaptive restriction.
        try:
            is_valid_name = self.validate_video_name(self.video_name_entry.get())
            is_filter_selected = self.filter_var.get() != 0
            is_media_file_loaded = self.media_file is not None
            is_ratio_one = self.ratio_var.get() == 1
            is_adaptive_filter_selected = self.filter_var.get() == 5 # 5 is the index for "Adaptive"
            is_adaptive_restriction_enabled = self.adaptive_restriction_var.get()

            can_export = is_valid_name and is_filter_selected and is_media_file_loaded and not is_ratio_one
            if is_adaptive_filter_selected and is_adaptive_restriction_enabled:
                can_export = False

            self.export_button.config(state=tk.NORMAL if can_export else tk.DISABLED)
            self.toolbar_toggle_button.config(state=tk.NORMAL if can_export else tk.DISABLED)

            # If the toolbar toggle button becomes disabled and the trim toolbar is active, switch back to main.
            # This logic should be skipped if DEBUG_INSPECT_TRIM_TOOLBAR is True
            if not DEBUG_INSPECT_TRIM_TOOLBAR and not can_export and self.trim_toolbar_frame.winfo_ismapped():
                self.toggle_toolbars()
        except:
            pass

    # Validation function for video name
    @staticmethod
    def validate_video_name(name):
        if not (1 <= len(name) <= 8):
            return False
        if not name.isalnum():
            return False
        if not name.isupper():
            return False
        if name[0].isdigit():
            return False
        return True

    def create_import_dialog(self):
        self.import_dialog = Toplevel(self.master)
        self.import_dialog.title("Importing video...")
        self.import_dialog.resizable(False, False)

        # Calculate the center position relative to the main window
        x = (self.master.winfo_width() // 2) - (200 // 2) + self.master.winfo_x()
        y = (self.master.winfo_height() // 2) - (50 // 2) + self.master.winfo_y()
        self.import_dialog.geometry(f"200x50+{x}+{y}")

        # Remove the maximize/minimize buttons
        self.import_dialog.attributes('-toolwindow', True)
        self.import_dialog.grab_set()

        # Disable the close button
        self.import_dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        self.progress_label = Label(self.import_dialog, text="Importing video...", font=("Arial", 12))
        self.progress_label.pack(pady=5)

        self.progressbar = Progressbar(self.import_dialog, orient=tk.HORIZONTAL, length=180, mode='determinate')
        self.progressbar.pack(pady=5)

        self.master.update_idletasks()  # Force update of the GUI

    def destroy_import_dialog(self):
        if hasattr(self, 'import_dialog') and self.import_dialog:
            try:
                if hasattr(self, 'progressbar'):
                    self.progressbar.destroy()
                self.import_dialog.destroy()
            except:
                pass
            self.import_dialog = None

    def update_progress(self, current, total):
        if hasattr(self, 'progressbar'):
            self.progressbar['value'] = current
            self.progressbar['maximum'] = total
            progress_percentage = (current / total) * 100
            self.progress_label.config(text=f"Importing video... ({progress_percentage:.1f}%)")
            self.master.update_idletasks()

    def import_media(self, filepath=None):
        if filepath is None:
            filepath = filedialog.askopenfilename(
                initialdir=".",
                title="Select a video file",
                filetypes=(("Video files", "*.mp4;*.avi;*.mov;*.webm;*.mkv"), ("all files", "*.*"))
            )
        if filepath:
            self.create_import_dialog()
            self.status_bar.config(text="Loading media...")
            self.progress_queue = queue.Queue()

            def import_thread_target():
                try:
                    self.media_file = cev_in.MediaFile(filepath, progress_callback=self.progress_queue.put)
                    self.master.after(0, self._post_import_success)
                except Exception as e:
                    self.master.after(0, lambda: self._post_import_failure(e))
                finally:
                    self.master.after(100, self.destroy_import_dialog)
                    self.stop_polling = True

            threading.Thread(target=import_thread_target).start()
            self.stop_polling = False
            self.poll_progress()

    def _post_import_success(self):
        self.frame_slider.config(from_=0, to=self.media_file.get_frame_count() - 1)
        self.status_bar.config(text="Media loaded successfully.")
        self.toolbar_toggle_button.config(state=tk.NORMAL)
        self.update_export_button_state()
        self.frame_boundary_start_spinbox.config(to=self.media_file.get_frame_count() - 1)
        self.frame_boundary_end_spinbox.config(to=self.media_file.get_frame_count() - 1)
        self.set_frame_spinbox_value("end", self.media_file.get_frame_count() - 1) # Set end frame to last frame

        # Clear existing Cevideolist objects and create a new one for the current mode
        for cev_list in self.cevideolist_cache.values():
            cev_list.cancel()
        self.cevideolist_cache.clear()

        try:
            current_mode = cev_proc.Cevideomode(self.ratio_var.get(), self.filter_var.get(), self.dither_var.get())
            new_cevideolist = cev_proc.Cevideolist(self.media_file, current_mode)
            self.cevideolist_cache[current_mode] = new_cevideolist
            self.active_cevideolist = new_cevideolist
            self.active_cevideolist.start_frame_build()
            self._start_buffering_status_update()
        except:
            pass
        self.update_frame(0)

    def _post_import_failure(self, e):
        error_message = f"Error loading media: {e}"
        self.status_bar.config(text=error_message)
        print(error_message)
        traceback.print_exc()

    def poll_progress(self):
        if not self.stop_polling:
            try:
                current, total = self.progress_queue.get_nowait()
                self.update_progress(current, total)
            except queue.Empty:
                pass
            self.master.after(100, self.poll_progress)  # Poll every 100 ms

    def update_frame(self, frame_number):
        if not self.media_file:
            return

        try:
            frame: Image = self.media_file.get_frame(int(frame_number))
            if not frame:
                return

            # Check if color settings have changed
            if cev_proc.Cevideomode.is_dirty:
                for cev_list in self.cevideolist_cache.values():
                    cev_list.cancel()
                self.cevideolist_cache.clear()
                self.active_cevideolist = None
                cev_proc.Cevideomode.is_dirty = False
                self._stop_buffering_status_update()

            # Get current mode settings
            current_mode = None # Initialize current_mode outside try-except
            try:
                current_mode = cev_proc.Cevideomode(self.ratio_var.get(), self.filter_var.get(), self.dither_var.get())

                # If active_cevideolist exists and its mode is different, pause it
                if self.active_cevideolist and self.active_cevideolist.mode != current_mode:
                    self.active_cevideolist.pause_frame_build()
                    self.active_cevideolist = None # Clear active_cevideolist as it's no longer current

                # Check if Cevideolist for current mode exists in cache
                if current_mode in self.cevideolist_cache:
                    self.active_cevideolist = self.cevideolist_cache[current_mode]
                    if not self.active_cevideolist.is_complete():
                        self.active_cevideolist.resume_frame_build()
                else:
                    # Create new Cevideolist if not in cache
                    new_cevideolist = cev_proc.Cevideolist(self.media_file, current_mode)
                    self.cevideolist_cache[current_mode] = new_cevideolist
                    self.active_cevideolist = new_cevideolist
                    self.active_cevideolist.start_frame_build()
                    self._start_buffering_status_update()
            except ValueError: # Removed 'as e' and error reporting
                self.active_cevideolist = None
                self._stop_buffering_status_update()
                # No status bar update or console print here, as per user feedback.
                # Existing UI safeguards handle reporting.

            # Attempt to get processed frame from active_cevideolist, otherwise process on the fly
            processed_frame = None
            if self.active_cevideolist and self.active_cevideolist.is_complete():
                # Ensure frame_number is within bounds of the buffered list
                if 0 <= int(frame_number) < len(self.active_cevideolist.frame_list):
                    buffered_frame_obj = self.active_cevideolist.frame_list[int(frame_number)]
                    if buffered_frame_obj:
                        processed_frame = buffered_frame_obj.processed_frame
            
            if not processed_frame:
                # Fallback to on-the-fly processing if not buffered or not yet available
                processed_frame = cev_proc.Cevideoframe.processframe(frame, current_mode)

            # Scale and center image on canvas
            self.current_frame = processed_frame
            img_width, img_height = processed_frame.size
            canvas_width, canvas_height = self.canvas_width, self.canvas_height

            aspect_ratio = img_width / img_height
            if canvas_width / aspect_ratio > canvas_height:
                new_width = int(canvas_height * aspect_ratio)
                new_height = canvas_height
            else:
                new_width = canvas_width
                new_height = int(canvas_width / aspect_ratio)

            scaled_img = processed_frame.resize((new_width, new_height), Image.Resampling.NEAREST)
            self.photo = ImageTk.PhotoImage(scaled_img)

            x_offset = (canvas_width - new_width) // 2
            y_offset = (canvas_height - new_height) // 2

            self.video_canvas.itemconfigure(self.canvas_image_object_id, image=self.photo)
            self.video_canvas.coords(self.canvas_image_object_id, x_offset, y_offset)
        except Exception as e:
            error_message = f"Error displaying frame: {e}"
            self.status_bar.config(text=error_message)
            print(error_message)
            traceback.print_exc()

    def toggle_play(self):
        if self.media_file:
            self.is_playing = not self.is_playing
            if self.is_playing:
                self.play_pause_button.config(text="Pause")
                start_frame = int(self.frame_boundary_start_spinbox.get())
                end_frame = int(self.frame_boundary_end_spinbox.get())
                current_frame = int(self.frame_slider.get())

                if current_frame >= end_frame or current_frame < start_frame:
                    self.frame_slider.set(start_frame)  # Reset to start frame
                    self.update_frame(start_frame)  # Update the frame
                self.play_video()
            else:
                self.play_pause_button.config(text="Play")

    def play_video(self):
        if self.media_file and self.is_playing:
            current_frame_number = self.frame_slider.get()
            end_frame = int(self.frame_boundary_end_spinbox.get())
            if current_frame_number < end_frame:
                self.frame_slider.set(current_frame_number + 1)
                self.update_frame(current_frame_number + 1)
                self.master.after(30, self.play_video)  # Adjust delay for desired frame rate
            else:
                self.is_playing = False
                self.play_pause_button.config(text="Play")

    def export_video(self, video_name, video_title, video_author):
        if not self.media_file:
            return

        folder_path = filedialog.askdirectory(initialdir=".", title="Select export directory")
        if folder_path:
            self.status_bar.config(text="Exporting video...")
            try:
                # Ensure the active_cevideolist is fully built before attempting to trim and export
                if not self.active_cevideolist or not self.active_cevideolist.is_complete():
                    self.status_bar.config(text="Error: Video buffering not complete. Please wait.")
                    return

                start_frame = int(self.frame_boundary_start_spinbox.get())
                end_frame = int(self.frame_boundary_end_spinbox.get())
                
                # Create a new Cevideolist representing only the trimmed portion
                # The from_frame_subset method expects an inclusive end frame, so we pass end_frame - 1
                trimmed_cevideolist = cev_proc.Cevideolist.from_frame_subset(self.active_cevideolist, start_frame, end_frame - 1)

                if trimmed_cevideolist is None:
                    self.status_bar.config(text="Error: Could not create trimmed video list for export.")
                    return

                self._stop_buffering_status_update() # Stop status updates during export
                # No need to wait_for_completion on trimmed_cevideolist as it's already built from a complete list
                cev_out.export_cev_files(trimmed_cevideolist, folder_path, video_name, video_title, video_author)
                self.status_bar.config(text=f"Video exported to {folder_path}")
                self._stop_buffering_status_update() # Ensure it's stopped after export
            except Exception as e:
                error_message = f"Error exporting video: {e}"
                self.status_bar.config(text=error_message)
                print(error_message)
                traceback.print_exc()

    def set_frame_spinbox_value(self, boundary_type, value=None, from_spinbox=False):
        if not self.media_file:
            return

        if boundary_type == "start":
            spinbox = self.frame_boundary_start_spinbox
        elif boundary_type == "end":
            spinbox = self.frame_boundary_end_spinbox
        else:
            return

        if value is None:
            value = self.frame_slider.get()

        if not from_spinbox:
            spinbox.config(state="normal")

        spinbox.delete(0, tk.END)
        spinbox.insert(0, value)

        if not from_spinbox:
            spinbox.config(state="readonly")

        if from_spinbox:
            try:
                frame_number = int(value)
                if 0 <= frame_number < self.media_file.get_frame_count():
                    self.frame_slider.set(frame_number)
                    self.update_frame(frame_number)
            except ValueError:
                pass

    def open_color_settings_modal(self):
        modal = Toplevel(self.master)
        modal.title("Color Settings")
        modal.transient(self.master)
        modal.grab_set()
        modal.resizable(False, False)

        # Center the modal over the main window
        self.master.update_idletasks()
        x = self.master.winfo_x() + (self.master.winfo_width() // 2) - (modal.winfo_reqwidth() // 2)
        y = self.master.winfo_y() + (self.master.winfo_height() // 2) - (modal.winfo_reqheight() // 2)
        modal.geometry(f"+{x}+{y}")

        # Brightness Slider
        brightness_frame = tk.Frame(modal)
        brightness_frame.pack(pady=5, padx=10, fill=tk.X)
        tk.Label(brightness_frame, text="Brightness:").grid(row=0, column=0, sticky="w")
        self.brightness_slider = tk.Scale(brightness_frame, from_=0.0, to=2.0, resolution=0.01, orient=tk.HORIZONTAL, length=200)
        self.brightness_slider.set(cev_proc.Cevideomode.brightness())
        self.brightness_slider.grid(row=0, column=1, sticky="ew")
        brightness_frame.grid_columnconfigure(1, weight=1)

        # Gamma Sliders
        gamma_frame = tk.Frame(modal)
        gamma_frame.pack(pady=5, padx=10, fill=tk.X)
        gamma_frame.grid_columnconfigure(0, weight=0) # Column for labels, no expansion
        gamma_frame.grid_columnconfigure(1, weight=1) # Column for sliders, expands

        tk.Label(gamma_frame, text="Gamma (R, G, B):").grid(row=0, column=0, sticky="w")

        # Add Sync Checkbox
        self.sync_gamma_checkbutton = tk.Checkbutton(gamma_frame, text="Sync", variable=self.sync_gamma_var)
        self.sync_gamma_checkbutton.grid(row=0, column=1, sticky="e", padx=5)

        gamma_values = cev_proc.Cevideomode.gamma()
        self.gamma_sliders = []
        colors = ["Red", "Green", "Blue"]
        for i, color in enumerate(colors):
            tk.Label(gamma_frame, text=f"{color}:").grid(row=i+1, column=0, sticky="w")
            slider = tk.Scale(gamma_frame, from_=0.0, to=2.0, resolution=0.01, orient=tk.HORIZONTAL, length=150, command=lambda val, idx=i: self._on_gamma_change(idx, float(val)))
            slider.set(gamma_values[i])
            slider.grid(row=i+1, column=1, sticky="ew")
            self.gamma_sliders.append(slider)

        # OK and Cancel buttons
        button_frame = tk.Frame(modal)
        button_frame.pack(pady=10)

        def apply_settings():
            cev_proc.Cevideomode.brightness(self.brightness_slider.get())
            new_gamma = [s.get() for s in self.gamma_sliders]
            cev_proc.Cevideomode.gamma(new_gamma)
            modal.destroy()
            self.update_frame(self.frame_slider.get()) # Update preview with new settings

        def cancel_settings():
            modal.destroy()

        # Store initial values for reset
        initial_brightness = cev_proc.Cevideomode.brightness()
        initial_gamma = list(cev_proc.Cevideomode.gamma()) # Create a copy

        def reset_settings():
            self.brightness_slider.set(initial_brightness)
            for i, slider in enumerate(self.gamma_sliders):
                slider.set(initial_gamma[i])

        ok_button = tk.Button(button_frame, text="OK", command=apply_settings, width=10)
        ok_button.pack(side=tk.LEFT, padx=5)
        reset_button = tk.Button(button_frame, text="Reset", command=reset_settings, width=10)
        reset_button.pack(side=tk.LEFT, padx=5) # Pack next to OK
        cancel_button = tk.Button(button_frame, text="Cancel", command=cancel_settings, width=10)
        cancel_button.pack(side=tk.RIGHT, padx=5)

        modal.update_idletasks() # Recalculate position after widgets are packed
        x = self.master.winfo_x() + (self.master.winfo_width() // 2) - (modal.winfo_width() // 2)
        y = self.master.winfo_y() + (self.master.winfo_height() // 2) - (modal.winfo_height() // 2)
        modal.wait_window(modal) # Make modal blocking

    def _on_gamma_change(self, changed_slider_index, new_value):
        if self.sync_gamma_var.get():
            for i, slider in enumerate(self.gamma_sliders):
                if i != changed_slider_index:
                    slider.set(new_value)

    def _start_buffering_status_update(self):
        self._stop_buffering_status_update() # Ensure no previous job is running
        self._update_buffering_status()
        self.status_update_job = self.master.after(1000, self._start_buffering_status_update) # Update every 1 second

    def _stop_buffering_status_update(self):
        if self.status_update_job:
            self.master.after_cancel(self.status_update_job)
            self.status_update_job = None

    def _update_buffering_status(self):
        if self.active_cevideolist:
            if self.active_cevideolist.is_build_thread_running() and not self.active_cevideolist.is_complete():
                current, total = self.active_cevideolist.get_build_progress()
                if total > 0:
                    progress_percentage = (current / total) * 100
                    self.status_bar.config(text=f"Buffering: {current}/{total} frames ({progress_percentage:.1f}%)")
                else:
                    self.status_bar.config(text="Buffering: Initializing...")
            elif self.active_cevideolist.is_complete():
                self.status_bar.config(text="Buffering complete.")
                self._stop_buffering_status_update()
            else:
                self.status_bar.config(text="Ready")
                self._stop_buffering_status_update()
        else:
            self.status_bar.config(text="Ready")
            self._stop_buffering_status_update()

def main():
    root = TkinterDnD.Tk()
    root.resizable(0, 0)
    ui = CevencoderUI(root)
    ui.update_frame(0)
    root.mainloop()

if __name__ == "__main__":
    main()
