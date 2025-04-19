import os
from m.util import tobytes, checkdel


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

