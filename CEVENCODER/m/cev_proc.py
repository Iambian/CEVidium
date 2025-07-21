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
            colorfiltertoframes = {1:20, 2:10, 3:5, 4:5, 5:5}
            if colorfilter in colorfiltertoframes:
                frames_per_segment = colorfiltertoframes[colorfilter]
        elif scale == 3:
            colorfiltertoframes = {1:30, 2:15, 3:10, 4:10, 5:10}
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
    END_OF_VIDEO_FRAME_SIZE = 1 # Define the size of the END_OF_VIDEO frame
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
            # its current frame will be a PIL Image of mode RGB, color black.
            # NOTE: Doing it this way allows one to generate a list of
            # Cevideoframe objects without this placeholder frame occupying
            # any position on that list, which is important if the contents of
            # that list requires that its length is equal to the imported video.
            # NOTE 2: That requirement slips in the end, but we account for a
            # trailing frame at that point. So if you get confused if you read
            # later in the file, that's why.
            frame_size_tuple = current_frame
            self.processed_frame = Image.new("RGB", frame_size_tuple, "black")
            self.current_frame = Image.new("RGB", frame_size_tuple, "black")
            self.previous_frame = None
            self.mode = None
            self.framedata = None
            self.palette = None
            self.output_palette = None
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
            if isinstance(mode, Cevideomode):
                self.mode = mode
            else:
                self.mode = Cevideomode(*mode)
            self.buffer_frame(previous_frame)
            #self.processed_frame = Cevideoframe.processframe(self.current_frame, mode, previous_frame)
            if previous_frame is None:
                previous_frame = Cevideoframe(None, self.processed_frame.size, None)
            self.previous_frame = previous_frame
            # We accept either Cevideomode objects, or (ratio, filter, dither)
            self.framedata = bytearray()
        return


    def buffer_frame(self, prevframe:"Cevideoframe|None"):
        ''' This is intended for color-accurate rendering for image array
            buffering. For exports and adaptive color renders, this is what
            you need to use.
            NOTE: Sensible placeholders must be used in case prevframe is None.
        '''
        color_palette = Cevideoframe.select_palette(self, prevframe, self.mode)
        self.palette = color_palette
        
        mode = self.mode
        frameobj = self
        frame = self.current_frame
        ratio = mode.scaleui
        filter = mode.filterui
        dither = mode.ditherui

        if ratio > 1:
            frame_width, frame_height = frame.size
            frame = frame.resize((frame_width // ratio, frame_height // ratio), Image.Resampling.LANCZOS)

        dither = Image.Dither.FLOYDSTEINBERG if dither else 0
        color_palette = Cevideoframe.select_palette(frameobj, prevframe, mode)
        broadcast_multiplier = int(256 / len(color_palette))
        color_palette = _flatten(color_palette * broadcast_multiplier)

        if filter >= 1:
            palimg = Image.new("P", (16,16))    #Actual dimensions won't matter. Is a square in case we need to visually debug.
            palimg.putpalette(color_palette)
            frame = frame.quantize(palette=palimg, dither=dither)
            #frame = frame.convert("RGB")

        self.processed_frame = frame


    @staticmethod
    def select_palette(curframe:"Cevideoframe|Image.Image", prevframe:"Cevideoframe|Image.Image|None", mode:Cevideomode):
        ''' This returns an array of 3-list entries corresponding to the
            palette chosen by Cevideomode.
            NOTE: To use with putpalette, you must broadcast this to a 256
            entry list, then flatten the result.
            NOTE: Further requirements must be met for adaptive palettes.
            NOTE: THE ADAPTIVE IMPORT MUST BE PERFORMED HERE TO AVOID CIRCULAR
                    IMPORTING ERRORS WHEN CEV_ADAPT TRIES TO IMPORT CEV_PROC
        '''
        from .cev_adapt import select_adaptive_palette, select_static_16

        ratio = mode.scaleui
        filter = mode.filterui
        dither = mode.ditherui
        if filter >= 1 and filter <= 4:
            # If palette-agnostic filter is selected, then just output the
            # palette, since it doesn't depend on any extended information.
            # curframe and prevframe doesn't need to contain valid data for
            # this to work.
            if filter == 1:  # Black and white
                color_palette = [(i,i,i) for i in [0, 255]]
            elif filter == 2:
                color_palette = [(i,i,i) for i in [0,64,192,255]]
            elif filter == 3:
                color_palette = [(i+(i<<4),)*3 for i in range(16)]
            else:
                color_palette = select_static_16()
        else:
            color_palette = None
            if filter == 5:
                color_palette = select_adaptive_palette(curframe, prevframe)

        # If we're buffering Cevideoframes for a Cevideolist, we need to store
        # the original selected palette separately from the color-adjusted
        # palette so that adaptive frames doesn't cascade color-adjustments.
        # Failing to do this would quickly wash out the frames.
        if isinstance(curframe, Cevideoframe):
            curframe.palette = color_palette

        # Apply brightness adjustment
        brightness_factor = Cevideomode.brightness()
        adjusted_palette = []
        for r, g, b in color_palette:
            new_r = int(max(0, min(255, r * brightness_factor)))
            new_g = int(max(0, min(255, g * brightness_factor)))
            new_b = int(max(0, min(255, b * brightness_factor)))
            adjusted_palette.append((new_r, new_g, new_b))
        
        # --- Gamma Correction Note ---
        # This gamma correction uses the standard formula:
        # output_color = 255 * (input_color / 255)^(1/gamma_value)
        #
        # Behavior with gamma values:
        # - gamma = 1.0: No change to the color.
        # - gamma < 1.0 (e.g., 0.5): Brightens the image.
        # - gamma > 1.0 (e.g., 2.0): Darkens the image.
        #
        # This is the standard behavior for gamma correction. It is important to note
        # that this is inverse to the current brightness implementation, where higher
        # brightness values result in a brighter image.
        # The input range for gamma is currently 0.0 to 2.0. Gamma values of 0.0
        # will be clamped to a small positive value (e.g., 0.01) to avoid division by zero.
        # -----------------------------
        gamma_factors = Cevideomode.gamma()
        final_palette = []
        for r, g, b in adjusted_palette:
            # Clamp gamma values to avoid division by zero or extreme results
            gamma_r = max(0.01, gamma_factors[0])
            gamma_g = max(0.01, gamma_factors[1])
            gamma_b = max(0.01, gamma_factors[2])

            new_r = int(max(0, min(255, 255 * ((r / 255.0) ** (1.0 / gamma_r)))))
            new_g = int(max(0, min(255, 255 * ((g / 255.0) ** (1.0 / gamma_g)))))
            new_b = int(max(0, min(255, 255 * ((b / 255.0) ** (1.0 / gamma_b)))))
            final_palette.append((new_r, new_g, new_b))

        # For output purposes, use this palette if buffering a Cevideolist.
        if isinstance(curframe, Cevideoframe):
            curframe.output_palette = final_palette
        return final_palette


    @staticmethod
    def processframe(frameobj:"Image.Image", mode: Cevideomode, previmg:"Image.Image|None"=None):
        """ NOTE: This is a display-only function intended for use in either a
            bufferless renderer or as a placeholder image while buffering
            is taking place.
        """
        ratio = mode.scaleui
        filter = mode.filterui
        dither = mode.ditherui
        frame = frameobj if isinstance(frameobj, Image.Image) else frameobj.current_frame

        if ratio > 1:
            frame_width, frame_height = frame.size
            frame = frame.resize((frame_width // ratio, frame_height // ratio), Image.Resampling.LANCZOS)

        dither = Image.Dither.FLOYDSTEINBERG if dither else 0

        if filter >= 1:
            color_palette = Cevideoframe.select_palette(frameobj, previmg, mode)
            broadcast_multiplier = int(256 / len(color_palette))
            color_palette = _flatten(color_palette * broadcast_multiplier)
            palimg = Image.new("P", (16,16))    #Actual dimensions won't matter. Is a square in case we need to visually debug.
            palimg.putpalette(color_palette)
            frame = frame.quantize(palette=palimg, dither=dither)
            #frame = frame.convert("RGB")

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
            palette_bitmap, color_data = self.encode_palette_delta()
            self.framedata.extend(palette_bitmap)
            self.framedata.extend(color_data)
            print(f"Initial Palette frame data: {palette_bitmap.hex()} : {color_data.hex()}")
            return

        current_frame_array = np.array(self.processed_frame.getdata())
        previous_frame_array = np.array(self.previous_frame.processed_frame.getdata())

        if np.array_equal(current_frame_array, previous_frame_array):
            self.framedata.append(Cevideoframe.DUPLICATE_FRAME)
            palette_bitmap, color_data = self.encode_palette_delta()
            self.framedata.extend(palette_bitmap)
            self.framedata.extend(color_data)
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
            #print(f"PARTFRAME (X,Y,W,H): ({min_x},{min_y},{max_x-min_x},{max_y-min_y}), framesize: {cropped_frame.size}:{len(p1)}, exp frame size: {((cropped_frame.size[0]*cropped_frame.size[1]) / alignment)}")
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
        palette_bitmap, color_data = self.encode_palette_delta()
        self.framedata.extend(palette_bitmap)
        self.framedata.extend(color_data)
        print(f"Palette frame data: {palette_bitmap.hex()} : {color_data.hex()}")


    def encode_palette_delta(self) -> tuple[bytes, bytearray]:
        """
        Compares the current frame's palette with the previous frame's palette
        and generates a PALETTE_BITMAP and corresponding Color Data.

        Returns:
            A tuple containing:
            - A 2-byte little-endian PALETTE_BITMAP.
            - A bytearray of Color Data in RGB555 format.
        """
        current_palette = self.output_palette if self.output_palette is not None else []
        previous_palette = self.previous_frame.output_palette if self.previous_frame and self.previous_frame.output_palette is not None else []

        palette_bitmap = 0
        color_data_bytes = bytearray()

        for i in range(1, 16):  # Iterate through hardware palette entries 1 through 15
            current_entry = current_palette[i] if i < len(current_palette) else None
            previous_entry = previous_palette[i] if i < len(previous_palette) else None

            if current_entry is not None and current_entry != previous_entry:
                palette_bitmap |= (1 << (i - 1))  # Set the corresponding bit (0-14 for entries 1-15)

                # Convert RGB to RGB555
                r5 = current_entry[0] >> 3
                g5 = current_entry[1] >> 3
                b5 = current_entry[2] >> 3
                rgb555 = (r5 << 10) | (g5 << 5) | b5

                color_data_bytes.extend(rgb555.to_bytes(2, 'little'))

        return palette_bitmap.to_bytes(2, 'little'), color_data_bytes


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
        self.thread = None
        self.media_file = media_file
        if not mode.frames_per_segment:
            raise ValueError(f"Invalid mode: {mode}. See documentation for valid modes.")
        self.mode = mode
        self._total_frames = len(self.media_file.frames) + 1 # +1 for END_OF_VIDEO frame
        self.frame_list: list[Optional["Cevideoframe"]] = [None] * self._total_frames
        self.is_finished = False
        self.is_cancelled = False
        self._progress = 0
        self._lock = threading.Lock()
        self._pause_event = threading.Event() # Added for pausing/resuming
        self._pause_event.set() # Start in a running state
        self.thread = threading.Thread(target=self._build_frame_list)
        self.has_data_file_data_field_segments = False
        self.field_data:list[bytearray] = []
        self.is_compressed = False
        self.compressed_data = []
        self._total_uncompressed_size = 0
        self._total_compressed_size = 0

    @classmethod
    def from_frame_subset(cls, original_list: "Cevideolist", start: int, end: int) -> Optional["Cevideolist"]:
        """
        Alternate constructor to create a new Cevideolist from a subset of frames
        of an already built Cevideolist.

        Args:
            original_list: The source Cevideolist object with its frame_list already built.
            start: The starting index (inclusive) of the frame subset.
            end: The ending index (inclusive) of the frame subset.

        Returns:
            A new Cevideolist object representing the subset, or None on failure.
        """
        if not isinstance(original_list, Cevideolist):
            print("Error: original_list is not a Cevideolist instance.")
            return None
        if not original_list.is_finished:
            print("Error: original_list frame_list is not yet built.")
            return None

        num_actual_frames = original_list._total_frames - 1 # Exclude the END_OF_VIDEO frame
        if not (0 <= start <= end < num_actual_frames):
            print(f"Error: Invalid start/end indices. start={start}, end={end}, actual_frames={num_actual_frames}")
            return None

        new_list = cls.__new__(cls)

        # Manually set attributes
        new_list.mode = original_list.mode
        new_list.media_file = None # No direct MediaFile for a subset

        # Slice the frame_list and add a new END_OF_VIDEO frame
        new_list.frame_list = original_list.frame_list[start:end+1]

        # Create a keyframe for the slice without damaging the original data structure.
        if new_list.frame_list:
            first_frame_of_slice = new_list.frame_list[0]
            # Create a new Cevideoframe using data from the first item, but with an empty previous frame
            keyframe = Cevideoframe(new_list.mode, first_frame_of_slice.current_frame, None)
            keyframe.encodeframe() # Re-encode to ensure it's a RAW_VIDEO_DATA frame
            new_list.frame_list[0] = keyframe # Copy this new frame into the first slot of the slice

        # Add a new END_OF_VIDEO frame based on the last frame of the subset
        last_frame_of_subset = new_list.frame_list[-1]
        end_frame = Cevideoframe(new_list.mode, last_frame_of_subset.current_frame, last_frame_of_subset)
        end_frame.framedata = bytearray([Cevideoframe.END_OF_VIDEO])
        new_list.frame_list.append(end_frame)

        new_list._total_frames = len(new_list.frame_list)
        new_list.is_finished = True
        new_list._progress = new_list._total_frames
        new_list.is_cancelled = False
        new_list._lock = threading.Lock()
        new_list._pause_event = threading.Event()
        new_list._pause_event.set()
        new_list.thread = None # No thread needed as frames are already built
        new_list.has_data_file_data_field_segments = False
        new_list.field_data = []
        new_list.is_compressed = False
        new_list.compressed_data = []
        new_list._total_uncompressed_size = 0 # Initialize for subset
        new_list._total_compressed_size = 0 # Initialize for subset

        # Calculate _total_uncompressed_size for the subset
        for frame in new_list.frame_list:
            if frame and frame.framedata:
                new_list._total_uncompressed_size += len(frame.framedata)
        
        # Add the size of the END_OF_VIDEO frame that will be appended
        # This is a fixed size (1 byte)
        new_list._total_uncompressed_size += Cevideoframe.END_OF_VIDEO_FRAME_SIZE # Assuming END_OF_VIDEO_FRAME_SIZE is 1 byte

        return new_list

    def _build_frame_list(self):
        try:
            pil_image_list = self.media_file.frames
            print(f"Length of pil_image_list: {len(pil_image_list)}")
            print(f"Processing image list...")
            prev_frame = None
            for i, img in enumerate(pil_image_list):
                #print(f"Type of img: {type(img)}, list length = {len(self.frame_list)} with cancel status: {self.is_cancelled}")
                self._pause_event.wait(0.1) # Wait if paused, with a timeout
                if self.is_cancelled:
                    return
                frame = Cevideoframe(self.mode, img, prev_frame)
                frame.encodeframe()
                with self._lock:
                    self.frame_list[i] = frame
                    self._progress = i + 1
                    self._total_uncompressed_size += len(frame.framedata)
                prev_frame = frame
            self.is_finished = True
            print(f"Image list processed.")

            # Add end-of-video frame
            if not self.is_cancelled:
                if pil_image_list: # Ensure there's at least one frame to base the end_frame on
                    last_frame_obj = self.frame_list[len(pil_image_list) - 1]
                    end_frame = Cevideoframe(self.mode, last_frame_obj.current_frame, last_frame_obj)
                else:
                    # Handle case where pil_image_list is empty (unlikely given current checks)
                    raise ValueError("MediaFile frames list is empty, cannot create end-of-video frame.")

                end_frame.encodeframe()
                end_frame.framedata = bytearray([Cevideoframe.END_OF_VIDEO])
                
                with self._lock:
                    self.frame_list[len(pil_image_list)] = end_frame
                    self._progress = self._total_frames # Mark all frames as processed
                    self._total_uncompressed_size += len(end_frame.framedata) # Add size of END_OF_VIDEO frame
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

    def start_frame_build(self):
        """
        Starts the frame list building process in a separate thread.
        This method should be called externally to control when the build begins.
        """
        if not self.thread.is_alive():
            self.thread.start()
        else:
            print("Frame build thread is already running.")

    def pause_frame_build(self):
        """
        Pauses the frame list building process.
        """
        self._pause_event.clear()

    def resume_frame_build(self):
        """
        Resumes the frame list building process.
        """
        self._pause_event.set()

    def is_build_thread_running(self) -> bool:
        """
        Checks if the frame build thread is currently alive.
        """
        return self.thread.is_alive()

    def get_build_progress(self) -> tuple[int, int]:
        """
        Returns the current progress of the frame list build in a thread-safe manner.
        Returns a tuple (frames_processed, total_frames_expected).
        """
        with self._lock:
            return (self._progress, self._total_frames)

    def __del__(self):
        """
        Ensures the background thread is properly terminated when the object is garbage collected.
        """
        if self.thread and self.thread.is_alive():
            print("Cevideolist object being discarded, attempting to cancel and join thread.")
            self.cancel()
            self._pause_event.set() # Ensure the thread is not blocked on wait()
            self.thread.join(timeout=5) # Wait up to 5 seconds for the thread to finish
            if self.thread.is_alive():
                print("Warning: Cevideolist thread did not terminate gracefully.")

    def collect_encoded_frames(self, frames_to_process: Optional[list['Cevideoframe']] = None):
        """
        Collects encoded frames into a list of sublists (segments).
        If frames_to_process is provided, it uses that list; otherwise, it uses self.frame_list.
        """
        if frames_to_process is None:
            frames_to_process = self.frame_list

        segment_size = self.mode.frames_per_segment
        encoded_frames = []
        current_segment = []
        for frame in frames_to_process:
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
                input_filename = None
                output_filename = None
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

                    segments_compressed += 1
                    callback(segments_compressed, total_segments)
                    with self._lock: # Ensure thread-safe update
                        self._total_compressed_size += len(compressed_segment_data)
                    return compressed_segment_data
                except Exception as e:
                    print(f"Error compressing segment: {e}")
                    # Attempt retry
                    try:
                        print("Retrying compression...")
                        # Run zx7.exe to compress the data
                        # input_filename and output_filename should still be valid from the outer try
                        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                        # Read the compressed data from the output file
                        with open(output_filename, "rb") as output_file:
                            compressed_segment_data = bytearray(output_file.read())
                        segments_compressed += 1
                        callback(segments_compressed, total_segments)
                        with self._lock: # Ensure thread-safe update
                            self._total_compressed_size += len(compressed_segment_data)
                        return compressed_segment_data
                    except Exception as e2:
                        print(f"Error compressing segment after retry: {e2}")
                        raise # Re-raise the exception if retry also fails
                finally:
                    # Clean up temporary files
                    if input_filename and os.path.exists(input_filename):
                        try:
                            os.remove(input_filename)
                        except FileNotFoundError:
                            pass
                    if output_filename and os.path.exists(output_filename):
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

        # Debug statement for compression ratio
        if self._total_uncompressed_size > 0:
            compression_ratio = (self._total_compressed_size / self._total_uncompressed_size) * 100
            print(f"Compression Ratio: {compression_ratio:.2f}% (Compressed: {self._total_compressed_size} bytes, Uncompressed: {self._total_uncompressed_size} bytes)")
        else:
            print("Compression Ratio: N/A (Uncompressed size is 0 bytes)")

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

    def find_end_frame_for_size(self, start_frame: int, size_kb: int) -> int:
        """
        Finds the maximum end frame index such that the exported data for the
        subset (from start_frame to end_frame) approaches but does not exceed
        the specified size_kb. This is done by performing actual compression
        on segments to get an accurate size prediction.

        Args:
            start_frame: The starting index (inclusive) of the frame subset.
            size_kb: The target size in kilobytes.

        Returns:
            An integer indicating the end frame number (inclusive) that fits
            within the size_kb. Returns start_frame - 1 if no frames from
            start_frame can fit, or -1 if the original list is not built or
            inputs are invalid.
        """
        if not self.is_finished:
            print("Error: Cevideolist frame_list is not yet built.")
            return -1

        num_actual_frames = self._total_frames - 1 # Exclude the END_OF_VIDEO frame
        if not (0 <= start_frame < num_actual_frames):
            print(f"Error: Invalid start_frame. start_frame={start_frame}, actual_frames={num_actual_frames}")
            return -1
        if size_kb <= 0:
            print(f"Error: size_kb must be a positive integer. Got {size_kb}")
            return -1

        TARGET_BYTES = size_kb * 1024
        SEGMENT_HEADER_SIZE = 4 # 2 bytes for field ID, 2 bytes for size
        END_OF_VIDEO_FRAME_SIZE = 1 # 1 byte for END_OF_VIDEO marker

        # Create a temporary Cevideolist for the subset from start_frame to the end
        temp_full_list = Cevideolist.from_frame_subset(self, start_frame, num_actual_frames - 1)
        if temp_full_list is None:
            print("Error: Could not create temporary Cevideolist for size estimation.")
            return -1 # Indicates a problem with subset creation

        # Collect and compress all segments for this temporary full subset
        encoded_segments = temp_full_list.collect_encoded_frames()
        
        def dummy_callback(current, total):
            pass # No actual progress reporting needed for this internal calculation

        # Perform actual compression on all segments of the temporary list
        # This will populate temp_full_list._total_compressed_size
        compressed_segments_data = temp_full_list.compress_encoded_segments(encoded_segments, dummy_callback)

        # Check if even the first frame (first segment) exceeds the size limit
        # This handles the case where start_frame itself is too large
        if not compressed_segments_data: # No segments were compressed (e.g., empty range)
            return start_frame - 1 # No frames fit

        # Calculate size of the first segment + EOV frame
        first_segment_size_with_header = len(compressed_segments_data[0]) + SEGMENT_HEADER_SIZE
        if (first_segment_size_with_header + END_OF_VIDEO_FRAME_SIZE) > TARGET_BYTES:
            return start_frame - 1 # Even the first frame is too large

        current_total_size = 0
        found_end_frame = start_frame - 1 # Default to no frames fitting

        # Iterate through the actually compressed segments to find the end_frame
        for seg_idx, compressed_segment in enumerate(compressed_segments_data):
            segment_size_with_header = len(compressed_segment) + SEGMENT_HEADER_SIZE
            
            # Calculate potential total size if this segment is included
            # The END_OF_VIDEO_FRAME_SIZE is added only once at the very end of the video data
            potential_total_size_with_eov = current_total_size + segment_size_with_header + END_OF_VIDEO_FRAME_SIZE

            if potential_total_size_with_eov <= TARGET_BYTES:
                current_total_size += segment_size_with_header
                
                # Calculate the index of the last frame of the current segment within the original frame_list
                # The frames in temp_full_list are relative to start_frame.
                # (seg_idx + 1) * self.mode.frames_per_segment gives the count of frames up to the end of this segment
                # within the temp_full_list's conceptual frame sequence.
                # Subtract 1 for 0-indexing.
                # Add start_frame to get the absolute index in the original list.
                # Cap at num_actual_frames - 1 to ensure it doesn't go beyond the original video's last frame.
                last_frame_in_segment_relative_to_temp_start = (seg_idx + 1) * self.mode.frames_per_segment - 1
                current_segment_end_frame_original_index = start_frame + last_frame_in_segment_relative_to_temp_start
                
                found_end_frame = min(current_segment_end_frame_original_index, num_actual_frames - 1)
            else:
                # Adding this segment would exceed the size limit
                break
        
        return found_end_frame

    def estimate_size_for_range(self, start_frame: int, end_frame: int) -> int:
        """
        Estimates the compressed size in kilobytes for a subset of frames.

        Args:
            start_frame: The starting index (inclusive) of the frame subset.
            end_frame: The ending index (inclusive) of the frame subset.

        Returns:
            The estimated size in kilobytes. Returns 0 if the original list is
            not built or inputs are invalid.
        """
        if not self.is_finished:
            print("Error: Cevideolist frame_list is not yet built.")
            return 0

        num_actual_frames = self._total_frames - 1 # Exclude the END_OF_VIDEO frame
        if not (0 <= start_frame <= end_frame < num_actual_frames):
            print(f"Error: Invalid start/end indices. start={start_frame}, end={end_frame}, actual_frames={num_actual_frames}")
            return 0

        # Create a temporary Cevideolist for the subset
        temp_list = Cevideolist.from_frame_subset(self, start_frame, end_frame)
        if temp_list is None:
            print("Error: Could not create temporary Cevideolist for size estimation.")
            return 0

        # Collect and compress all segments for this temporary subset
        encoded_segments = temp_list.collect_encoded_frames()
        
        def dummy_callback(current, total):
            pass # No actual progress reporting needed for this internal calculation

        # Perform actual compression on all segments of the temporary list
        compressed_segments_data = temp_list.compress_encoded_segments(encoded_segments, dummy_callback)

        # Calculate total size including segment headers and the END_OF_VIDEO frame
        total_size_bytes = 0
        SEGMENT_HEADER_SIZE = 4 # 2 bytes for field ID, 2 bytes for size
        END_OF_VIDEO_FRAME_SIZE = 1 # 1 byte for END_OF_VIDEO marker

        for _ in compressed_segments_data:
            total_size_bytes += len(_) + SEGMENT_HEADER_SIZE
        
        total_size_bytes += END_OF_VIDEO_FRAME_SIZE # Add size for the final END_OF_VIDEO marker

        return ceil(total_size_bytes / 1024) # Return size in KB
