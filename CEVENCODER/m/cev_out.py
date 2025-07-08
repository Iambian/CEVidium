import sys,os,subprocess,time,struct,tkinter,re
from PIL import Image,ImageChops,ImageTk
from math import floor,ceil
from collections import OrderedDict
from . import cev_proc

np,cwd,gbn = (os.path.normpath,os.getcwd(),os.path.basename)
def getFileName(f): return os.path.splitext(gbn(f))[0]
def ep(f): return np(cwd+"/"+f)
def ensuredir(d):
    if not os.path.isdir(d): os.makedirs(d)

def tobytes(indata:list|tuple|str|bytes|bytearray):
    """ Attempts to recursively turn a sequence into a bytes object.
    """
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

# Miscellaneous


TI_VAR_PROG_TYPE, TI_VAR_PROTPROG_TYPE, TI_VAR_APPVAR_TYPE = (0x05,0x06,0x15)
TI_VAR_FLAG_RAM, TI_VAR_FLAG_ARCHIVED = (0x00,0x80)
def export8xv(basepath: str, basename: str, filedata: bytes) -> None:
    """
    Exports the given file data as a TI-8X AppVar (.8xv) file.
    """
    # Ensure that filedata is a bytearray
    if isinstance(filedata, list):
        filedata = bytearray(filedata)

    # Ensure that basename contains only alphanumeric characters.
    basename = ''.join([c for c in basename if c.isalnum()])

    # Add size bytes to file data as per (PROT)PROG/APPVAR data structure
    data_length_low_byte = len(filedata) & 0xFF
    data_length_high_byte = (len(filedata) >> 8) & 0xFF
    filedata = bytearray([data_length_low_byte, data_length_high_byte]) + filedata

    # Construct variable header
    variable_length_low_byte = len(filedata) & 0xFF
    variable_length_high_byte = (len(filedata) >> 8) & 0xFF
    variable_header = bytearray([0x0D, 0x00, variable_length_low_byte, variable_length_high_byte, TI_VAR_APPVAR_TYPE])
    variable_header += tobytes(basename.ljust(8, '\x00')[:8])
    variable_header += bytearray([0x00, TI_VAR_FLAG_ARCHIVED, variable_length_low_byte, variable_length_high_byte])

    # Pull together variable metadata for TI8X file header
    variable_entry = variable_header + filedata
    variable_entry_length_low_byte = len(variable_entry) & 0xFF
    variable_entry_length_high_byte = (len(variable_entry) >> 8) & 0xFF
    variable_checksum = sum([i for i in variable_entry])
    checksum_low_byte = variable_checksum & 0xFF
    checksum_high_byte = (variable_checksum >> 8) & 0xFF

    # Construct TI8X file header
    header = tobytes("**TI83F*")
    header += bytearray([0x1A, 0x0A, 0x00])
    header += tobytes("Rawr. Gravy. Steaks. Cherries!".ljust(42)[:42])  # Always makes comments exactly 42 chars wide.
    header += bytearray([variable_entry_length_low_byte, variable_entry_length_high_byte])
    header += variable_entry
    header += bytearray([checksum_low_byte, checksum_high_byte])

    # Write data out to file
    was_written = False
    with open(f"{os.path.join(basepath,basename)}.8xv", "wb") as f:
        print(f.name)
        f.write(header)
        was_written = True
    return was_written

def export_cev_files(cev_list: 'cev_proc.Cevideolist', folderpath: str, filename: str, video_title: str, video_author: str) -> None:
    """
    Exports the Cevideolist data to CEVidium metadata and data files.

    Args:
        cev_list: An initialized Cevideolist object.
        folderpath: The path to the folder where the metadata and data files go.
        filename: The base filename for the metadata and data files.
        video_title: The video title string.
        video_author: The author string.
    """
    if not cev_list.is_finished:
        raise ValueError("Cevideolist is not finished initializing.")

    if not cev_list.is_compressed:
        encoded_segments = cev_list.collect_encoded_frames()
        def dummy_callback(current, total):
            pass
        compressed_data = cev_list.compress_encoded_segments(encoded_segments, dummy_callback)

    field_data_list = cev_list.build_field_data(compressed_data)
    concatenated_bytearrays, entry_counts = cev_list.concatenate_field_data(field_data_list)
    cev_list.field_data = concatenated_bytearrays
    # Create metadata file
    metadata_filename = ''.join([c for c in filename if c.isalpha()])[:8]
    decoder_scale = cev_list.mode.scale
    if decoder_scale == 2:
        decoder_name = "M1X2-ZX7"
    elif decoder_scale == 3:
        decoder_name = "M1X3-ZX7"
    else:
        raise ValueError("Unrecognized scaling factor. No decoder available.")
    bit_depth_code = int(cev_list.mode.filterui) - 1
    frame_rate = 30

    if not cev_list.frame_list:
        raise ValueError("Frame list must be populated with frames.")

    width, height = cev_list.frame_list[0].processed_frame.size
    frames_per_field = cev_list.mode.frames_per_segment

    metadata_header = bytearray(b"8CEVDaH")
    metadata_header += tobytes(decoder_name.ljust(9, '\x00'))
    metadata_header += tobytes(video_title + '\x00')
    metadata_header += tobytes(video_author + '\x00')
    metadata_header += struct.pack("<H", sum(entry_counts))  # Total number of fields
    metadata_header += struct.pack("<H", width)  # Video width
    metadata_header += struct.pack("<H", height)  # Video height
    metadata_header += struct.pack("<B", frames_per_field)  # Number of video frames per video data FIELD (assuming 1 for now)
    metadata_header += struct.pack("<B", bit_depth_code)  # Bit depth code
    metadata_header += struct.pack("<B", frame_rate)  # Video frame rate in FPS

    export8xv(folderpath, metadata_filename, bytes(metadata_header))

    # Create data files
    for i, field_data in enumerate(cev_list.field_data):
        data_filename = f"{metadata_filename[:6]}{i:02x}"[:8]
        if data_filename == metadata_filename:
            raise ValueError(f"Filename {filename} resulted in data/metadata name collision ({metadata_filename}).")
        data_header = bytearray(b"8CEVDat")
        data_header += tobytes(metadata_filename.ljust(9, '\x00'))
        data_header += struct.pack("<B", entry_counts[i])  # Number of segments/FIELDs in this file
        #data_header += struct.pack("<H", i)  # ID of this field
        #data_header += struct.pack("<H", len(field_data))  # Size of the field's data segment
        data_file_data = data_header + field_data   #Aside from the header, the file's been preconstructed. No field headers here.

        export8xv(folderpath, data_filename, bytes(data_file_data))
