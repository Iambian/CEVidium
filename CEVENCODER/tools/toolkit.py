print "Loading libraries"
from PIL import Image,ImageTk,ImagePalette
from ffmpy import FFmpeg
from itertools import chain
import Tkinter as tk
import sys,os,ctypes,subprocess,getopt,shutil,struct,time,colorsys

np  = os.path.normpath
cwd = os.getcwd()
    
TEMP_DIR     = np(cwd+"/obj/")
TEMP_PNG_DIR = np(cwd+"/obj/png")
OUTPUT_DIR   = np(cwd+"/bin")
STATUS_FILE  = np(TEMP_DIR+'/curstate')

def GETIMGPATH(fname): return np(TEMP_PNG_DIR+"/"+fname)
def GETIMGNAMES():
    global TEMP_PNG_DIR
    return sorted([f for f in os.listdir(TEMP_PNG_DIR) if os.path.isfile(os.path.join(TEMP_PNG_DIR,f))])
def ensure_dir(d):
    if not os.path.isdir(d): os.makedirs(d)
def checkdel(fnp,isdel):  #True to check if deleted, False to check if exist (yet)
    retries = 60
    while os.path.isfile(fnp) == isdel:
        time.sleep(0.015)
        retries -= 1
        if retries < 1:
            return False
    return True
    
ensure_dir(TEMP_DIR)
ensure_dir(TEMP_PNG_DIR)
ensure_dir(OUTPUT_DIR)
ensure_dir(TEMP_DIR+'/tin')
ensure_dir(TEMP_DIR+'/tout')

ENCODER_NAMES = {   1: "1B3X-ZX7",
                    2: "2B3X-ZX7",
                    3: "2B1X-ZX7",
                    4: "1B1X-ZX7",
                    5: "4C3X-ZX7",
                    6: "4A3X-ZX7",
}
FPSEG_BY_ENCODER = {    1:30,
                        2:15,
                        3:6,
                        4:10,
                        5:15,
                        6:10,
}



# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
# Miscellaneous
def readFile(fn):
    a = []
    with open(fn,"rb") as f:
        b = f.read(1)
        while b!=b'':
            a.append(ord(b))
            b = f.read(1)
    return a
def writeFile(fn,a):
    with open(fn,"wb+") as f:
        f.write(bytearray(a))

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Export data to appvar
TI_VAR_PROG_TYPE = 0x05
TI_VAR_PROTPROG_TYPE = 0x06
TI_VAR_APPVAR_TYPE = 0x15
TI_VAR_FLAG_RAM = 0x00
TI_VAR_FLAG_ARCHIVED = 0x80

def export8xv(filepath,filename,filedata):
    # Ensure that filedata is a string
    if isinstance(filedata,list): filedata = str(bytearray(filedata))
    # Add size bytes to file data as per (PROT)PROG/APPVAR data structure
    dsl = len(filedata)&0xFF
    dsh = (len(filedata)>>8)&0xFF
    filedata = str(bytearray([dsl,dsh]))+filedata
    # Construct variable header
    vsl = len(filedata)&0xFF
    vsh = (len(filedata)>>8)&0xFF
    vh  = str(bytearray([0x0D,0x00,vsl,vsh,TI_VAR_APPVAR_TYPE]))
    vh += filename.ljust(8,'\x00')[:8]
    vh += str(bytearray([0x00,TI_VAR_FLAG_ARCHIVED,vsl,vsh]))
    # Pull together variable metadata for TI8X file header
    varentry = vh + filedata
    varsizel = len(varentry)&0xFF
    varsizeh = (len(varentry)>>8)&0xFF
    varchksum = sum([ord(i) for i in varentry])
    vchkl = varchksum&0xFF
    vchkh = (varchksum>>8)&0xFF
    # Construct TI8X file header
    h  = "**TI83F*"
    h += str(bytearray([0x1A,0x0A,0x00]))
    h += "Rawr. Gravy. Steaks. Cherries!".ljust(42)[:42]  #Always makes comments exactly 42 chars wide.
    h += str(bytearray([varsizel,varsizeh]))
    h += varentry
    h += str(bytearray([vchkl,vchkh]))
    # Write data out to file
    writeFile(np(filepath+"/"+filename+".8xv"),h)
    return

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Video window class

class Application(tk.Frame):
    def __init__(self, master=None):
        tk.Frame.__init__(self, master)
        self.master.title("* Ohhhh yesss!")
        self.master.geometry('200x200')
        self.master.minsize(400,300)
        self.pack()
        self.img = ImageTk.PhotoImage(Image.new('RGB',(96,72),0))
        self.canvas = tk.Canvas(self.master,width=320,height=240)
        self.canvas.place(x=10,y=10,width=320,height=240)
        self.canvas.configure(bg='white',width=96,height=72,state=tk.NORMAL)
        self.imgobj = self.canvas.create_image(1,1,image=self.img,anchor=tk.NW,state=tk.NORMAL)
    def updateframe(self,pimg):
        self.img = ImageTk.PhotoImage(pimg)
        self.canvas.itemconfig(self.imgobj,image=self.img)
        self.update_idletasks()
        self.update()
        
        
# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Frame data packager
class CmprSeg():
    def __init__(self,segid,data):
        self.segid = segid
        self.data = data
        self.size = len(data)
        
class Framebuf():
    def __init__(self,video_width,video_height,video_title='',video_author=''):
        self.frame_buffer = []
        self.cmpr_arr = []
        self.frames_per_segment = 30
        self.cur_frame = 0
        self.cur_segment = 0
        self.cmpr_len = 0
        self.raw_len = 0
        self.vid_w = video_width
        self.vid_h = video_height
        self.vid_title = video_title
        self.vid_author = video_author
        
    def addframe(self,framedata):
        global TEMP_DIR
        if framedata:
            framedata = str(bytearray(framedata))
            self.frame_buffer.extend(framedata)
            self.cur_frame += 1
            if self.cur_frame >= self.frames_per_segment:
                framedata = None
        if not framedata and self.frame_buffer:
            tfo = np(TEMP_DIR+"/tin/"+str(self.cur_segment))
            tfc = np(TEMP_DIR+"/tout/"+str(self.cur_segment))
            if os.path.exists(tfo): os.remove(tfo)
            if os.path.exists(tfc): os.remove(tfc)
            if not checkdel(tfo,True):
                raise IOError("Input file "+tfo+" could not be deleted.")
            if not checkdel(tfc,True):
                raise IOError("Output file "+tfo+" could not be deleted.")
            writeFile(tfo,self.frame_buffer)
            if not checkdel(tfo,False):
                raise IOError("Input file "+tfo+" could not be created.")
            FNULL = open("NUL","w")
            subprocess.call([np(cwd+"/tools/zx7.exe"),tfo,tfc],stdout=FNULL)
            if not checkdel(tfc,False):
                raise IOError("Output file "+tfo+" could not be created.")
            self.cmpr_arr.append(CmprSeg(self.cur_segment,readFile(tfc)))
            if os.path.exists(tfo): os.remove(tfo)
            if os.path.exists(tfc): os.remove(tfc)
            self.raw_len += len(self.frame_buffer)
            self.cmpr_len += self.cmpr_arr[-1].size
            sys.stdout.write("Output seg "+str(self.cur_segment)+" size "+str(self.cmpr_arr[-1].size)+"      \r")
            self.frame_buffer = []
            self.cur_frame = 0
            self.cur_segment += 1
            
    def framecap(self,framedata):
        if self.cur_frame:
            for i in range(self.frames_per_segment-self.cur_frame):
                self.addframe(framedata)
    
    def flushtofile(self,output_filename,output_encoding):
        global ENCODER_NAMES,OUTPUT_DIR
        outfilename = str(os.path.splitext(os.path.basename(output_filename))[0])
        video_decoder = ENCODER_NAMES[int(output_encoding)]
        self.cmpr_arr = sorted(self.cmpr_arr,key=lambda i:i.size,reverse=True)
        slack = -1
        curfile = 0
        curseg = 0
        tslack = 0
        maxslack = 65000
        total_len = 0
        while len(self.cmpr_arr)>0:
            slack = maxslack
            segs_in_file = 0
            i = 0
            wfiledata = ""
            while i<len(self.cmpr_arr):
                if self.cmpr_arr[i].size > slack:
                    i += 1
                else:
                    a  = self.cmpr_arr.pop(i)
                    s  = struct.pack('<H',a.segid) + struct.pack('<H',a.size)
                    s += str(bytearray(a.data))
                    wfiledata += s
                    curseg += 1
                    segs_in_file += 1
                    slack -= a.size+4
                    print "Segment "+str(a.segid)+ " sized "+str(a.size)+" written."
            wfilename = outfilename[:5]+str(curfile).zfill(3)
            wtempdata = "8CEVDat" + outfilename.ljust(9,'\x00')[:9] #header, assocaited file
            wtempdata+= str(bytearray([segs_in_file&0xFF]))
            wfiledata = wtempdata + wfiledata
            export8xv(OUTPUT_DIR,wfilename,wfiledata)
            print "File output: "+str(wfilename)
            curfile += 1
            tslack += slack
            total_len += len(wfiledata)
    
        mfiledata  = "8CEVDaH" + video_decoder.ljust(9,'\x00')[:9]  #header and decoder name
        mfiledata += self.vid_title + "\x00"                           #title string
        mfiledata += self.vid_author + "\x00"                          #author string
        mfiledata += struct.pack("<H",curseg)
        mfiledata += struct.pack("<H",self.vid_w)
        mfiledata += struct.pack("<H",self.vid_h)
        mfiledata += struct.pack("B",self.frames_per_segment)
        export8xv(OUTPUT_DIR,outfilename,mfiledata)

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Image filtering

def gethsv(t):
    r,g,b = (i/255.0 for i in t)
    return colorsys.rgb_to_hsv(r,g,b)

def rgbpaltolist(s):
    o = []
    for i in range(0,15*3,3):
        r = ord(s[i+0])&~0x7
        g = ord(s[i+1])&~0x7
        b = ord(s[i+2])&~0x7
        o.append((r,g,b))
    o = list(set(o))      #remove duplicates
    o.sort()
#    if (0,0,0) not in o: o.insert(0,(0,0,0))  #black must always be in the palette
#    o.insert(0,o.pop(o.index((0,0,0))))       #black is always at the front
    if len(o)<256:
        o += [(0,0,0)]*(256-len(o))
#    if o[0] != (0,0,0):
#        raise ValueError("First val of out array is not (0,0,0) despite best efforts")
    return o



# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Conversion to palettized image without dithering, sourced from:
# https://stackoverflow.com/questions/29433243/convert-image-to-specific-palette-using-pil-without-dithering

def quantizetopalette(silf, palette, dither=False):
    silf.load()
    palette.load()
    if palette.mode != "P":
        raise ValueError("bad mode for palette image")
    if silf.mode != "RGB" and silf.mode != "L":
        raise ValueError(
            "only RGB or L mode images can be quantized to a palette"
            )
    im = silf.im.convert("P", 1 if dither else 0, palette.im)
    try:
        return silf._new(im)
    except AttributeError:
        return silf._makeself(im)
        
# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
def usage():
           #012345678901234567890123456789012345678901234567890123456789012345678901234567
    print "\ntoolkit.py is a video converter/packager utility for the TI-84 CE platform."
    print "Usage: python toolkit.py -i <in_video.name>"
    print "Additional options:"
    print "-e ENCODER  = Uses a particular encoder. ENCODER are as follows:"
    print "              1 = 1bpp b/w, 3x scaling from 96 by X"
    print "              2 = 2bpp b/dg/lg/w, 3x scaling from 96 by X"
    print "              3 = (decoder not supported)"
    print "              4 = 1bpp b/w, no scaling from 176 by X"
    print "              5 = 4bpp 16 color, 3x scaling from 96 by X"
    print "              6 = 4bpp adaptive palette, 3x scaling from 96 by X"
    print "        -d  = Uses dithering. May increase filesize."
    print "        -f  = Force reconversion of video data"
    print ' -t "title" = Adds title information to the project'
    print '-a "author" = Adds author information to the project'
    return 2
# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
# It gets real.

print "Setting variables"

try: opts,args = getopt.gnu_getopt(sys.argv,"i:e:dt:a:f")
except:
    print "Err0"
    sys.exit(usage())

dithering = Image.NONE
vid_encoder = ''
invidname = ''
doffmpeg = False
vid_title = ''
vid_author = ''


for opt,arg in opts:
    if opt == '-h':
        print "Err1"
        sys.exit(usage())
    elif opt == '-i':
        invidname = arg
    elif opt == '-e':
        vid_encoder = arg
    elif opt == '-d':
        dithering = Image.FLOYDSTEINBERG
    elif opt == '-f':
        doffmpeg = True
    elif opt == '-t':
        vid_title = arg
    elif opt == '-a':
        vid_author = arg
    
#status file line numbers: 0=src path/fn; 1=encoding; 2=titlestr; 3=authorstr
status_file_array = []
if not os.path.isfile(STATUS_FILE):
    with open(STATUS_FILE,'w') as f:
        f.write("\n1\n\n\n")
with open(STATUS_FILE,"r") as f:
    for line in f: status_file_array.append(line.strip())
sf_fileget = status_file_array[0]
sf_encoder = status_file_array[1]
sf_title   = status_file_array[2]
sf_author  = status_file_array[3]
# Override sf variables if found on cmd line, else set vid stuff to sf.
if invidname:
    if sf_fileget and sf_fileget != invidname:
        print "Input video name has changed since last build. Cleaning png buffer."
        for f in os.listdir(TEMP_PNG_DIR):
            fn = os.path.join(TEMP_PNG_DIR,f)
            try:
                if os.path.isfile(fn):
                    os.remove(fn)
            except Exception as e:
                print e
    sf_fileget = invidname
else: invidname = sf_fileget
if vid_title: sf_title = vid_title
else: vid_title = sf_title
if vid_author: sf_author = vid_title
else: vid_author = sf_author
if vid_encoder: 
    if sf_encoder != vid_encoder:
        doffmpeg = True
        sf_encoder = vid_encoder
else: vid_encoder = sf_encoder
if not os.path.isfile(invidname):
    if not os.path.isfile(sf_fileget):
        print "Error: File "+str(invidname)+" does not exist."
        sys.exit(2)
    else:
        invidname = sf_fileget
else:
    sf_fileget = invidname
flist = GETIMGNAMES()
if not flist: doffmpeg = True
#-----------------------------------------------------------------------------------
#VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
if doffmpeg:
    if vid_encoder == '1':
        hres = 96
        vres = -2
    elif vid_encoder == '2':
        hres = 96
        vres = -2
    elif vid_encoder == '3':
        hres = 176
        vres = -2
    elif vid_encoder == '4':
        hres = 176
        vres = -2
    elif vid_encoder == '5':
        hres = 96
        vres = -2
    elif vid_encoder == '6':
        hres = 96
        vres = -2
    else:
        print "Illegal encoder value was used. Cannot encode video."
        sys.exit(2)
    
    of1   = np(TEMP_DIR+"/"+"t1.mp4")
    of2   = np(TEMP_DIR+"/"+"t2.mp4")
    ofimg = np(TEMP_PNG_DIR+'/i%05d.png')
    try:
        print "Converting video to target dimensions"
        FFmpeg(
            inputs  = { invidname: '-y'},
            outputs = { of1: '-vf scale='+str(hres)+':'+str(vres)+':flags=neighbor'},
        ).run()
        print "Outputting individual frames to .png files"
        FFmpeg(
            inputs  = {of1:'-y'},
            outputs = {ofimg:'-f image2'},
        ).run()
    except Exception as e:
        print e
        print "Terminating script."
        sys.exit(2)
#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#-----------------------------------------------------------------------------------
print "Saving config data"
status_file_array[0] = sf_fileget
status_file_array[1] = sf_encoder
status_file_array[2] = sf_title  
status_file_array[3] = sf_author 
with open(STATUS_FILE,"w") as f:
    for i in status_file_array: f.write(i+"\n")

print "Collecting image data..."

img_width,img_height = (0,0)
fl = [f for f in os.listdir(OUTPUT_DIR) if os.path.isfile(np(OUTPUT_DIR+'/'+f)) and f[:5]==invidname[:5]]
for i in fl: os.remove(np(OUTPUT_DIR+'/'+i))

flist = sorted([f for f in os.listdir(TEMP_PNG_DIR) if os.path.isfile(os.path.join(TEMP_PNG_DIR,f))])
for f in flist:
    if f.lower().endswith('.png'):
        timg = Image.open(GETIMGPATH(f))
        img_width,img_height = timg.size
        break
if not (img_width|img_height):
    print "Illegal image data passed. You must rebuild the video"
    print "Hint: Add the -f flag to force a rebuild"
    sys.exit()

fb = Framebuf(img_width,img_height,vid_title,vid_author)
fb.frames_per_segment = FPSEG_BY_ENCODER[int(vid_encoder)]
palimg = Image.new("P",(16,16))
newimgobj = Image.new("P",(img_width,img_height))
#root = tk.Tk()
#app = Application(root)
#app.update_idletasks()
#app.update()


for f in flist:
    print f
    img = Image.open(GETIMGPATH(f))
    imgdata = []
    if vid_encoder == '1':
        imgdata = img.convert('1',None,dithering).tostring() # Changed from .tobytes() to be compatible with the latest PIL version
    elif vid_encoder == '2':
        palimg.putpalette([0,0,0,102,102,102,176,176,176,255,255,255]*64)
        timg = quantizetopalette(img,palimg,dithering)
        timgdat = timg.tostring()
        #app.updateframe(timg)
        for i in range(len(timgdat)/4):
            t = 0
            for j in range(4):
                t += (ord(timgdat[(i*4)+j])&3)<<(2*j)
            imgdata.append(t)
    elif vid_encoder == '3':
        palimg.putpalette([0,0,0,102,102,102,176,176,176,255,255,255]*64)
        timg = quantizetopalette(img,palimg,dithering)
        timgdat = timg.tostring()
        #app.updateframe(timg)
        for i in range(len(timgdat)/4):
            t = 0
            for j in range(4):
                t += (ord(timgdat[(i*4)+j])&3)<<(2*j)
            imgdata.append(t)
    elif vid_encoder == '4':
        imgdata = img.convert('1',None,dithering).tostring() # Changed from .tobytes() to be compatible with the latest PIL version
    elif vid_encoder == '5':
        palette = [0,0,0, 128,0,0, 0,128,0, 0,0,128,
                   128,128,0, 0,128,128, 128,0,128, 128,128,128,
                   128,128,128, 255,0,0, 0,255,0, 0,0,255,
                   255,255,0, 0,255,255, 255,0,255, 255,255,255]
        palimg.putpalette(palette*16)
        timg = quantizetopalette(img,palimg,dithering)
        timgdat = timg.tostring()
        #app.updateframe(timg)
        for i in range(len(timgdat)/2):
            t = 0
            for j in range(2):
                t += (ord(timgdat[(i*2)+j])&15)<<(4*j)
            imgdata.append(t)
    elif vid_encoder == '6':
        timg = img.convert("P",palette=Image.ADAPTIVE,colors=15)
        p = rgbpaltolist(timg.palette.getdata()[1])
        palimg.putpalette(list(chain.from_iterable(p)))
        timg = quantizetopalette(img,palimg,dithering)
        palettebin = ''
        for i in range(0,15):
            r,g,b = ((p[i][0]>>3)&0x1F,(p[i][1]>>3)&0x1F,(p[i][2]>>3)&0x1F)
            t = (r<<10)+(g<<5)+b
            palettebin += struct.pack("<H",t)
        timgdat = str(bytearray(timg.tostring()))
        app.updateframe(timg)
        #app.updateframe(timg)
        for i in range(len(timgdat)/2):
            t = 0
            for j in range(2):
                t += (ord(timgdat[(i*2)+j])&15)<<(4*j)
            imgdata.append(t)
        imgdata = bytearray(palettebin) + bytearray(imgdata)
    else:
        print "Illegal encoder value passed ("+vid_encoder+"). Cannot convert video."
        sys.exit(2)
    fb.addframe(imgdata)
    
fb.framecap(imgdata)  #makes sure that video capped with same last image
fb.flushtofile(invidname,vid_encoder)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
