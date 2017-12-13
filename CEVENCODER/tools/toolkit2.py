print "Loading libraries..."
import sys,os,getopt,Tkinter,struct
from PIL import Image,ImageChops,ImageTk
from itertools import chain
from math import floor
sys.path.append(os.path.normpath(os.getcwd()+"/tools/"))
import extern

# PIL.Image compatibility
try: Image.Image.tobytes()
except AttributeError: Image.Image.tobytes = Image.Image.tostring
except: pass

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
def flatten(a): return list(chain.from_iterable(a))

def usage(err=2):
          #012345678901234567890123456789012345678901234567890123456789012345678901234567
    print "\n"
    print "toolkit.py is a script that takes a video file and returns video"
    print "files that will play on the TI-84 CE graphing calculator."
    print "Usage: python toolkit.py -i <in_video.name>"
    print "Additional options:"
    print "-e ENCODER  = Uses a particular encoder. ENCODER are as follows:"
    print "              M1B1 = 96xN x3 scaled video, 1bpp black and white"
    print "              M1G2 = 96xN x3 scaled video, 2bpp grayscale"
    print "              M1G4 = 96xN x3 scaled video, 4bpp grayscale"
    print "              M1C1 = 96xN x3 scaled video, 4bpp fixed color"
    print "              M1A1 = 96xN x3 scaled video, 4bpp adaptive color"
    print "        -d  = Uses dithering. May increase filesize."
    print "        -f  = Force reconversion of video data"
    print ' -t "title" = Adds title information to the project'
    print '-a "author" = Adds author information to the project'
    return err
    ''' Error codes:
        0 = Requested for help in arguments
        2 = Error occurred in calling getopt.gnu_getopt()
        3 = Illegal argument passed in command line
    ''' 
# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
# It gets real.
try: opts,args = getopt.gnu_getopt(sys.argv,"i:e:dt:a:f")
except: sys.exit(usage(2))

dithering,vencoder,vname,doffmpeg,vtitle,vauthor = (Image.NONE,'','',False,'','')

for opt,arg in opts:
    if opt == '-h': sys.exit(usage(0))
    elif opt == '-i': vname = arg
    elif opt == '-e': vencoder = arg
    elif opt == '-d': dithering = Image.FLOYDSTEINBERG
    elif opt == '-f': doffmpeg = True
    elif opt == '-t': vtitle = arg
    elif opt == '-a': vauthor = arg
    else: sys.exit(usage(3))

settings = extern.Config(extern.STATUSF)
settings.update(vname,vencoder,vtitle,vauthor)
settings.process(doffmpeg)
settings.save()
settings.cleanOutput()
imglist = settings.getImgList()

root = Tkinter.Tk()
app = extern.Application(root)
app.update_idletasks()
app.update()

img_width, img_height = Image.open(imglist[0]).size
if not (img_width|img_height):
    raise ValueError("Bad image data passed. Force image rebuild with -f flag")

fb = extern.Framebuf(settings)
palimg = Image.new("P",(16,16))

# Generate palettes
pal1bpp_bw = flatten([(0,0,0),(255,255,255)]*128)
pal2bpp_gs = flatten([(i,i,i) for i in [0,85,170,255]]*64)
pal4bpp_gs = flatten([(i+(i<<4),i+(i<<4),i+(i<<4)) for i in range(16)]*16)
pal4bpp_col= [0,0,0,85,85,85,170,170,170,255,255,255,
              127,0,0, 0,127,0, 0,0,127, 127,127,0, 127,0,127, 0,127,127,
              255,0,0, 0,255,0, 0,0,255, 255,255,0, 255,0,255, 0,255,255]*16
if len(settings.enco)>3 and settings.enco[2]=='A':
    if settings.enco[3]=='4': adalooparr = tuple(range(1,16))
    elif settings.enco[3]=='8': adalooparr = tuple(range(1,256))
    else: raise ValueError("Illegal bit value for adaptive palette passed")

previmg = None
prevpal = None   # These palettes are lists of 3-tuples
curpal = None    # containing (r,g,b) values.

for imgmainidx,f in enumerate(imglist):
    # Process input image to reduce bit depth to rgb555
    i = Image.open(f).convert("RGB").tobytes()
    i = iter( [ord(b)&~7 for b in i] )
    img = Image.new("RGB",(img_width,img_height))
    img.putdata(zip(i,i,i))
    imgdata = []
    # Process input image according to encoder
    if settings.enco[:2] == "M1":
        if settings.enco[2:] == "B1":
            bppdivider = 8.0
            internal_bpp = 1
            palimg.putpalette(pal1bpp_bw)
        elif settings.enco[2:] == "G2":
            bppdivider = 4.0
            internal_bpp = 2
            palimg.putpalette(pal2bpp_gs)
        elif settings.enco[2:] == "G4":
            bppdivider = 2.0
            internal_bpp = 4
            palimg.putpalette(pal4bpp_gs)
            pass
        elif settings.enco[2:] == "C4":
            bppdivider = 2.0
            internal_bpp = 4
            palimg.putpalette(pal4bpp_col)
            pass
        elif settings.enco[2:] == "A4":
            bppdivider = 2.0
            internal_bpp = 4
            #Adaptive. You'll need to construct the palette yourself then use it
            p = img.convert("P",palette=Image.ADAPTIVE,colors=15).palette.getdata()[1]
            curpal = extern.paltolist(p,None)
            palimg.putpalette(flatten(curpal))
            
        else: ValueError("Invalid subcode passed")
        nimg = extern.quant2pal(img,palimg,dithering)
        app.updateframe(nimg)
        if previmg:
            t = extern.findDiffRect(previmg,img,bppdivider)
            u = extern.findDiff8x8Grid(previmg,img,8)  #search in 8x8 blocks
            if t and len(t)>3: tt= (t[0],t[1],t[0]+t[2],t[1]+t[3])
            if t==(None,):
                sys.stdout.write("Cycle "+str(imgmainidx)+", perfect match\r")
                imgdata = "\x03"
            elif t==None and not any(u):
                sys.stdout.write("Cycle "+str(imgmainidx)+", complete mismatch\r")
                imgdata = "\x01" + extern.imgToPackedData(nimg,internal_bpp)
                previmg = img
            elif len(t) == 4 and (t[2]*t[3])<=(len(u)/8+((len(u)-u.count(None))*8*8)):
                pct = floor((t[2]*t[3]*1.0)/(img_width*img_height)*100)
                sys.stdout.write("Cycle "+str(imgmainidx)+", partial blck mismatch, "+str(pct)+"% difference\r")
                timg = img.crop(tt)
                previmg.paste(timg,tt)
                if previmg.tobytes() != img.tobytes():
                    dbg1,dgb2,s = (previmg.convert("RGB").tobytes(),img.convert("RGB").tobytes(),"")
                    print "\nBlatant error dump\n"+str(len(dbg1))+"\n"+str(tt)+"\nDiscrepency list as follows:\n"+''.join(["["+format(k%img_width,"02")+","+format(k/img_width,"02")+"]:["+format(ord(i),"02X")+","+format(ord(j),"02X")+"] " for i,j,k in [(i,j,k) for i,j,k in zip(dbg1,dbg2,range(len(dbg1))) if i!=j]])
                    ImageChops.difference(previmg.convert("RGB"),img.convert("RGB")).show()
                    raise ValueError("Block image recomposition mismatch. This shouldn't happen.")
                h  = "\x02"
                h += struct.pack("B",t[0])
                h += struct.pack("B",t[1])
                h += struct.pack("B",t[2])
                h += struct.pack("B",t[3])
                imgdata = h + extern.imgToPackedData(extern.quantizetopalette(timg,palimg,dithering),internal_bpp)
                previmg = img
            elif len(t) == 4 and (t[2]*t[3])>(len(u)/8+((len(u)-u.count(None))*8*8)):
                pct = (len(u)-u.count(None)*1.0)/(len(u)*1.0)
                sys.stdout.write("Cycle "+str(imgmainidx)+", partial grid mismatch, "+str(pct)+"% difference\r")
                res = extern.test8x8Grid(previmg,u,img,8)
                if not res[0]:
                    raise ValueError("Grid image recomposition mismatch. This shouldn't happen.")
                for i in range(len(u)):
                    if u[i]: u[i] = extern.quantizetopalette(u[i],palimg,dithering)
                imgdata = ''.join(['\x04',dumpGridData(u,8,internal_bpp)])
            else:
                print t
                print u
                ValueError("Invalid value returned from matcher")
        else:
            imgdata = "\x01" + extern.imgToPackedData(nimg,internal_bpp)
            previmg = nimg

    else:
        raise ValueError("Illegal encoder value was passed.")
        
    # Palette processing for adaptive palette codecs
    if len(settings.enco)>3 and settings.enco[2]=='A':
        palarr = []
        palidx = 0
        palbin = ""
        if prevpal:
            for i in adalooparr:
                palidx >>= 1
                if curpal[i] and curpal[i]!=prevpal[i]:
                    palidx |= 0x8000
                    if settings.enco[3]=='4':
                        palarr.append(curpal[i])
                    else:
                        palarr.append((i,curpal[i]))
            palidx >>= 1  #make up for last entry unused
        else:
            if settings.enco[3]=='4':
                palidx = 0x7FFF
                palarr = curpal[1:16]
            else:
                palarr = [0] + curpal[1:256]
        if settings.enco[3]=='4':
            palbin = struct.pack("<H",palidx)
            for i in palarr: palbin += extern.rgb24torgb555(i)
            #print "\nPalette object length"+str(len(palarr))+" with bytecode "+format(palidx,"04X")+"\n"
        else:
            for i in palarr:
                palbin += struct.pack("B",i[0]) + extern.rgb24torgb555(i[1])
        imgdata += palbin
        prevpal = curpal
    else:
        imgdata += "\x00\x00"
    # All processing completed. Buffer frame data for write
    fb.addframe(imgdata)
fb.addframe("\x00\x00\x00") #End of Video packet
fb.flushtofile()

