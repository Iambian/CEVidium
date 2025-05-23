import os, subprocess
import ffmpeg
from PIL import Image, ImageTk
from m.util import tobytes, checkdel
from m.encode import EncodeFrames


def readfile(filename:str) -> bytes:
    contents = None
    with open(filename, "rb") as f:
        contents = f.read()
    if contents is None:
        raise IOError(f"File {filename} could not be read.")
    return contents

#Note:  Deprecate use of strings. You should only be passing in binary data.
def writefile(filename:str, data:bytes|bytearray|str, encoding="utf-8") -> None:
    if isinstance(data, str):
        data = data.encode(encoding)
    with open(filename, "wb+") as f:
        f.write(data)

def export8xv(filebase:str, filedata:bytes|bytearray) -> None:
    TI_VAR_PROG_TYPE, TI_VAR_PROTPROG_TYPE, TI_VAR_APPVAR_TYPE = (0x05,0x06,0x15)
    TI_VAR_FLAG_RAM, TI_VAR_FLAG_ARCHIVED = (0x00,0x80)
    if not isinstance(filedata, (bytes, bytearray)):
        filedata = tobytes(filedata)
    # Add size bytes to file data as per (PROT)PROG/APPVAR data structure
    dsl = len(filedata)&0xFF
    dsh = (len(filedata)>>8)&0xFF
    filedata = bytearray([dsl,dsh])+filedata
    # Construct variable header
    vsl = len(filedata)&0xFF
    vsh = (len(filedata)>>8)&0xFF
    vh  = bytearray([0x0D,0x00,vsl,vsh,TI_VAR_APPVAR_TYPE])
    vh += tobytes(filebase.ljust(8,'\x00')[:8])
    vh += bytearray([0x00,TI_VAR_FLAG_ARCHIVED,vsl,vsh])
    # Pull together variable metadata for TI8X file header
    varentry = vh + filedata
    varsizel = len(varentry)&0xFF
    varsizeh = (len(varentry)>>8)&0xFF
    varchksum = sum([i for i in varentry])
    vchkl = varchksum&0xFF
    vchkh = (varchksum>>8)&0xFF
    # Construct TI8X file header
    h  = tobytes("**TI83F*")
    h += bytearray([0x1A,0x0A,0x00])
    h += tobytes("Rawr. Gravy. Steaks. Cherries!".ljust(42)[:42])  #Always makes comments exactly 42 chars wide.
    h += bytearray([varsizel,varsizeh])
    h += varentry
    h += bytearray([vchkl,vchkh])
    # Write data out to file
    writefile(f"{filebase}.8xv", h)
    return

def ensuredir(dirpath):
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath)

def getfilebasename(filepath):
    return os.path.splitext(os.path.basename(filepath))[0]

class MediaMetadata(object):
    """ Instance object contains metadata retrieved from file.

    self.e: Error state. If it is None, then the instance is initialized.
            Otherwise, contains an object that subclasses Exception.
    self.width: Frame width.
    self.height: Frame height.
    self.probedata: Full metadata as returned by ffprobe.
    self.stderr: Output from ffprobe if an error happened when it was called.
    """
    def __init__(self, filepath:str):
        self.e = None
        self.filepath = filepath
        self.width = None
        self.height = None
        self.duration_ts = None
        self.probedata = None
        self.stderr = None
        try:
            if not os.path.exists(filepath):
                raise IOError(f"{filepath} not found.")
            meta = ffmpeg.probe(filepath)
            for stream in meta['streams']:
                if stream['codec_type'] == 'video':
                    self.width = stream['width']
                    self.height = stream['height']
                    self.duration_ts = stream['duration_ts']
                    if self.duration_ts == 1:
                        raise(ValueError(f"{filepath} contains only one image, making it ineligible for conversion."))
                    self.probedata = meta
                    return
            else:
                raise(ValueError(f"{filepath} contains no recognizeable video stream."))
            pass
        except Exception as e:
            self.e = e
            if hasattr(e, "stderr"):
                self.stderr = e.stderr

class MediaFile(object):
    DEFAULT_SCREEN_WIDTH = 288
    MAXIMUN_SCREEN_HEIGHT = 240
    def __init__(self, metadataobj:str|MediaMetadata, hspan=96, *args, **kwargs):
        '''TODO: Add extra arguments in case video requires adjustment to
        combat possible "TOO TALL" errors.
        '''
        if isinstance(metadataobj, str):
            metadataobj = MediaMetadata(metadataobj)
        cls = self.__class__
        screen_width = cls.DEFAULT_SCREEN_WIDTH
        max_screen_height = cls.MAXIMUN_SCREEN_HEIGHT
        self.meta = metadataobj
        self.e = None
        self.stderr = None
        self.tootall = False
        #
        self.outfilepath = None     #TODO: gen this in a "smort" way. w/e it is
        self.outfilepath = "caches/test.png"
        #
        flags = [f"flags={kwargs['flags']}"] if 'flags' in kwargs else []
        framerate = kwargs['framerate'] if 'framerate' in kwargs else '30'
        if not isinstance(metadataobj, MediaMetadata):
            self.e = TypeError("Input object is not type MediaMetadata")
            return
        if metadataobj.e:
            self.e = metadataobj.e
            if self.meta.stderr:
                self.stderr = self.meta.stderr
            return
        if screen_width % hspan:
            self.e = ValueError("hspan is not a multiple of frame width.")
            return
        #video must become hspan by multiply with scale factor. factor found by
        #doing vwidth/hspan. To avoid vertical distortion, you must then use the
        #same scale factor with vheight to obtain vspan.
        scale_factor = metadataobj.width / hspan        
        vspan = metadataobj.height / scale_factor
        if vspan*scale_factor > max_screen_height:
            self.tootall = True
            self.e = ValueError(f"Video too tall. width scaling: {scale_factor}, requested height: {vspan}, maximum height: {max_screen_height}")
            return
        compiled = [
            "ffmpeg",
            "-i",
            metadataobj.filepath,
            "-vf",
            f"scale={hspan}:{vspan}"
        ] + flags + [
            "-r",
            framerate,
            "-y",
            "-an",
            "-plays",
            "0",
            "-f",
            "apng",
            self.outfilepath
        ]
        #NOTE: Do not attempt to output to PIPE. FFMpeg requires a rewindable
        #   output stream for writing to header, but for some reason, FFMpeg
        #   neglects to tell the user this. A friend and I burned 2+ hours
        #   verifying this behavior via hashing and binary file diffs.
        procobj = subprocess.run(compiled, capture_output=True, shell=True)
        stdout = procobj.stdout
        stderr = procobj.stderr
        self.png = stdout
        if procobj.returncode:
            self.e = RuntimeError("ffmpeg failed. Results in stderr.")
            print(stderr.decode('utf-8'))
            self.stderr = stderr
            return
        self.pilimg = Image.open(self.outfilepath)
        self.frames = list()
        self.tkimgs = [None]* self.pilimg.n_frames
        self.tkcacher = self.cachecoro() #Must be placed here because self.tkimgs
        print(f"Finished running")
        return
    
    # It's being done here because we can't use ImageTk until Tk is actually
    # being used which is blocking initial testing because Tk doesn't exist
    # at that point. This will also allow us to lazily evaluate the image.
    def gettkimg(self, framenum):
        if self.tkimgs[framenum]:
            return self.tkimgs[framenum]
        else:
            self.pilimg.seek(framenum)
            i = ImageTk.PhotoImage(self.pilimg)
            self.tkimgs[framenum] = i
            return i

    def cachecoro(self):
        yield
        for i in range(len(self.tkimgs)):
            if self.tkimgs[i]:
                continue
            else:
                self.gettkimg(i)
                yield

    def cacheing(self):
        ''' Call repeatedly to gradually cache ImageTk frames
        '''
        try:
            self.cacheing()
        except:
            pass


