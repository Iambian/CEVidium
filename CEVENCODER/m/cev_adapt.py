# It's where the adaptive palette stuff is going to be kept.
# Things could get math-heavy, so that's why this is here.
# 

from .cev_proc import Cevideoframe, Cevideomode
from PIL import Image

import numpy as np
from sklearn.cluster import KMeans
from skimage.color import rgb2lab, lab2rgb

def to_3_list(a:list|bytes|bytearray):
    return [[a[i+0], a[i+1], a[i+2]] for i in range(0, len(a), 3)]

def select_static_16():
    # Note: Although this returns 16 colors, the first color slot is ignored
    #       whenever it is used.
    # Spoiler: That ignored slot always contains black.
    color_palette = [
        (0, 0, 0),       # Black
        (64, 64, 64),    # Dark Gray
        (192, 192, 192), # Light Gray
        (255, 255, 255), # White
        (255, 0, 0),     # Red
        (0, 255, 0),     # Lime
        (0, 0, 255),     # Blue
        (255, 255, 0),   # Yellow
        (255, 0, 255),   # Magenta
        (0, 255, 255),   # Cyan
        (128, 0, 0),     # Maroon
        (0, 128, 0),     # Green
        (0, 0, 128),     # Dark Blue
        (128, 128, 0),   # Olive
        (128, 0, 128),   # Purple
        (0, 128, 128)    # Teal
    ]
    return color_palette

def select_adaptive_palette(curframe:Cevideoframe|Image.Image, prevframe:Cevideoframe|None=None):
    if isinstance(curframe, Image.Image) or prevframe is None or prevframe.mode is None:
        # These check if viewing unbuffered image data or viewing the initial
        # frame of a buffered Cevideolist. Relies on short circuiting in case 
        # prevframe isn't a Cevideoframe object.
        img = curframe.current_frame if isinstance(curframe, Cevideoframe) else curframe
        qimg = img.quantize(colors=15)
        color_palette = [[0,0,0]] + to_3_list(qimg.getpalette())
    elif isinstance(curframe, Cevideoframe) and isinstance(prevframe, Cevideoframe):
        # The real magic is called here
        color_palette = select_dynamic_15(curframe, prevframe)
    else:
        # Nothing should reach here. In case it happens, I want the result to
        # be very obvious.
        color_palette = [(i,i,i) for i in [0, 255]] * 8
    #print(color_palette)
    return color_palette




def select_dynamic_15(curframe:Cevideoframe, prevframe:Cevideoframe):
    # Returns a palette of 16. Fixed color black at index 0.
    #
    # The real magic is supposed to happen here. At the moment, it's just
    # a single-frame placeholder that matches the capabilities of the
    # previous encoder. Which... isn't much.
    #
    img = curframe.current_frame
    qimg = img.quantize(colors=15)
    color_palette = [[0,0,0]] + to_3_list(qimg.getpalette())
    return color_palette








