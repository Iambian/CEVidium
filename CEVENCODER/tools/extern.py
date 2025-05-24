print "External library file loading"
import sys,os,subprocess,time,struct,Tkinter
from PIL import Image,ImageChops,ImageTk
from math import floor,ceil
from collections import OrderedDict

np,cwd,gbn = (os.path.normpath,os.getcwd(),os.path.basename)
def getFileName(f): return os.path.splitext(gbn(f))[0]
def ep(f): return np(cwd+"/"+f)
def ensuredir(d):
    if not os.path.isdir(d): os.makedirs(d)
    
TDIR,TIMGDIR,OUTDIR,STATUSF = (ep("obj"),ep("obj/png"),ep("bin"),ep("obj/curstate"))
for i in (TDIR,TIMGDIR,OUTDIR): ensuredir(i)

try: Image.Image.tobytes()
except AttributeError: Image.Image.tobytes = Image.Image.tostring
except: pass
ENCNAMES = { "M1" : "M1X3-ZX7",
             "M2" : "M1X2-ZX7", }
ENCFPSEG = { "M1" : (30,15,10,10,10),
             "M2" : (20,10, 5, 5, 5), }

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
# Miscellaneous


# Waits either 1 second to ensure that a file is in a certain state or errors
# if the operation times out. Incrase retry value if trying to access high
# a high latency file system.
#fnp: file name and path, isdel: True= ensure deletion, False= ensure existence
def checkdel(fnp,isdel):
    retry=60
    while os.path.isfile(fnp)==isdel:
        time.sleep(0.015)
        retry-=1
        if retry<1: return False
    return True

def readFile(fn):
    a = []
    with open(fn,"rb") as f:
        b = f.read(1)
        while b!=b'':
            a.append(ord(b))
            b = f.read(1)
    return a
    
def writeFile(fn,a):
    with open(fn,"wb+") as f: f.write(bytearray(a))

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Video window class

class Application(Tkinter.Frame):
    def __init__(self, master=None):
        Tkinter.Frame.__init__(self, master)
        self.master.title("* Ohhhh yesss!")
        self.master.geometry('200x200')
        self.master.minsize(400,300)
        self.pack()
        self.img = ImageTk.PhotoImage(Image.new('RGB',(96,72),0))
        self.canvas = Tkinter.Canvas(self.master,width=320,height=240)
        self.canvas.place(x=10,y=10,width=320,height=240)
        self.canvas.configure(bg='white',width=96,height=72,state=Tkinter.NORMAL)
        self.imgobj = self.canvas.create_image(1,1,image=self.img,anchor=Tkinter.NW,state=Tkinter.NORMAL)
    def updateframe(self,pimg):
        self.img = ImageTk.PhotoImage(pimg)
        self.canvas.itemconfig(self.imgobj,image=self.img)
        self.update_idletasks()
        self.update()
        
# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Export data to TI calculator appvar type
TI_VAR_PROG_TYPE, TI_VAR_PROTPROG_TYPE, TI_VAR_APPVAR_TYPE = (0x05,0x06,0x15)
TI_VAR_FLAG_RAM, TI_VAR_FLAG_ARCHIVED = (0x00,0x80)

#fpath: Path to output file; fname: file's base name (no extension);
#fdata: bytearray-compatible iterable containing just the file's data section
def export8xv(fpath,fname,fdata):
    # Ensure that filedata is a string
    fdata = str(bytearray(fdata))
    # Add size bytes to file data as per (PROT)PROG/APPVAR data structure
    fdata = struct.pack('<H',len(fdata)) + fdata
    # Construct variable header
    vheader  = "\x0D\x00" + struct.pack("<H",len(fdata)) + chr(TI_VAR_APPVAR_TYPE)
    vheader += fname.ljust(8,'\x00')[:8]
    vheader += "\x00" + chr(TI_VAR_FLAG_ARCHIVED) + struct.pack("<H",len(fdata))
    variable = vheader + fdata
    # Construct header, add file data, then add footer
    output  = "**TI83F*\x1A\x0A\x00"
    output += "Cherries! Steaks! Gravy! Rawr!".ljust(42)[:42]
    output += struct.pack('<H',len(variable)) + variable
    output += struct.pack('<H',sum(ord(i) for i in variable)&0xFFFF)
    # Output result to file
    writeFile(np(fpath+"/"+fname+".8xv"),output)

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Frame data packager

# Compressed segment data container
class CmprSeg():
    def __init__(self,segid,data):
        self.segid = segid
        self.data = data
        self.size = len(data)
        
# Main class
class Framebuf():
    def __init__(self,config):
        self.frame_buffer = []
        self.cmpr_arr = []
        self.frames_per_segment = config.getFramesPerSegment()
        self.cur_frame = 0
        self.cur_segment = 0
        self.cmpr_len = 0
        self.raw_len = 0
        self.vid_w, self.vid_h = config.getImgDims()
        self.vid_title = config.titl
        self.vid_author = config.auth
        self.bit_depth = config.getBitDepthCode()
        self.videoname = config.vname
        self.encoding = config.enco
        
    def addframe(self,framedata):
        global TDIR
        if framedata:
            framedata = str(bytearray(framedata))
            self.frame_buffer.extend(framedata)
            self.cur_frame += 1
            if self.cur_frame >= self.frames_per_segment:
                framedata = None
        if not framedata and self.frame_buffer:
            tfo = np(TDIR+"/tin")
            tfc = np(TDIR+"/tout")
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
            self.raw_len += len(self.frame_buffer)
            self.cmpr_len += self.cmpr_arr[-1].size
            sys.stdout.write("\nOutput seg "+str(self.cur_segment)+" size "+str(self.cmpr_arr[-1].size)+"      \n")
            self.frame_buffer = []
            self.cur_frame = 0
            self.cur_segment += 1
    
    def flushtofile(self):
        global ENCNAMES,OUTDIR
        output_filename = self.videoname
        if self.frame_buffer: self.addframe(None)
        outfilename = str(os.path.splitext(os.path.basename(output_filename))[0])
        video_decoder = ENCNAMES[self.encoding[:2]]
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
            export8xv(OUTDIR,wfilename,wfiledata)
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
        mfiledata += struct.pack("B",self.bit_depth)
        export8xv(OUTDIR,outfilename,mfiledata)
        
# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Image filtering and processing

# Converts a 3-tuple (r,g,b) to (h,s,v)
def gethsv(t): return colorsys.rgb_to_hsv(*(i/255.0 for i in t))

def rgb24torgb555(rgbtuple):
    return struct.pack("<H",((rgbtuple[0]>>3)<<10)+((rgbtuple[1]>>3)<<5)+(rgbtuple[2]>>3))

# Processes a raw palette from a PIL Image object to a 256-list of 3-tuples
# containing (r,g,b) values, using only the first 16 entries of the palette
# for the purpose of creating a 4bpp adaptive palette.
# Optionally, sorts using a pre-processed palette from the previous frame.
def paltolist(s,prvpal=None):
    o = []
    for i in range(0,15*3,3):
        o.append((ord(s[i+0])&~0x7,ord(s[i+1])&~0x7,ord(s[i+2])&~0x7))
    o = list(OrderedDict.fromkeys(o[:16]))    #removes dupes, preserves order
    if (0,0,0) not in o: o.insert(0,(0,0,0))  #black must always be in the palette
    o.insert(0,o.pop(o.index((0,0,0))))       #black is always at the front
    # If prvpal is passed in, sort new list by best possible match wrt prvpal
    if prvpal:
        oldvals = list(OrderedDict.fromkeys(prvpal[:16])) #removes duplicates, preserves order
        newvals = o[:]
        n = []
        #match up all possible oldvals with newvals and leave blanks for nonmatch
        for i in oldvals:
            if i in newvals: n.append(newvals.pop(newvals.index(i)))
            else: n.append(None)
        for i in newvals:
            if None in n: n[n.index(None)] = i
            else: n.append(i)
        for i in range(len(n)):
            if n[i] == None: n[i] = (0,0,0)
        if n[0] != (0,0,0): ValueError("Well, shit.")
        o = n
    if len(o)<16:
        o += [(0,0,0)]*(16-len(o))
        o = o * 16
    elif len(o)<64:
        o += [(0,0,0)]*(64-len(o))
        o = o * 4
    elif len(o)<128:
        o += [(0,0,0)]*(128-len(o))
        o = o * 2
    else:
        o += [(0,0,0)]*(256-len(o))
    return o

# Compares two images to detect the subframe in which both images are different.
# The left and right side are adjusted by dividing it by "hdiv" to account for
# different bpp that the images will be converted and packed into.
# Can return one of the following:
# 4-tuple (subFrameX, subFrameY, subFrameW, subFrameH) indicating subframe bounds
# 1-tuple (None,) indicating that the two frames are identical
# NoneType object None indicating that the entire frame was different
def fedge(d,wa,ha,w):
    def scx(d,wa,ha,w):
        for x in wa:
            for y in ha:
                if d[y*w+x]: return x
    def scy(d,wa,ha,w):
        for y in ha:
            for x in wa:
                if d[y*w+x]: return y
    return (scx(d,wa,ha,w),scy(d,wa,ha,w))
def findDiffRect(im1,im2,hdiv):
    w,h = im1.size
    d = ImageChops.difference(im1.convert("RGB"),im2.convert("RGB")).tobytes()
    d = tuple(ord(d[i])+ord(d[i+1])*256+ord(d[i+2])*65536 for i in range(0,len(d),3))
   
    if not any(d): return (None,)
    wa,ha = (range(w),range(h))
    l,t = fedge(d,wa,ha,w)   #find left and top edges
    wa.reverse()
    ha.reverse()
    r,b = fedge(d,wa,ha,w)   #find right and bottom edges
    l,r = (int(floor(l/hdiv)*hdiv),int(ceil((r+1)/hdiv)*hdiv-1))  #adjust bounds
    if (l,r,t,b) == (0,w-1,0,h-1): return None
    return [l,t,r+1-l,b+1-t]
    
    
# Accepts a palette image file 8bpp and an output bpp with which to pack the data.
# Outputs packed data.
def imgToPackedData(img,bpp):
    a = tuple(bytearray(img.tobytes()))
    d = []
    if bpp==1: b,c,m = (8,(0,1,2,3,4,5,6,7),0x01)
    elif bpp==2: b,c,m = (4,(0,2,4,6),0x03)
    elif bpp==4: b,c,m = (2,(0,4),0x0F)
    elif bpp==8: return str(bytearray(a))
    else: ValueError("Invalid bpp ("+str(bpp)+") passed. Only 1,2,4 accepted")
    for i in range(len(a)/b):
        t = 0
        for j,k in enumerate(c): t += (a[i*b+j]&m)<<k
        d.append(t)
    return str(bytearray(d))
    
def findDiff8x8Grid(im1,im2,sw):
    w,h = im1.size
    im2 = im2.convert("RGB")
    arr = []
    for y in range(0,int(ceil(h*1.0/sw))*sw,sw):
        for x in range(0,w-w%sw,sw):
            x2 = x+sw if x+sw <= w else w
            y2 = y+sw if y+sw <= h else h
            r = im2.crop((x,y,x2,y2))
            if r.tobytes() != im1.crop((x,y,x2,y2)).tobytes():
                arr.append(r)
            else:
                arr.append(None)
    return arr
    
#Transform im1 by arr and test to see if it matches im2.
def test8x8Grid(im1,arr,im2,sw):
    w,h = im1.size
    imt = im1.copy().convert("RGB")
    im2 = im2.convert("RGB")
    i = 0
    for y in range(0,int(ceil(h*1.0/sw))*sw,sw):
        for x in range(0,w-w%sw,sw):
            if not arr[i]: continue
            x2 = x+sw if x+sw <= w else w
            y2 = y+sw if y+sw <= h else h
            imt.paste(arr[i],(x,y,x2,y2))
            i += 1
    r = ImageChops.difference(imt,im2)
    return (any(r.tobytes()),r)
    
    
# bits are read in decoder by right-shifting (little endian)
# First byte is preshifted so loop counter can use TST 7
# Destroys arr
def dumpGridData(arr,sw,internal_bpp):
    t,bitfield,datafield,matches = ([],[],[],0)
    for i in range(len(arr)%8): t.append(arr.pop(0)) #Sets in array to be mult of 8, taking excess from arr start
    a = iter(arr)
    a = zip(a,a,a,a,a,a,a,a)  #Unflatten to list of 8-list
    if t != []: a = [t] + a  #Combines list with short lead
    for i in a:
        bits = 0
        for j in i:
            bits = bits >> 1
            if j:
                bits |= 0x80
                t = bytearray(imgToPackedData(j,internal_bpp))
                datafield.extend(t)
                matches += 1
        if len(i)%8 > 0: bits = bits >> abs(len(i)%(-8))
        bitfield.append(bits)
    #bitfield.append(matches)
    s = str(bytearray(bitfield)+bytearray(datafield))
    '''
    print "\n"
    print [len(bitfield),len(datafield),len(s)]
    print ''.join([format(i,"02X") for i in bitfield])
    print ''.join([format(i,"02X") for i in datafield])
    sys.exit()
    '''
    return s

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Conversion to palettized image without dithering, sourced from:
# https://stackoverflow.com/questions/29433243/convert-image-to-specific-palette-using-pil-without-dithering

def quantizetopalette(silf, palette, dither=Image.NONE):
    silf.load()
    palette.load()
    if palette.mode != "P": raise ValueError("Palette image must have palette")
    if silf.mode not in ("RGB","L"):
        raise ValueError("Only RGB or L mode images can be quantized to a palette")
    im = silf.im.convert("P",dither , palette.im)
    try: return silf._new(im)
    except AttributeError: return silf._makeself(im)
    
#Shorter alias
quant2pal = quantizetopalette

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# Project-specific functions and classes

def getImageList():
    global TIMGDIR
    return [i for i in os.listdir(TIMGDIR) if os.path.isfile(np(TIMGDIR+"/"+i)) and i.lower().endswith('.png')]


#Singleton pattern. Probably not needed.
class Config(object):
    def __new__(cls,*args):
        if not hasattr(cls,'instance'): cls.instance = super(Config,cls).__new__(cls)
        return cls.instance
    def __init__(self,statusfile):
        self.status = statusfile
        self.doffmpeg = False
        if not os.path.isfile(self.status):
            with open(self.status,'w') as f: f.write("\nM1\n\n\n")
        with open(self.status,'r') as f: self.arr = [line.strip() for line in f]
        self.vname,self.enco,self.titl,self.auth = self.arr
        
    def update(self,videoname,encodername,title,author):
        def cleanPngBuffer():
            global TIMGDIR
            a = getImageList()
            for i in a:
                try: os.remove(np(TIMGDIR+'/'+i))
                except Exception as e: print e
        pass
        if videoname:
            if self.vname and self.vname != videoname:
                print "Input video name has changed since last build. Cleaning png buffer."
                cleanPngBuffer()
                self.doffmpeg = True
            self.vname = videoname
        if encodername and self.enco != encodername:
            self.enco = encodername
            self.doffmpeg = True
        if title: self.titl = title
        if author: self.auth = author
        if not os.path.isfile(self.vname):
            raise IOError("File "+str(self.vname)+" does not exist.")
        self.getBitDepthCode()  #simply call it to make sure that decoder subcode is valid
        self.getFramesPerSegment() #just call to make sure decoder can support subcode
        
    def save(self):
        writeFile(self.status,"\n".join([self.vname,self.enco,self.titl,self.auth]))
        
    def process(self,force_reprocess=False):
        global TDIR,TIMGDIR
        from ffmpy import FFmpeg
        def chk(self,v): return self.enco.startswith(v)
        if not (self.doffmpeg or force_reprocess): return
        if chk(self,'M1'): hres = 96 ; vres = -2 ; vflags = "neighbor"
        elif chk(self,'M2'): hres =144 ; vres = -2 ; vflags = "neighbor"
        else: raise ValueError("Illegal encoder value was passed. Cannot encode video")
        
        o1,o2,oi = (np(TDIR+'/t1.mp4'), np(TDIR+'/t2.mp4'), np(TIMGDIR+'/i%05d.png'))
        try:
            print "Converting video to target dimensions"
            FFmpeg(
                inputs  = { self.vname: '-y'},
                outputs = { o1: '-c:v libx264 -profile:v baseline -preset medium -vf scale='+str(hres)+':'+str(vres)+':flags='+str(vflags)+' -r 30 -an'},
            ).run()
            print "Outputting individual frames to .png files"
            FFmpeg(
                inputs  = { o1:'-y'},
                outputs = { oi:'-f image2'},
            ).run()
        except Exception as e:
            print e
            print "An error has occurred during transcoding. Script has terminated."
            sys.exit(2)
    
    def cleanOutput(self):
        global OUTDIR
        fl = [f for f in os.listdir(OUTDIR) if os.path.isfile(OUTDIR+"/"+f) and f[:5]==self.vname[:5]]
        for i in fl: os.remove(np(OUTDIR+'/'+i))

    def getImgList(self):
        global TIMGDIR
        return [np(TIMGDIR+'/'+i) for i in sorted(getImageList())]
        
    def getImgDims(self):
        return Image.open(self.getImgList()[0]).size
        
    def getBitDepthCode(self):
        i = None
        if len(self.enco)==4:
            try: 
                i = ["B1","G2","G4","C4","A4","G8","C8","A8","CF"].index(self.enco[2:])
            except Exception as e: ValueError("Invalid codec subcode")
        else:
            i = (-1)
        if i == None: raise RuntimeError("Bit depth failed to initialize. This shouldn't happen.")
        return i
        
    def getFramesPerSegment(self):
        i = self.getBitDepthCode()
        en= self.enco[:2]
        r = None
        if i<0:
            r = ENCFPSEG[en]
        else:
            try: r = ENCFPSEG[en][i]
            except: ValueError("Decoder "+str(en)+" does not support subtype "+str(self.enco[2:]))
        if r == None: RuntimeError("Failure to return frames per segment")
        return r
        
        
        