CEVidium - Video Conversion and On-Calculator Playback Project
==============================================================
Warning:
* **This only works on the TI-84+ CE.**
* This will not work on the TI-84+ CSE.
* This will not work on any TI-84+ (SE)

Motivation
----------
I wanted to see Bad Apple play on my TI-84 CE.
Then I wanted to see cool stuff. Nothing much to it.

Converting the Video
--------------------
1. Copy your .MP4 or other video file to the CEVENCODER folder.
2. Rename that video to a name that contains 8 or less characters.
3. Open a command prompt in the CEVENCODER folder.
4. Type: `BUILD.BAT -h`
5. Read the options, then retype the above line without the '-h' flag and with
   the flags that you want. For example, if your input video is MYVID.mp4 and you
   wanted to use encoding 2 with dithering:
   `BUILD.BAT -i MYVID.mp4 -e 2 -d`
6. If everything worked, copy the contents of CEVENCODER/bin to your calculator.

Building and Sending the Video Player
-------------------------------------
1. If you have not installed the CE programming toolchain, download and install
   from: https://github.com/CE-Programming/toolchain/releases
2. Open a command prompt in the CEVPLAY folder and type 'make' to build the
   video player.
3. If everything worked, copy CEVPLAY/bin/CEVIDIUM.8xp to your calculator.

Building and Sending the Decoders
---------------------------------
1. Double-click CEVDECODER/build.bat to run it.
2. If everything worked, copy the contents of CEVDECODER/bin to your calculator.

Copyrights and Licenses
-----------------------
* The ZX7 (de)compression code and executable was done by Einar Saukas.
  See CEVENCODER/tools/ZX7_LICENSE for details.
* SPASM-ng (e)z80 assembler was done by a bunch of people.
  See CEVDECODER/tools/SPASM_LICENSE for details.
* The rest of Project CEVidium was done by me.
  See LICENSE for details.
 
Version History
---------------
0.00 - Initial commit











