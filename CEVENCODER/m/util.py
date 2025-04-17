import os, sys, time


#Note: This'll also flatten any embedded lists, tuples, and strings.
def tobytes(indata:list|tuple) -> bytes:
    outlist = list()
    for dat in indata:
        if isinstance(dat,str):
            for s in dat:
                outlist.append(ord(s))
        elif isinstance(dat,(bytes, bytearray)):
            for b in dat:
                outlist.append(b)
        elif isinstance(dat, (list, tuple)):
            subdata = tobytes(dat)
            for b in subdata:
                outlist.append(b)
        else:
            outlist.append(dat)
    return bytes(outlist)

#Note: Increase sleep_iterval or retry if you're getting IOError()
def checkdel(fnp:str, isdel:bool) -> bool:
    retry = 60
    sleep_interval = 0.015
    while os.path.isfile(fnp) == isdel:
        time.sleep(sleep_interval)
        retry -= 1
        if retry < 1:
            return False
    return True