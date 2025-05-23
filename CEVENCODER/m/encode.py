from itertools import chain
from PIL import Image

def _flatten(iterable):
    return list(chain.from_iterable(iterable))

class EncodeParams(object):
    #gs
    BLACK = [0,0,0]
    DARKGRAY = [85,85,85]
    LIGHTGRAY = [170,170,170]
    WHITE = [255,255,255]
    #255 primary
    RED = [255,0,0]
    LIME = [0,255,0]
    BLUE = [0,0,255]
    #255 secondary
    YELLOW = [255,255,0]
    MAGENTA = [255,0,255]
    CYAN = [0,255,255]
    #128 primary
    MAROON = [128,0,0]
    GREEN = [0,128,0]
    DARKBLUE = [0,0,128]
    #128 secondary
    OLIVE = [128,128,0]
    PURPLE = [128,0,128]
    TEAL = [0,128,128]

    palnone= [0]*256
    pal1bw = _flatten([BLACK + WHITE] * 128)
    pal2gs = _flatten([BLACK + DARKGRAY + LIGHTGRAY + WHITE] * 64)
    pal4gs = _flatten([[i+(i<<4)]*3 for i in range(16)] * 16)   #Too many grays
    pal4col= _flatten([
        BLACK, DARKGRAY, LIGHTGRAY, WHITE,
        MAROON, GREEN, DARKBLUE, OLIVE, PURPLE, TEAL,
        RED, LIME, BLUE, YELLOW, MAGENTA, CYAN
    ]*16)

    def __init__(self, paramstring:str):
        cls = self.__class__
        self.params = paramstring
        self.bitdepth = None        #Allowed values: 1, 2, or 4
        self.invbitdepth = None     #Is (8 / self.bitdepth)
        self.adaptive = False       #If has adaptive frames
        self.adaptparams = dict()   #Parameters for adative control
        encoder = paramstring[:2]
        options = paramstring[2:]
        bpp = None
        pal = None
        if encoder == "M1":
            if options == "B1":
                bpp = 1
                pal = cls.pal1bw
            elif options == "G2":
                bpp = 2
                pal = cls.pal2gs
            elif options == "G4":
                bpp = 4
                pal = cls.pal4gs
            elif options == "C4":
                bpp = 4
                pal = cls.pal4col
            elif options == "A4":
                bpp = 4
                pal = cls.palnone
                self.adaptive = True
            else:
                raise ValueError(f"Invalid subcode {options} passed for encoder {encoder}")
        if encoder == "M2":
            if options == "B1":
                bpp = 1
                pal = cls.pal1bw
            elif options == "G2":
                bpp = 2
                pal = cls.pal2gs
            elif options == "G4":
                bpp = 4
                pal = cls.pal4gs
            elif options == "C4":
                bpp = 4
                pal = cls.pal4col
            elif options == "A4":
                bpp = 4
                pal = cls.palnone
                self.adaptive = True
            else:
                raise ValueError(f"Invalid subcode {options} passed for encoder {encoder}")
        else:
            raise ValueError(f"Invalid encoder code used.")
        self.bitdepth = bpp
        if 8 % bpp:
            raise ValueError(f"bpp may only be 1, 2, or 4. Value given: {bpp}")
        self.invbitdepth = 8/bpp

''' Container class for EncodeFrame. '''
class EncodeFrames(object):
    def __init__(self, apng:Image):
        """NOTES: Image object contains .seek(int) to set current frame
        .tell() to return what the current frame is.
        .n_frames (if defined) tells how many frames there are. For iterating.
        Presumably, to use. You seek to the frame, then use the object as if
        the current frame was the only frame. Do your things. At end of
        operation, loop to beginning to seek next frame.

        The file object is never actually closed. You have to use .seek().
        """
        pass

class EncodeFrame(object):
    def __init__(self, ):
        pass





