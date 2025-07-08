import os
import subprocess
import tempfile
import threading
import time
import traceback
from math import ceil
from concurrent.futures import ThreadPoolExecutor
from itertools import chain
from typing import Union, Optional
from .cev_in import MediaFile

import numpy as np
from PIL import Image

''' 
Methods that I got from elsewhere that either don't belong in a class or
I haven't decided where they'd go. The following methods are here so far:
* imgtopacked(img:Image.Image, bpp:int|"Cevideomode")
* gridarraypack(a:list[bool])
* _flatten(iterable)

'''
# Accepts a palette image file 8bpp and an output bpp with which to pack the data.
# Outputs packed data.
def imgtopacked(img:Image.Image, bpp:"Cevideomode|int") -> bytearray:
    if img.mode != "P":
        print(f"======== {dir(img)} ===========")
        raise ValueError(f"Source image must be palette image; Got {img.mode} instead.")
    if isinstance(bpp, Cevideomode):
        bpp = bpp.bpp
    a = img.tobytes()
    d = []
    if bpp==1: 
        b,c,m = (8,(0,1,2,3,4,5,6,7),0x01)
    elif bpp==2: 
        b,c,m = (4,(0,2,4,6),0x03)
    elif bpp==4: 
        b,c,m = (2,(0,4),0x0F)
    elif bpp==8: 
        return a
    else: 
        raise ValueError("Invalid bpp ("+str(bpp)+") passed. Only 1, 2, 4, or 8 are accepted.")
    for i in range(len(a)//b):
        t = 0
        for j,k in enumerate(c): 
            t += (a[i*b+j]&m)<<k
        d.append(t)
    return bytearray(d)

#Packs an array filled with True/False values.
#Bytes are set up so that reading from left to right requires right shifting.
def gridarraypack(a:list[bool]) -> bytes:
    output = []
    # Right align the whole thing. The original code did it by using zip/iter
    # trickery and prepending the shortlist of nonaligned data at the start.
    # Here, we do it the *right* way. With clearly-visible slicing and mod math.
    n = 0
    if len(a) % 8:
        for i,v in enumerate(a[:len(a)%8]):
            n |= (v << i)
            #print(f"Lead-in values: {[n,v,i]}")
        output.append(n)
        #print(f"Lead-in blocks: {len(a)%8}, value {n:02X}")
    #
    # All further output is byte-aligned.
    #
    n = 0
    i = 0 # This will be the bit position (0-7)
    for v in a[len(a)%8:]:
        # v is True (1) or False (0)
        # Shift v to its correct position (i) and OR it with n
        n |= (v << i)
        i = (i + 1) % 8 # Increment bit position, wrap around at 8
        if i == 0: # If a full byte is formed
            output.append(n)
            n = 0 # Reset for the next byte
            
    return bytes(output)

def _flatten(iterable):
    return list(chain.from_iterable(iterable))


class Cevideomode(object):
    ''' 
    Contains modes and metadata needed by any conversion processes.
    Set by the UI and read by any consumer of formatted video data.
    Class support: Equality (__eq__) and identity (__hash__)
    Exposed class variable(s):
    cls.is_dirty - If true, gamma or brightness was changed. Is intended for the
        UI to set back to false in response to forcing cache/frame updates.
    Global settings: Combined get/set. Specify arg to set. Always get (after).
    cls.brightness(int)
    cls.gamma(3-list)
    Instance variables:
    scale - Integer divisor. Only 2 and 3 has codec support this time.
    filter - String identifier. See cls.filtermap for mappings from int input.
    dither - Boolean. Whether or not image had dithering applied to it.
    scaleui - Convenience feature. Same as scale for now.
    filterui - Convenience feature. Integer identifier wrt UI radio options
    ditherui - Conveniene feature. Same as dither. No reason to ever change this
    frames_per_segment - Number of encoded frames within each compressable
        segment. Each data file contains various segments arranged to maximize
        amount of space used without splitting segments.
    bpp - Bits Per Pixel. Important for use in bitpacking and byte alignment.
    '''
    #Keep scalemap and filtermap sync'd to UI button options. Filtermap uses encoder-internal names, not UI names.
    scalemap = {1:1, 2:2, 3:3}
    filtermap = {0: 0, 1:"B1", 2:"G2", 3:"G4", 4:"C4", 5:"A4"}
    is_dirty = False
    #
    _brightness = 1.0
    _gamma = [1.0, 1.0, 1.0]

    def __init__(self, scale:int, colorfilter:int, dither:bool=False):
        cls = self.__class__
        self.scale = cls.scalemap[scale]
        self.filter = cls.filtermap[colorfilter]
        self.dither = dither
        # Convenience properties to refer back to the UI elements.
        self.scaleui = scale
        self.filterui = colorfilter
        self.ditherui = self.dither
        filter = self.filter
        frames_per_segment = False
        if scale == 2:
            colorfiltertoframes = {1:20, 2:10, 3:5, 4:5}
            if colorfilter in colorfiltertoframes:
                frames_per_segment = colorfiltertoframes[colorfilter]
        elif scale == 3:
            colorfiltertoframes = {1:30, 2:15, 3:10, 4:10}
            if colorfilter in colorfiltertoframes:
                frames_per_segment = colorfiltertoframes[colorfilter]
        self.frames_per_segment = frames_per_segment
        # Additional properties controlled globally
        self.bpp = 8
        if self.filter in ("B1",):
            self.bpp = 1
        elif self.filter in ("G2",):
            self.bpp = 2
        elif self.filter in ("G4", "C4", "A4"):
            self.bpp = 4

    @classmethod
    def brightness(cls, val=None):
        if val is not None:
            if val != cls._brightness:
                cls.is_dirty = True
            cls._brightness = val
        return cls._brightness
    @classmethod
    def gamma(cls, val=None):
        if val is not None:
            if val != cls._gamma:
                cls.is_dirty = True
            cls._gamma = val
        return cls._gamma
            
    def __hash__(self):
        return hash((self.scale, self.filter, self.dither))
    
    def __eq__(self, other):
        if not isinstance(other, Cevideomode):
            return False
        return (self.scale == other.scale and
                self.filter == other.filter and
                self.dither == other.dither)

class Cevideoframe:
    ''' Contains frame data with a linked list-like structure.
    Instance objects made from an actual PIL image frame contains the following:
    self.current_frame - 288p PIL image object. Used for later reconversions
    self.previous_frame - If a previous frame exists, this is a Cevideoframe
        object containing the prior frame. Do not use this to mark official
        video start.
    self.mode - Cevideomode object if made from PIL image object. None if the
        frame in question doesn't actually exist, but must be present for
        some reason. The iterable definition is never permanently stored.
    self.framedata - Doesn't actually contain anything until self.encodeframe()
        is called. Done this way because calling that method across an entire
        video is a long-running operation, and it's no good to do all that work
        before the user finalizes all the settings they need. Though that
        rationale gets weaker for size-restricted videos since this long-running
        operation *has* to be done earlier. Let the UI take care of that.
    
    The static method build_framelist() is probably never used anywhere since
    the Cevideolist is used to thread the creation of the video list.
    '''
    dummy_node = None
    END_OF_VIDEO = 0x00
    RAW_VIDEO_DATA = 0x01
    PARTIAL_FRAME = 0x02
    DUPLICATE_FRAME = 0x03
    GRID_FRAME = 0x04

    def __init__(self, mode: Cevideomode|tuple|list|None, current_frame: Image.Image|tuple, previous_frame: Optional["Cevideoframe"]):
        ''' Special notes: current_frame must be the original frame that videoinput.MediaFile provides.
            Any image processing that the UI did apart from this class is strictly for show.
            All image processing for purposes of encoding is output to processed_frame.
        '''
        if isinstance(current_frame, tuple):
            # If current_frame is a tuple, object init is in a special case.
            # Special case: Previous frame must be a Cevideoframe object, but
            # there is no frame before the first one. If there wasn't one,
            # one needs to be generated. This is the code that does it.
            # A generated frame will have no mode, no previous frame, and
            # its current frame will be an PIL Image of mode RGB, color black.
            frame_size_tuple = current_frame
            self.processed_frame = Image.new("RGB", frame_size_tuple, "black")
            self.current_frame = Image.new("RGB", frame_size_tuple, "black")
            self.previous_frame = None
            self.mode = None
            self.framedata = None
            return
        else:
            # Otherwise, try to initialize this object as a Cevideoframe object
            # that will carry image data that will be saved.
            if not isinstance(current_frame, Image.Image):
                raise ValueError("Current frame is not PIL Image compatible.")
            if not isinstance(previous_frame,(Cevideoframe, type(None))):
                raise ValueError("Previous frame is not Cevideoframe object or None")
            # There's a bit of a chicken-or-egg problem here wrt previous_frame.
            # I'm going to ignore it for now since a previous frame isn't strictly
            # necessary for processframe to run, but the special case absolutely
            # requires a processed frame before running (due to mode not being allowed).
            self.current_frame = current_frame
            previous_frame = previous_frame if isinstance(previous_frame, Cevideoframe) else None
            self.processed_frame = Cevideoframe.processframe(self.current_frame, mode, previous_frame)
            if previous_frame is None:
                previous_frame = Cevideoframe(None, self.processed_frame.size, None)
            self.previous_frame = previous_frame
            # We accept either Cevideomode objects, or (ratio, filter, dither)
            if isinstance(mode, Cevideomode):
                self.mode = mode
            else:
                self.mode = Cevideomode(*mode)
            self.framedata = bytearray()
        return

    @staticmethod
    def processframe(frameobj:Image.Image, mode: Cevideomode, previmg:Image.Image=None):
        """ Note: previmg is same size as frameobj AFTER frameobj is processed
            via scale. The previmg argument is intended to be used while
            constructing an image array and if a previous image frame is needed
            for purposes of improving possible adaptive frame accuracy.
        """
        ratio = mode.scaleui
        filter = mode.filterui
        dither = mode.ditherui
        frame = frameobj

        if ratio > 1:
            frame_width, frame_height = frame.size
            frame = frame.resize((frame_width // ratio, frame_height // ratio), Image.Resampling.LANCZOS)

        dither = Image.Dither.FLOYDSTEINBERG if dither else 0
        if filter == 1:  # Black and white
            color_palette = [
                0, 0, 0,       # Black
                255, 255, 255, # White
            ]
            palimg = Image.new("P", (16,16))
            palimg.putpalette(color_palette*128)
            frame = frame.quantize(palette=palimg, dither=dither)
            #frame = frame.convert("RGB")
        elif filter == 2:  # Black, white, light gray, and dark gray
            color_palette = [
                0, 0, 0,       # Black
                64, 64, 64,    # Dark Gray
                192, 192, 192, # Light Gray
                255, 255, 255, # White
            ]
            palimg = Image.new("P", (16,16))
            palimg.putpalette(color_palette*64)
            frame = frame.quantize(palette=palimg, dither=dither)
            #frame = frame.convert("RGB")
        elif filter == 3:  # Black, white, and 14 equidistant shades of gray
            color_palette = _flatten([[i+(i<<4)]*3 for i in range(16)] * 16)   #Too many grays
            palimg = Image.new("P", (16,16))
            palimg.putpalette(color_palette)
            frame = frame.quantize(palette=palimg, dither=dither)
            #frame = frame.convert("RGB")
        elif filter == 4:  # Black, dark gray, light gray, white, red, lime, blue, yellow, magenta, cyan, maroon, green, dark blue, olive, purple, and teal
            color_palette = [
                0, 0, 0,       # Black
                64, 64, 64,    # Dark Gray
                192, 192, 192, # Light Gray
                255, 255, 255, # White
                255, 0, 0,     # Red
                0, 255, 0,     # Lime
                0, 0, 255,     # Blue
                255, 255, 0,   # Yellow
                255, 0, 255,   # Magenta
                0, 255, 255,   # Cyan
                128, 0, 0,     # Maroon
                0, 128, 0,     # Green
                0, 0, 128,     # Dark Blue
                128, 128, 0,   # Olive
                128, 0, 128,   # Purple
                0, 128, 128    # Teal
            ]
            palimg = Image.new("P", (16,16))
            palimg.putpalette(color_palette*16)
            frame = frame.quantize(palette=palimg, dither=dither)
            #frame = frame.convert("RGB")
        elif filter == 5:  # Placeholder function
            pass
        return frame

    @staticmethod
    def build_framelist(pilimagelist:list[Image.Image], mode:Cevideomode):
        ''' This builds a list of Cevideoframe objects based on
            full list of PIL-compatible images from MediaFile object.

            Access processed image object by: framelist[index].processed_frame
        '''
        framelist = list()
        previmg = None
        for img in pilimagelist:
            curimg = Cevideoframe(mode, img, previmg)
            framelist.append(curimg)
            previmg = curimg
        return framelist

    def encodeframe(self):
        """
        Examines the contents of the processed frame against the contents
        of the previous frame. The output data will be in self.framedata, which is a bytearray.
        """
        if self.framedata is None:
            return

        if len(self.framedata) > 0:
            return

        if self.previous_frame.mode is None:
            self.framedata.append(Cevideoframe.RAW_VIDEO_DATA)
            self.framedata.extend(imgtopacked(self.processed_frame, self.mode))
            self.framedata.extend(b'\x00\x00')  #adaptive format placeholder
            return

        current_frame_array = np.array(self.processed_frame.getdata())
        previous_frame_array = np.array(self.previous_frame.processed_frame.getdata())

        if np.array_equal(current_frame_array, previous_frame_array):
            self.framedata.append(Cevideoframe.DUPLICATE_FRAME)
            self.framedata.extend(b'\x00\x00')  #adaptive format placeholder
            return

        # Find the smallest possible box that contains all of the pixels that failed to match
        p1 = bytearray()
        diff_indices = np.where(current_frame_array != previous_frame_array)[0]
        if len(diff_indices) > 0:
            min_x = min(diff_indices % self.processed_frame.width)
            max_x = max(diff_indices % self.processed_frame.width)  + 1
            min_y = min(diff_indices // self.processed_frame.width)
            max_y = max(diff_indices // self.processed_frame.width) + 1

            alignment = 8 // self.mode.bpp

            min_x = (min_x // alignment) * alignment
            max_x = ((max_x // alignment) + 1) * alignment
            # Extract a copy of the processed frame's data from the bounding box
            bbox = (min_x, min_y, max_x, max_y)
            cropped_frame = self.processed_frame.crop(bbox)

            # Use imgtopacked() to format that data
            p1 = imgtopacked(cropped_frame, self.mode)
            print(f"PARTFRAME (X,Y,W,H): ({min_x},{min_y},{max_x-min_x},{max_y-min_y}), framesize: {cropped_frame.size}:{len(p1)}, exp frame size: {((cropped_frame.size[0]*cropped_frame.size[1]) / alignment)}")
            assert not cropped_frame.size[0] % alignment and not min_x % alignment 
            assert max_x-min_x and max_y-min_y
            assert len(p1) == ((cropped_frame.size[0]*cropped_frame.size[1]) / alignment)

        # Grid comparison
        p2a = bytearray()
        p2b = []
        grid_size = 8
        frame_width, frame_height = self.processed_frame.size

        for y in range(0, frame_height, grid_size):
            for x in range(0, frame_width, grid_size):
                # Define the coordinates of the current grid cell
                cell_bbox = (x, y, x + grid_size, min(y + grid_size, frame_height))

                # Crop the current cell from both frames
                current_cell = self.processed_frame.crop(cell_bbox)
                previous_cell = self.previous_frame.processed_frame.crop(cell_bbox)

                # Compare the pixel data of the two cells
                current_cell_array = np.array(current_cell.getdata())
                previous_cell_array = np.array(previous_cell.getdata())

                assert isinstance(current_cell, Image.Image)
                assert isinstance(self.mode, Cevideomode)
                #print(f"Cell size: {current_cell.size}")

                if not np.array_equal(current_cell_array, previous_cell_array):
                    # If the cell differs, copy the corresponding cell from the processed image,
                    # format the data using imgtopacked(), then emit to p2a.
                    p2a.extend(imgtopacked(current_cell, self.mode))
                    p2b.append(True)
                else:
                    # If the cell did not differ, then append the value False to p2b
                    p2b.append(False)
        #Verify proper encoded frame size:
        calc_max_numblocks = (frame_width / 8) * ceil(frame_height / 8)
        assert calc_max_numblocks == len(p2b), f"Bitfield size match failure. Expected {calc_max_numblocks}, got {len(p2b)}"
        alignment = 8 // self.mode.bpp
        normal_cell_size = (8*8)/alignment
        truncated_cell_size = ((frame_height%8)*8)/alignment
        if (frame_height/8).is_integer():
            # Evenly-divisible height? Data block size calc is easy!
            calc_datablock_size = sum(p2b)*normal_cell_size
        else:
            # Else, we'll have to calc size piecewise.
            num_blocks_per_row = int(frame_width / 8)
            calc_datablock_size_a = sum(p2b[:-num_blocks_per_row])*normal_cell_size
            calc_datablock_size_b = sum(p2b[-num_blocks_per_row:])*truncated_cell_size
            calc_datablock_size = calc_datablock_size_a + calc_datablock_size_b
            #print(f"Grid data frame size: {calc_datablock_size_a}+{calc_datablock_size_b}={calc_datablock_size}")
        assert calc_datablock_size == len(p2a), f"Datasize match failure. Expected {calc_datablock_size}, got {len(p2a)}"
        #print(f"Grid frame bitfield size: {ceil(len(p2b)/8)}")
        #print(f"Grid frame total expected size: {ceil(len(p2b)/8)+len(p2a)}")

        # Choose which check performed the best with respect to size
        box_performance = len(p1)
        grid_performance = len(p2a) + len(gridarraypack(p2b)) # Use actual packed size of bitfield
        
        # Calculate the expected packed size of a full frame
        alignment = 8 // self.mode.bpp
        full_frame_packed_size = (self.processed_frame.width * self.processed_frame.height) // alignment

        if min(box_performance, grid_performance) >= full_frame_packed_size:
            self.framedata.append(Cevideoframe.RAW_VIDEO_DATA)
            self.framedata.extend(imgtopacked(self.processed_frame, self.mode))
        elif box_performance < grid_performance:
            self.framedata.append(Cevideoframe.PARTIAL_FRAME)
            width = cropped_frame.width
            height = cropped_frame.height
            x = min_x
            y = min_y
            self.framedata.extend(int(x).to_bytes(1, 'little'))
            self.framedata.extend(int(y).to_bytes(1, 'little'))
            self.framedata.extend(width.to_bytes(1, 'little'))
            self.framedata.extend(height.to_bytes(1, 'little'))
            self.framedata.extend(p1)
        else:
            self.framedata.append(Cevideoframe.GRID_FRAME)
            self.framedata.extend(gridarraypack(p2b))
            self.framedata.extend(p2a)
        self.framedata.extend(b'\x00\x00')  # adaptive format placeholder


class Cevideolist:
    ''' 
    A class that converts a MediaFile object to something exportable.

    Object initialization involves threading. After init, immediately call its
    instance method wait_for_completion(). This step provides the following:
    * is_finished - Set to True when this part of the initialization is done.
    * mode - The Cevideomode object passed into init.
    * frame_list - List of Cevideoframe objects.

    After initialization, call collect_encoded_frames() to create a list of
    Cevideoframe lists. Each item in the top-level list is referred to as a
    "segment" and contains at most self.mode.frames_per_segment Cevideoframes.
    Each Cevideoframe is consecutive, and at this stage, so is each segment.
    No instance variables are stored at this step; the output
    of this method is shoved into the next step.

    Call compress_encoded_segments() using the output of collect_encoded_frames()
    and a few other self-explanitory (mostly non-critical) parameters. This is a
    method that uses subprocess to run the compression step on each segment, and
    to silence the annoying console output of each.
    Once this step completes, we get as instance variables:
    * is_compressed - Set to true if successful.
    * compressed_data - List of compressed segments.

    After compression, call build_field_data() to attach formatted metadata to
    each segment. This is important because that metadata is what allows the
    following step to be reversed during decoding.

    Call concatenate_field_data() using the output of build_field_data(). The
    return value of this function is a 2-tuple, the elements being:
    *   A list of bytearrays that had as many formatted segments concatenated
        without threatening to exceed the max file size of a TI-83+ AppVar 
        object. Some steps are missing, but those are filled in during export.
    *   A list of integers whose indices corresponds to the list of bytearrays.
        The integer represents the number of segments in its related bytearray.
    
    NOTE: We don't put some of these obviously export-only features with export
        because we're going to implement a feature to trim videos based on
        filesize. We can't get an accurate prediction without at least
        performing the compression and segment collection step, though these
        will likely need to be modified to accept a different start point. Or
        possibly implement a slice operation for this class and perform the
        compression steps on those slices? This class *does* lend itself well
        towards that operaton, and I did infact look into what it'd take to
        make it usable like a list. Spoiler: I did NOT implement any of it.
        Reading about it made it seem like a total shitshow.
    '''
    def __init__(self, media_file: MediaFile, mode: Cevideomode):
        self.media_file = media_file
        if not mode.frames_per_segment:
            raise ValueError(f"Invalid mode: {mode}. See documentation for valid modes.")
        self.mode = mode
        self.frame_list:list["Cevideoframe"] = []
        self.is_finished = False
        self.is_cancelled = False
        self.thread = threading.Thread(target=self._build_frame_list)
        self.thread.start()
        self.has_data_file_data_field_segments = False
        self.field_data:list[bytearray] = []
        self.is_compressed = False
        self.compressed_data = []

    def _build_frame_list(self):
        try:
            pil_image_list = self.media_file.frames
            print(f"Length of pil_image_list: {len(pil_image_list)}")
            print(f"Processing image list...")
            prev_frame = None
            for img in pil_image_list:
                print(f"Type of img: {type(img)}, list length = {len(self.frame_list)} with cancel status: {self.is_cancelled}")
                if self.is_cancelled:
                    return
                frame = Cevideoframe(self.mode, img, prev_frame)
                frame.encodeframe()
                self.frame_list.append(frame)
                prev_frame = frame
            self.is_finished = True
            print(f"Image list processed.")

            # Add end-of-video frame
            if not self.is_cancelled:
                end_frame = Cevideoframe(self.mode, self.frame_list[-1].current_frame, self.frame_list[-1])
                end_frame.encodeframe()
                end_frame.framedata = bytearray([Cevideoframe.END_OF_VIDEO])
                self.frame_list.append(end_frame)
        except Exception as e:
            print(f"Error building frame list: {e}")
            self.is_cancelled = True
            traceback.print_exc()
            
    def cancel(self):
        self.is_cancelled = True

    def wait_for_completion(self):
        while not self.is_finished and not self.is_cancelled:
            time.sleep(0.1)  # Wait a bit before checking again

    def is_complete(self):
        return self.is_finished

    def collect_encoded_frames(self):
        """Collects encoded frames into a list of sublists."""
        segment_size = self.mode.frames_per_segment
        encoded_frames = []
        current_segment = []
        for frame in self.frame_list:
            current_segment.append(frame)
            if len(current_segment) == segment_size:
                encoded_frames.append(current_segment)
                current_segment = []
        if current_segment:  # Add the last segment if it's not empty
            encoded_frames.append(current_segment)
        return encoded_frames


    def compress_encoded_segments(self, encoded_segments: list[list[Cevideoframe]], callback: callable, cpu_usage: int = 75) -> list[bytearray]:
        num_threads = max(1, int(cpu_usage / 100 * os.cpu_count()))
        compressed_data = []
        total_segments = len(encoded_segments)
        segments_compressed = 0

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            def compress_segment(segment: list[Cevideoframe]):
                nonlocal segments_compressed
                try:
                    # Concatenate frame data into a single bytearray
                    segment_data = bytearray()
                    for frame in segment:
                        segment_data.extend(frame.framedata)

                    # Create temporary files for input and output
                    with tempfile.NamedTemporaryFile(delete=False) as input_file:
                        input_file.write(segment_data)
                        input_filename = input_file.name

                    output_filename = input_filename + ".compressed"

                    # Run zx7.exe to compress the data
                    zx7_path = "tools/zx7.exe"
                    command = [zx7_path, input_filename, output_filename]
                    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                    # Read the compressed data from the output file
                    with open(output_filename, "rb") as output_file:
                        compressed_segment_data = bytearray(output_file.read())

                    # Clean up temporary files
                    try:
                        os.remove(input_filename)
                    except FileNotFoundError:
                        pass
                    try:
                        os.remove(output_filename)
                    except FileNotFoundError:
                        pass

                    segments_compressed += 1
                    callback(segments_compressed, total_segments)
                    return compressed_segment_data
                except Exception as e:
                    print(f"Error compressing segment: {e}")
                    try:
                        print("Retrying compression...")
                        # Run zx7.exe to compress the data
                        zx7_path = "tools/zx7.exe"
                        command = [zx7_path, input_filename, output_filename]
                        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                        # Read the compressed data from the output file
                        with open(output_filename, "rb") as output_file:
                            compressed_segment_data = bytearray(output_file.read())
                        segments_compressed += 1
                        callback(segments_compressed, total_segments)
                        return compressed_segment_data
                    except Exception as e2:
                        print(f"Error compressing segment after retry: {e2}")
                        raise
                finally:
                    # Clean up temporary files
                    try:
                        os.remove(input_filename)
                    except FileNotFoundError:
                        pass
                    try:
                        os.remove(output_filename)
                    except FileNotFoundError:
                        pass

            results = executor.map(compress_segment, encoded_segments)

        for result in results:
            if result:
                compressed_data.append(result)

        self.is_compressed = True
        self.compressed_data = compressed_data
        return compressed_data

    def build_field_data(self, compressed_data: list[bytearray]) -> list[bytearray]:
        """
        Constructs the CEVidium data file's field data from the compressed data list.

        Args:
            compressed_data: A list of compressed data segments.

        Returns:
            A list of bytearrays, where each bytearray represents a field in the CEVidium data file.
        """
        field_data_list = []
        for field_id, segment_data in enumerate(compressed_data):
            field_data = bytearray()
            field_data.extend(field_id.to_bytes(2, 'little'))  # Field ID
            field_data.extend(len(segment_data).to_bytes(2, 'little'))  # Size of data segment
            field_data.extend(segment_data)  # Data segment
            field_data_list.append(field_data)
        return field_data_list

    def concatenate_field_data(self, field_data_list: list[bytearray]) -> tuple[list[bytearray], list[int]]:
        """
        Concatenates the field data bytearrays into larger bytearrays,
        ensuring that each resulting bytearray does not exceed 65400 bytes.

        Args:
            field_data_list: A list of bytearrays representing the field data.

        Returns:
            A tuple containing:
            - A list of concatenated bytearrays.
            - A list of the number of entries in each bytearray.
        """
        concatenated_bytearrays = []
        entry_counts = []
        current_bytearray = bytearray()
        current_entry_count = 0

        for field_data in field_data_list:
            if len(current_bytearray) + len(field_data) <= 65400:
                current_bytearray.extend(field_data)
                current_entry_count += 1
            else:
                concatenated_bytearrays.append(current_bytearray)
                entry_counts.append(current_entry_count)
                current_bytearray = bytearray(field_data)
                current_entry_count = 1

        if current_bytearray:
            concatenated_bytearrays.append(current_bytearray)
            entry_counts.append(current_entry_count)

        return concatenated_bytearrays, entry_counts
