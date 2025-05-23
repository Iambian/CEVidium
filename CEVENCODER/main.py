from m.fileio import readfile, writefile, export8xv, MediaMetadata, MediaFile
from m.ui import *

testfile = 'caches/fdumpster.mp4'
testfile2 = 'caches/tallcat.gif'
testfile3 = 'caches/nestest.nes'
testfile4 = 'caches/GtKSwIy.jpeg'

mf = MediaFile(testfile)
print(mf)
if mf.e:
    print(mf.e)
print("Finished")

from tkinter import *
from tkinter import ttk


class VideoCanvas(Canvas):
    def xview(self, *args):
        print([args, super().xview(*args)])


root = Tk()
root.title("CEVidium Encoder Interface")

rootframe = ttk.Frame(root, padding="4 4 10 10")
rootframe.grid(column=0, row=0, sticky=(N, W, E, S))
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

videoframe = VideoFrame(rootframe)



root.mainloop()





