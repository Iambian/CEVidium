import json
import subprocess
import re
import time
import os
from PIL import Image

SILENCE_MEDIAFILE_OUTPUT = True

class MediaFile:
    """
    Represents a video file.

    Args:
        filename (str): The name of the video file.

        Returns:
            frames (list): An array where all the frames are stored.
        """
    def __init__(self, filename: str, progress_callback=None):
        self.filename = filename
        self.progress_callback = progress_callback
        try:
            subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
        except FileNotFoundError:
            raise FileNotFoundError("ffmpeg is not installed. Please install ffmpeg to use this application.")
        command = [
            "ffprobe",
            "-v", "quiet",
            "-show_format",
            "-show_streams",
            "-print_format", "json",
            self.filename
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if stderr and not SILENCE_MEDIAFILE_OUTPUT:
            print(f"ffprobe stderr: {stderr.decode('utf-8')}")
        if not stdout:
            raise ValueError(f"ffprobe failed to produce any output for file '{filename}'.")
        try:
            info = json.loads(stdout.decode('utf-8'))
        except json.JSONDecodeError:
            raise ValueError(f"ffprobe produced invalid JSON output for file '{filename}'. Output: {stdout.decode('utf-8')}")

        if 'streams' not in info:
            raise ValueError(f"ffprobe output does not contain 'streams' information for file '{filename}'.")

        self.is_video = any(stream['codec_type'] == 'video' for stream in info['streams'])
        if not self.is_video:
            raise ValueError(f"File '{filename}' is not a video file.")
        try:
            video_stream = next((stream for stream in info['streams'] if stream['codec_type'] == 'video'), None)
            if video_stream and 'nb_frames' in video_stream:
                nb_frames = int(video_stream['nb_frames'])
                if nb_frames <= 1:
                    raise ValueError(f"File '{filename}' appears to contain only one frame, which is not considered a video.")
            else:
                # If nb_frames is not available, try to get the duration and frame rate
                if video_stream and 'duration' in video_stream and 'r_frame_rate' in video_stream:
                    duration = float(video_stream['duration'])
                    frame_rate_str = video_stream['r_frame_rate']
                    num, den = map(int, frame_rate_str.split('/'))
                    frame_rate = num / den
                    nb_frames_estimated = duration * frame_rate
                    if nb_frames_estimated <= 1:
                        raise ValueError(f"File '{filename}' appears to contain only one frame, which is not considered a video.")
                else:
                    if not SILENCE_MEDIAFILE_OUTPUT:
                        print("Warning: Could not determine the number of frames. Assuming it's a video.")
        except StopIteration:
            pass

        width = video_stream['width']
        height = video_stream['height']
        new_width = 288
        new_height = int(height * (new_width / width))
        if new_height > 240:
            raise ValueError(f"The scaled height ({new_height}) exceeds the maximum allowed height of 240 pixels.")

        command = [
            "ffmpeg",
            "-i", self.filename,
            "-vf", f"scale={new_width}:{new_height}",
            "-r", "30",
            "-plays", "0",
            "-f", "apng",
            "temp.apng"
        ]

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        total_frames = None
        duration_pattern = re.compile(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})")
        frame_pattern = re.compile(r"frame=\s*(\d+)")

        start_time = time.time()
        try:
            for line in process.stdout:
                if not SILENCE_MEDIAFILE_OUTPUT:
                    print(line.strip())
                if total_frames is None:
                    duration_match = duration_pattern.search(line)
                    if duration_match:
                        hours, minutes, seconds = map(float, duration_match.groups())
                        duration_seconds = hours * 3600 + minutes * 60 + seconds
                        if duration_seconds > 0:
                            total_frames = int(30 * duration_seconds)  # Assuming 30 FPS
                            if not SILENCE_MEDIAFILE_OUTPUT:
                                print(f"Estimated total frames: {total_frames}")
                frame_match = frame_pattern.search(line)
                if frame_match and total_frames:
                    current_frame = int(frame_match.group(1))
                    if self.progress_callback:
                        self.progress_callback((current_frame, total_frames))
                        if not SILENCE_MEDIAFILE_OUTPUT:
                            print(f"CALLBACK CALLED: {current_frame}:{total_frames}")
        except Exception as e:
            if not SILENCE_MEDIAFILE_OUTPUT:
                print(f"Error during ffmpeg conversion: {e}")
        return_code = process.wait()
        if return_code != 0:
            raise ValueError(f"FFmpeg conversion failed with return code {return_code}")

        self.frames = []
        try:
            img = Image.open(open("temp.apng", "rb"), )
            img.load()
            for i in range(img.n_frames):
                img.seek(i)
                newimg = img.convert("RGB")    # A conversion must happen to ensure a copy exists.
                self.frames.append(newimg)
            if not SILENCE_MEDIAFILE_OUTPUT:
                print("APNG conversion successful, and frame processing implemented.")
            if self.progress_callback:
                self.progress_callback((i + 1, img.n_frames))
        except ImportError:
            raise ImportError("Pillow is required to process the APNG file.")
        except FileNotFoundError:
            raise FileNotFoundError("The temporary APNG file 'temp.apng' was not found. This could indicate an issue with the video conversion process.")
        except Exception as e:
            raise ValueError(f"An unexpected error occurred while processing the APNG file: {e}")
        finally:
            if os.path.exists("temp.apng"):
                img.close()
                os.remove("temp.apng")

    def get_frame_count(self):
        """Returns the number of frames in the video."""
        return len(self.frames)

    def get_frame(self, frame_number):
        """Returns the frame at the specified frame number."""
        if 0 <= frame_number < len(self.frames):
            return self.frames[frame_number]
        else:
            return None
