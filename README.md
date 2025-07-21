CEVidium - Video Conversion and On-Calculator Playback Project
==============================================================
Warning:
* **This only works on the TI-84+ CE.**
* This will not work on the TI-84+ CSE.
* This will not work on any TI-84+ (SE)

NOTE
----
July 21, 2025: Ok. Encoder parity has been reached, as best as I can tell. At
least for the capabilities called for in toolkit2.py. Thing is, the adaptive
palette selection algorithm just isn't meant for video objects. Never was.
That's the focus of the work going forward. Also, UI now wants more libraries,
even though they don't use them yet. Reread the dependencies section if needed.

Motivation
----------
I wanted to see Bad Apple play on my TI-84 CE.
Then I wanted to see more cool stuff.

The Video Converter
-------------------
Depending on use, you need to install a bunch of other things before you can
get on with it. Download and install [FFmpeg](https://ffmpeg.org/). You'll
also need to install Python, the version of which depends on which tool you'll
be using. *You are encouraged to use the UI version. I am no longer supporting
the CLI version, and neither does PyPI, so you're on your own wrt use and
package installation.*

**Converter Dependencies**
* Python 2.7.x, if using the command-line tool (`BUILD2.bat`)
  * ffmpy
  * pillow
* Python 3.10, if using the GUI (`main.py`)
  * pillow
  * ffmpeg
  * numpy
  * tktooltip
  * tkinterdnd2
  * scikit-learn
  * scikit-image

**Using the Converter**
* If using the command-line tool (`BUILD2.bat`)
  1. Copy your .MP4 or other video file to the CEVENCODER folder.
  2. Rename that video to a name that contains 8 or less characters.
  3. Open a command prompt in the CEVENCODER folder.
  4. Type into the cmd prompt: `BUILD2.BAT -h`
  5. Read the options, then retype the above line without the '-h' flag and with
    the flags that you want. For example, if your input video is MYVID.mp4 and you
    wanted to use the 96-by-X 4 level grayscale encoding with dithering:
    * `BUILD2.BAT -i MYVID.mp4 -e M1G4 -d`
    Available encoding formats used with the -e switch:
    * `M1B1` - 96*N x3 scaling, 1bpp color (black/white)
    * `M1G2` - 96*N x3 scaling, 2bpp color (black/white/lgray/dgray)
    * `M1G4` - 96*N x3 scaling, 4bpp color (black/white/ 14 grays)
    * `M1C4` - 96*N x3 scaling, 4bpp color (4 shades, 6 primaries, 6 secondaries)
    * `M1A4` - 96*N x3 scaling, 4bpp color (15 color adaptive palette)
    * `M2B1` - 144*N x2 scaling, 1bpp color (black/white)
    * `M2G2` - 144*N x2 scaling, 2bpp color (black/white/lgray/dgray)
    * `M2G4` - 144*N x2 scaling, 4bpp color (black/white/ 14 grays)
    * `M2C4` - 144*N x2 scaling, 4bpp color (4 shades, 6 primaries, 6 secondaries)
    * `M2A4` - 144*N x2 scaling, 4bpp color (15 color adaptive palette)
    Note that some of the information produced by its usage text is incorrect and
    will not be fixed anytime soon. If any information above contradicts the utility,
    assume that the text in this readme is correct.
  6. If everything worked, copy the contents of CEVENCODER/bin to your calculator.
* If using the GUI (`main.py`)
  1. Open a command prompt in the CEVENCODER folder.
  2. Type `python3 main.py`
  3. Use the Import button to select the file using the GUI, or drag & drop the
    video file into the window.
  4. Take a good, hard look at the UI, then push a bunch of buttons until
    something happens.

Using the Video Player
----------------------
The video player consists of two parts, you must build both of them 
and then send them to the calculator.

**Building the project**
* The main player software in CEVPLAY
  * Install [The CE Toolchain](https://ce-programming.github.io/toolchain/static/getting-started.html#getting-started) if you haven't already. The version that
  is known to work with this part of the project is `12.1`.
  * Open a command line in the CEVPLAY folder.
  * Run `make`.
  * Find `CEVIDIUM.8xp` in the `CEVPLAY/bin` folder, then send it to your
    calculator.
* The decoders that the player uses in CEVDECODER
  * Open a command line in the CEVDECODER folder.
  * Run `build.bat`.
  * Find `DECODEM1.8xv` and `DECODEM2.8xv` in the `CEVDECODER/bin` folder, then
    send them to your calculator. Archiving these files is recommended.

**Running the player**

`prgmCEVIDIUM` is an assembly program. TI has made it increasingly difficult
to run these types of programs. You can try these steps:

* Run the program from the homescreen as an `Asm(` program. Find the `Asm(`
  token from catalog by pressing `2nd`, then `0`, then pushing the `down`
  button until you select it. Press `Enter` to copy it to the homescreen,
  then proceed to put in the program as normal. The homescreen should read
  `Asm(prgmCEVIDIUM` when you are done. Press `Enter` to start.
* If you can't find `Asm(` in the catalog, it may be because your OS version
  is too high. In later versions of the OS, Texas Instruments removed that
  command to prevent people from easily running assembly programs, so you'll
  need a [jailbreak such as arTIfiCE](https://yvantt.github.io/arTIfiCE/).
  The instructions may both vary and change without warning, so I cannot
  copy them here.
* Some of the newest calculators may have had their exploits patched over
  such that no available jailbreak works. In that case, head on over to
  [Cemetech](https://www.cemetech.net/) to find out or ask for a working
  jailbreak.
* If the program runs but immediately quits, it's because you don't have
  any videos that CEVidium can recognize. Send some to the calculator!
  Here's a wonderful example containing [a dumpster fire](https://www.cemetech.net/downloads/files/2046/x2144)

Copyrights and Licenses
-----------------------
* The ZX7 (de)compression code and executable was created by Einar Saukas.
  See CEVENCODER/tools/ZX7_LICENSE for details.
* SPASM-ng (e)z80 assembler was created by a bunch of people.
  See CEVDECODER/tools/SPASM_LICENSE for details.
* The CEVidium CLI encoder, CEVidium player, and the decoders were crafted by me.
  See LICENSE for details.
* The CEVidium GUI encoder was programmed by me using AI-assistance. 
  See CONFESSIONS.md for details. Not sure how to license it.
  
Acknowledgements
----------------
* Merged fix for counting logic, by github user ctrefethen
* Those fixes for the original version of the encoder, by commandblockguy, whose
  pull requests I mismanaged because I didn't know what I was doing. (sorry!)
  
Controlling the Video Player
----------------------------

Controls on video selection:

| Keys     |  Function         |
|---------:|:------------------|
|[Mode]    | Quit CEVidium     |
|[2nd]     | Start video       |
|arrow keys| Show next video   |

Controls during playback:

| Keys     |  Function                         |
|---------:|:----------------------------------|
|[Mode]    | Retrun to video selection         |
|[2nd]     | (Un)pause the video               |
|[Left]    | Rewind video by one segment       |
|[Right]   | Fast forward video by one segment |


 
Version History (Player)
------------------------
* 0.00 - Initial commit
* 0.01 - Updated the documentation to make what's available actually useable
* 0.02 - Updated docs again, figuring out merge stuff to include others' improvements.
* 0.03 - Fixed a bug that prevented 4:3 video playback with the M1X2-ZX7 decoder.
		 Also changed UI spacing in the media player for readability and made
		 it easier to make other changes like that in the future.
* 0.04 - Label change to verify that CEVidium built with the new toolchain.

Known Issues
------------
* Deprecated the original encoder toolkit without prior notice but still have
  references for it for debugging purposes. You should be using BUILD2.bat
* If you choose to modify the build to use the old codecs, encoder 4 (DECODR03)
  is known to crash.
* You really cannot use Python 3 for this. Everything is broken and I'm
  trying to fix it. By burning it all to the ground. And then burning the
  ashes just to make sure.
* The shiny new GUI encoder doesn't support adaptive encoding. That's on the
  TODO list.
* The shiny new GUI encoder also sometimes mysteriously screws up. I ran into
  a problem importing a video. I "solved" it by closing the app and trying to
  do the same thing again. Intermittent problems, yeh?
* The rewind feature in the decoders aren't known to work properly. Getting that
  to work properly is encoder-dependant and involves starting each encoded
  segment with a keyframe. I... uh. Probably should make that an option.







