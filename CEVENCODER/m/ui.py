import time
from tkinter import *
from tkinter import ttk
from m.fileio import MediaFile
import asyncio

'''
--------------------
|                  |
|      Video       |
|                  |
|------------------|
| Control | Status |
|------------------|
'''
class VideoFrame(object):
    ''' Note: Playback function should always be running
        With non-async, you must handle the timing yourself.
        With asyn
    '''
    def __init__(self, rootframe):
        colspanwidth = 10  #Total width in columns
        colspansplit = 7   #Width of scrollbar. Status adjusts wrt this & above
        self.mediafile:MediaFile = None
        self.prevscroll = 0
        self.curpos = 0
        self.maxpos = 100
        self.playbackstate = False
        self.imgobjid = None  #From canvas.create_image(). For update.
        self.prevtime = None
        #
        self.frame = ttk.Frame(rootframe, padding="4 4 10 10")
        self.frame.grid(column=0, row=0, sticky=(N,W,E,S))
        #
        self.video = Canvas(self.frame, width=320, height=240)
        self.video.grid(row=1, column=1, columnspan=colspanwidth)
        self.video.create_rectangle(0,0,340-1, 240-1, fill="black", outline="red")
        self.video.columnconfigure(320, weight=0)
        self.video.rowconfigure(240, weight=0)
        #
        self.statusstring = StringVar()
        self.statusstring.set("NONE")
        self.buttonstring = StringVar()
        self.buttonstring.set(">")

        #
        self.scroll = ttk.Scrollbar(self.frame, orient=HORIZONTAL, command=self.xview)
        self.scroll.grid(column=1, row=2, sticky=(W,E), columnspan=colspansplit)
        self.scroll.grid_columnconfigure(10, weight=1)
        #
        self.button = ttk.Button(self.frame, state="disabled", textvariable=self.buttonstring, width=2, command=self.pushplay)
        self.button.grid(column=colspansplit+1, row=2, sticky=(E,))
        self.status = ttk.Label(self.frame, textvariable=self.statusstring, justify="right")
        self.status.grid(column=colspansplit+2, row=2, sticky=(E,), columnspan=colspanwidth-colspansplit)
        self.status.grid_columnconfigure(100, weight=0)

    def xview(self, *args):
        #("command", *params): ("moveto", dir=float()) or ("scroll", dir=int())
        if len(args) < 2:
            return
        if not self.mediafile:
            return
        if args[0] == "scroll":
            self.prevscroll = 0
            if args[1] < 0:
                self.prevframe()
            elif args[1] > 0:
                self.nextframe()
        print(args)

    def loadmediafile(self, mediafile: MediaFile):
        self.playbackstate = False
        self.prevtime = None
        self.mediafile = mediafile
        self.prevscroll = 0
        self.scroll.configure(state='normal')
        self.buttonstring.set('>')

    def pushplay(self):
        if self.playbackstate:
            #Was playing when button was pushed. Show playable and stop video.
            self.buttonstring.set('>')
        else:
            #Was stopped when button was pushed. Show stoppable and play video.
            self.buttonstring.set('#')
            self.curpos = 0
        self.playbackstate = not self.playbackstate

    def prevframe(self):
        ''' doesn't return a value because it ain't natural.
        '''
        if self.mediafile and isinstance(self.mediafile, MediaFile):
            if self.curpos > 0:
                self.curpos -= 1
                self.showframe()
        pass

    def nextframe(self) -> bool:
        ''' Returns True so long as it's advancing. prevframe doesn't do this
            because ain't nobody gonna make a backwards playback.
        '''
        if self.mediafile and isinstance(self.mediafile, MediaFile):
            if self.curpos < self.maxpos:
                self.curpos += 1
                self.showframe()
                return True
        else:
            return False
        pass

    def getframe(self, framenum=None):
        if framenum is None:
            framenum = self.curpos
        if self.mediafile and isinstance(self.mediafile, MediaFile):
            return self.mediafile.gettkimg(framenum)
        else:
            return None

    def showframe(self):
        if self.mediafile and isinstance(self.mediafile, MediaFile):
            self.statusstring.set(f"{self.curpos+1}/{self.maxpos}")
            tkimg = self.mediafile.gettkimg(self.curpos)
            if self.imgobjid is not None:
                self.video.itemconfig(self.imgobjid, image=tkimg)
            else:
                self.imgobjid = self.video.create_image(0, 0, anchor=(N,W), image=tkimg)
        else:
            self.statusstring.set("NONE")
            if self.imgobjid is not None:
                self.video.delete(self.imgobjid)
                self.imgobjid = None

    def keepcacheing(self):
        #Fills in the video class while we wait for the user to do something
        pass

    def playback(self, selftimed=False):
        FRAMERATE = (1.0 / 30.0)
        if self.playbackstate:
            if selftimed:
                curtime = time.perf_counter()
                if self.prevtime is None:
                    self.prevtime = curtime
                    return
                elapsed = curtime - self.prevtime
                if elapsed > FRAMERATE:
                    self.prevtime += FRAMERATE
                    self.nextframe()
            else:
                self.nextframe()

    async def async_playback(self):
        FRAMERATE = (1.0 / 30.0)
        while True:
            await asyncio.sleep(0)
            curtime = time.perf_counter()
            if self.prevtime is None:
                self.prevtime = curtime
            elapsed = curtime - self.prevtime
            if elapsed < FRAMERATE:
                self.keepcacheing()
            else:
                self.prevtime += FRAMERATE
                self.nextframe()

















