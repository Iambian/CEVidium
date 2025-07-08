# CEVidium File Formats

This document describes the file formats used by the CEVidium video player, encoder, and decoders. CEVidium consists of a TI-84 Plus CE player (written in C), assembly decoders, and a Python video encoder.

All multi-byte data is stored in little-endian order due to the target platform's ez80 microprocessor.

CEVidium files are stored as "Application Variables" (*.8xv) to bypass filesystem restrictions on the target system.

## Definitions

*   **NULL:** A byte with a value of zero (0x00).
*   **NULL-padded:** A fixed-length sequence containing a variable-length sequence (at least one byte smaller) with unused bytes filled with NULLs.
*   **uint:** An unsigned integer with explicitly defined length (e.g., uint8, uint16).
*   **string:** A sequence of bytes that may contain NULLs. Text is ASCII-encoded unless otherwise specified. NULL terminators are included in the string's length.
*   **literal:** An explicitly defined number or string value.
*   **HEADER:** A sequence of bytes at the beginning of a file.
*   **FIELD:** A sequence of bytes following a HEADER.
*   **N byte:** A sequence of bytes whose length is determined elsewhere (either explicitly defined or inferred, such as a NULL-terminated string).

## Decoder File Format

CEVidium decoders are application variables with a HEADER followed by one or more FIELDs. The player scans for specific headers to identify decoder files.

**HEADER:**

*   `7 byte literal "8CECPck"`: Magic string identifying a decoder file.
*   `9 byte string, NULL-padded`: Decoder name.
*   `1 byte uint`: Number of FIELDs (must be greater than 0).

**FIELD:**

*   `2 byte uint`: Size of the FIELD's data segment.
*   `3 byte uint`: Address to relocate the FIELD's data segment to.
*   `N byte`: Data segment containing ez80 bytecode and data.

## Media File Format

CEVidium media files consist of a METADATA FILE and one or more DATA FILEs. DATA FILEs reference the METADATA FILE by name.

### METADATA FILE

**HEADER:**

*   `7 byte literal "8CEVDaH"`: Magic string identifying a METADATA FILE.
*   `9 byte string, NULL-padded`: Decoder name to use for DATA FILEs.
*   `N byte string, NULL-terminated`: Video title.
*   `N byte string, NULL-terminated`: Video author.
*   `2 byte uint`: Total number of FIELDs across all DATA files.
*   `2 byte uint`: Video width (native horizontal resolution).
*   `2 byte uint`: Video height (native vertical resolution).
*   `1 byte uint`: Number of video frames per video data FIELD.
*   `1 byte uint`: Bit depth code
*   `1 byte uint`: Video frame rate in FPS.

### DATA FILE

**HEADER:**

*   `7 byte literal "8CEVDat"`: Magic string identifying a DATA FILE.
*   `9 byte string, NULL-padded`: Name of the METADATA FILE this DATA FILE belongs to.
*   `1 byte uint`: Number of FIELDs in this file.

**FIELD:**

*   `2 byte uint`: ID of this field (non-sequential, allowing rearranging).
*   `2 byte uint`: Size of the field's data segment.
*   `N byte`: Data segment containing frame data (may be compressed).

## Frame Data Format - M1X3-ZX7 Decoder

This section describes the frame data format for the M1X3-ZX7 decoder.

*   All frames have a leading TYPE byte. Data following the TYPE byte depends on the TYPE.

*   **TYPE 0x00: End of Video**
    *   No data; stop video playback.
*   **TYPE 0x01: Raw Video Data**
    *   Width and height assumed to be the entire frame.
    *   Pixel data bytes, length `(width * height) * (bit_depth / 8)`
*   **TYPE 0x02: Partial Frame**
    *   Frame metadata, 4 entries, 1 byte each, in this order: `x, y, width, height`
    *   Frame data bytes, length `(width * height) * (bit_depth / 8)`
    *   `x` and `width` are selected to retain full byte alignedness at destination.
*   **TYPE 0x03: Duplicate Frame**
    *   No data; copy the previous frame verbatim.
*   **TYPE 0x04: 8x8 Grid Frame**
    *   `ACTIVE_BITFIELD`: Bits and bytes little-endian. The bits are packed from LSB (least significant bit) to MSB (most significant bit) within each byte. The entire bitfield is right-aligned within its allocated bytes. If the total number of 8x8 blocks is not a multiple of 8, the initial bytes of the bitfield are padded with zeros on the MSB side to ensure the active bits are right-aligned. Size: `(w/8*ceil(h/8))`
    *   `8x8 squares`: Data for each 8x8 square (or partial square at edges) is packed based on its *actual cropped dimensions*, not padded to a full 8x8 pixel size. The decoder dynamically adjusts its drawing routine for these partial heights. Size adjusted to input bitrate (e.g., 1bpp = 8 bytes for a full 8x8 block, 4bpp = 32 bytes for a full 8x8 block).

*   Immediately following all frame data (if the video palette is adaptive) is a delta palette update. This update consists of a `PALETTE_BITMAP` and, optionally, corresponding color data.

    *   **`PALETTE_BITMAP`**: A 16-bit bitfield (2 bytes) that specifies which of the 16 hardware palette entries (fields 0-15) are being updated.
        *   Each '1' bit in the bitmap indicates that the corresponding hardware palette entry will be updated. Bit 0 (LSB) maps to hardware palette field 0, and bit 15 (MSB) maps to hardware palette field 15.
        *   The `PALETTE_BITMAP` is read from LSB to MSB.
        *   If the frame is not adaptive, or if the frame `TYPE` does not carry frame data (e.g., `End of Video`), the `PALETTE_BITMAP` will be `0x0000`, and no color information will follow.
        *   Note: `PALETTE_BITMAP` is expected even after `Duplicate Frame` (TYPE 0x03) frames.

    *   **Color Data**: For every '1' bit in the `PALETTE_BITMAP`, two bytes of color information will immediately follow.
        *   The order of this color information matches the LSB-to-MSB order of the '1' bits in the `PALETTE_BITMAP`.
        *   Color data is stored in RGB555 format (16-bit, 5 bits for Red, 5 for Green, 5 for Blue, 1 bit unused, typically 0).

    The example block below illustrates this format.

    ```
    ; Example palette entry, TASM-style assembly.

    #define RGB555(r,g,b) (0<<15 + R<<10 + G<<5 + B<<0)
    .dw %0100000000001001       ; PALETTE_BITMAP, field mapping to 0, 3, and 14
    .dw RGB555(255,0,0)         ; Assign red to palette field 0.
    .dw RGB555(0,255,0)         ; Assign green to palette field 3.
    .dw RGB555(0,0,255)         ; Assign blue to palette field 14.

## Additional Notes That Needed To Be Rediscovered About This Format

*   **Bitfield Packing:** The `ACTIVE_BITFIELD` for `8x8 Grid Frame` (TYPE 0x04) is packed LSB-first within each byte. The entire bitfield, when viewed as a sequence of bytes, is right-aligned. If the total number of 8x8 blocks is not a multiple of 8, the initial bytes of the bitfield are padded with zeros on the MSB side to ensure the active bits are right-aligned. This is due to the decoder's loop counter behavior, which expects the unaligned portion of the dataset to occur at the start.
*   **Partial 8x8 Block Data:** For `8x8 Grid Frame` (TYPE 0x04), the packed data for individual 8x8 squares (or partial squares at the right/bottom edges of the frame) should correspond to their *actual cropped dimensions*. The decoder's drawing routine (`M1X3-ZX7.asm`) dynamically adjusts to draw these partial blocks correctly, so no padding to a full 8x8 packed size is required in the encoder's output.
*   Partial frame X-coordinate and width must be byte-aligned. X-coordinate 0 is considered aligned.
*   The current distribution of the M1X3-ZX7 library halts on an illegal frame type, but M1X2-ZX7 does not. The latter quits playback instead, which meant that EOF wasn't strictly required when using that decoder.
*   The `PALETTE_BITMAP` is expected even after duplicate frames. This would theoretically allow animations to be carried solely in palette updates, as old palettized animations from ancient GIFs and games sometimes did, but none of our encoders are smart enough to actually detect this sort of thing. I think. 
*   From reading the decoder, the only frame type that doesn't expect a `PALETTE_BITMAP` would be the `End of Video` frame type. The code involved in handling EoV/EoF involves a stack unwinding that bypasses palette placement and skips straight to cleanup code.
*   `ACTIVE_BITFIELD` May not be larger than 256 bits (32 bytes). This can't be done with a M1X3-ZX7 decodeable stream (since you'd run into height problems first), but can be accomplished with a stream decodeable by M1X2-ZX7. In fact, M1X2-ZX7 had to be kludged to accept a bitfield equal to the stated maximum size. Anything larger, however, and the stream will be treated as though its size had its uppermost bits chopped off. (size % 32 bytes)
