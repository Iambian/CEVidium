.ASSUME ADL=1

#DEFINE VBUFSTART $D40000       ;Start of VRAM, screen buffer
#DEFINE VBUFSIZE  $012C00       ;Total size of video buffer: x2 4bpp buffers
#DEFINE BUFSWAPMASK $96         ;XOR this with 2nd byte of screen buffer address
#DEFINE MAIN_FIELD_LOC $D52C00  ;Primary location, 3072 bytes large
#DEFINE FAST_FIELD_LOC $D53800  ;Reserved for fast code exec, 1024 bytes large
#DEFINE DECOMP_BUFFER  $D54000  ;

#DEFINE VLCD_CTRL $E30000
#DEFINE VLCD_PAL  $E30200

#DEFINE BDA_FIELD_WIDTH 7
#DEFINE SCOL_CMD $2A	;X-AXIS (256px wide, start 32, end 288-1)
#DEFINE SROW_CMD $2B	;Y-AXIS (144px high, start 48, end 192-1)
#DEFINE LCD_WIDTH 320
#DEFINE LCD_HEIGHT 240
#DEFINE VIDEO_WIDTH 96
#DEFINE SCALE_FACTOR 3
#DEFINE DRAWFRAME_SMC_BLOCKLEN 15

#DEFINE VSEG_ARR 3
#DEFINE VSTRUCT  6
#DEFINE VSEG_STR -40
#DEFINE VSEG_CUR -43
#DEFINE VSEG_END -46
#DEFINE PREV_BUF -49
#DEFINE PREV_LMO -52
#DEFINE M_FRAMES -55
#DEFINE C_FRAME  -56
#DEFINE F_HEIGHT -57

#DEFINE V_CODEC  0
#DEFINE V_TITLE  3
#DEFINE V_AUTH   6
#DEFINE V_SEGS   9
#DEFINE V_WIDTH  12
#DEFINE V_HEIGHT 15
#DEFINE V_SEGFR  18
#DEFINE V_BDEPTH 21


.ORG 0  \ .DB "8CECPck"     ;Decoder file header
.ORG 7  \ .DB "M1X3-ZX7",0  ;Multiformat ver 1, scale x3, ZX7 decompression
.ORG 16 \ .DB 2             ;Number of fields
;===================================================================================
;===================================================================================
;===================================================================================
;===================================================================================
.DW MF_END-MF_START \ .DL MAIN_FIELD_LOC \ .ORG MAIN_FIELD_LOC
;In: (SP+3) = ptr to data segment array, (SP+6) = ptr to video metadata struct
MF_START:
	DI
	LD IY,0
	ADD IY,SP
	LD HL,(IY+VSTRUCT)
	LD BC,V_BDEPTH
	ADD HL,BC
	LD A,(HL)   ;Fetch bit depth
	CP 5
	RET NC
	;JR $
	PUSH IX
		PUSH AF
		;CLEAR SCREEN BUFFERS
			LD HL,VBUFSTART
			LD BC,VBUFSIZE
			CALL $0210DC ;MemClear
		;-- SET UP LCD CONTROLLER
			LD IX,VLCD_CTRL
			LD HL,(IX+$10)  \ LD (IY+PREV_BUF),HL  ;SAVE PREVIOUS BUFFER ADDRESS
			LD A,(IX+$18)   \ LD (IY+PREV_LMO),A   ;SAVE LCD BIT DEPTH MODE
			LD HL,VBUFSTART \ LD (IX+$10),HL       ;SET CURRENT BUFFER ADDRESS
		POP AF
		OR A \ SBC HL,HL \ LD L,A \ LD H,BDA_FIELD_WIDTH \ MLT HL
		LD DE,bitDepthActionTable \ ADD HL,DE  ;GET BIT DEPTH FIELD TABLE ENTRY
		LD A,(HL) \ INC HL \ LD (IX+$18),A     ;SET CURRENT BIT DEPTH MODE
		RES 2,(IX+$19)                         ;RESET BIG-ENDIAN PIXEL ORDER
		PUSH HL
			LD HL,(HL) \ LD DE,VLCD_PAL \ LD BC,32 \ LDIR  ;SET DEFAULT PALETTE
		;COPY RELEVENT INFORMATION FROM STRUCT TO STACK SLACK
			LD IX,(IY+VSTRUCT)
			LD A,(IX+V_SEGFR) \ LD (IY+M_FRAMES),A
			LD HL,(IY+VSEG_ARR) \ LD (IY+VSEG_STR),HL \ LD (IY+VSEG_CUR),HL
			LD DE,(IX+V_SEGS) \ ADD HL,DE \ ADD HL,DE \ ADD HL,DE \ LD (IY+VSEG_END),HL
		;SET UP LCD HARDWARE / SCREEN BOUNDARIES
			LD A,(IX+V_HEIGHT) \ LD (IY+F_HEIGHT),A
			LD E,A \ LD D,SCALE_FACTOR \ MLT DE \ LD HL,LCD_HEIGHT ; (MAXHEIGHT-VIDHEIGHT)/2 = DIST
			OR A \ SBC HL,DE \ SRL H \ RR  L            ; BTWN SCREEN-TOP AND VID-TOP
			EX DE,HL                                    ; Y OFFSET IN DE
		POP HL
		INC HL \ INC HL \ INC HL \ LD HL,(HL)  ;GET ADR FOR VOFFSET + LUT SETUP
		LD IX,FF_END
		LD BC,+_
		PUSH BC
			JP (HL)
_:		;SET UP DECODER GRID
		LD A,(IY+F_HEIGHT)
		TST A,%00000111
		JR Z,+_
		SUB A,8
		LD (sfs_8x8_vidheight),A  ;IN THE GRID ARRAY CODE. REMOVE THE ADD/SUB
		ADD A,8
		JR ++_
_:		LD (sfs_8x8_vidheight),A  ;IN THE GRID ARRAY CODE. REMOVE THE ADD/SUB
_:		TST A,%00000111 ;CHECK TO SEE IF h%8 IS NONZERO
		JR Z,+_
		ADD A,8         ;IF NOT, ceil() IT
_:		AND A,%11111000
		LD L,A
		LD H,VIDEO_WIDTH
		MLT HL
		ADD HL,HL
		ADD HL,HL  ;X4 TO MAKE /256 BY TAKING JUST H
		LD A,H
		LD (sfs_8x8_vidloop),A
		RRCA \ RRCA \ RRCA  ;DIV 8 TO GET NUMBER OF BYTES TO OFFSET
		TST A,%11100000
		JR Z,+_         ;HOW MANY TIMES DO I HAVE TO DO ceil() ???
		INC A
_:		AND A,%00011111
		JR NZ,_			;KLUDGE FOR 4:3 VIDEOS
		LD A,%00100000  ;THIS IS A TERRIBLE HACK THERE HAS TO BE A BETTER WAY
_:		LD (sfs_8x8_vidoffset),A
;SET UP TIMER HARDWARE - UNSETS POINTER TO STRUCT
		CALL resetTimer
		;SYSTEM SET UP. START THE DECODER.
		;------------------------------------------------------------
MF_LOAD_NEXT_SEGMENT:
		LD HL,(IY+VSEG_CUR)
		LD HL,(HL)
		LD DE,DECOMP_BUFFER
		PUSH DE
			CALL _dzx7_Turbo  ;also located in MAIN_FIELD
		CALL waitOneFrame			
		LEA HL,IY+M_FRAMES ;-25 MFR
			EX (SP),IY
			LD A,(HL)
			DEC HL     ;-26 CFR
			LD (HL),A  ;SET CUR FRAME
MF_DRAW_FRAME_LOOP:
			DEC HL     ;-78 FRH
			LD C,(HL)  ;READ FRAME_HEIGHT
			PUSH HL
				CALL setupFrameState  ;Checks frame data and sets up renderer state
				CALL drawFrame
MF_SKIP_FRAME_DRAW:
			POP HL
			INC HL    ;-77 CFR
			CALL doControls
			DEC (HL)
			CALL handleDeltaPaletteAndTiming  ;must preserve flags since using them too
			JR NZ,MF_DRAW_FRAME_LOOP
		POP IY
		LD DE,(IY+VSEG_CUR)
		INC DE
		INC DE
		INC DE
		LD (IY+VSEG_CUR),DE
		LD HL,(IY+VSEG_END)
		OR A
		SBC HL,DE
		JP NC,MF_LOAD_NEXT_SEGMENT
MF_STOP_PLAYBACK:
		;------------------------------------------------------------
		;PUTAWAY - RESET TIMERS AND LCD HARDWARE.
		XOR A \ LD ($F20000),A  ;DISABLE TIMERS
		;RESTORE OLD MODES TO THE VIDEO CONTROLLER
		LD IX,VLCD_CTRL
		LD HL,(IY+PREV_BUF) \ LD (IX+$10),HL ;RESTORE SCREEN ADDRESS
		LD A,(IY+PREV_LMO)  \ LD (IX+$18),A  ;RESTORE LCD BIT DEPTH
		RES 2,(IX+$19)                       ;RESET BIG-ENDIAN PIXEL ORDER (DEFAULT)
	POP IX
	EI
	RET
;===================================================================================
; Setup subroutines
#DEFINE NXRW1B (320*SCALE_FACTOR/8)+0
#DEFINE NXRW2B (320*SCALE_FACTOR/4)+0
#DEFINE NXRW4B (320*SCALE_FACTOR/2)+0

ofsAndLUTSetup1bpp:
	LD D,40  \ MLT DE \ INC DE \ INC DE
	PUSH DE
		XOR A
_:		LD B,8
_:		RLCA \ ADC HL,HL \ RRCA
		RLCA \ ADC HL,HL \ RRCA
		RLCA \ ADC HL,HL
		DJNZ -_
		LD (IX+0),HL
		LEA IX,IX+SCALE_FACTOR
		INC A
		JR NZ,--_
		;ADDITIONAL SMC SETUP
		LD A,40       \ LD (sdw_smc_ymultiplier),A
		LD HL,$1F1F1F \ LD (sdw_smc_wdivider),HL \ LD (sdw_smc_xdivider),HL
		LD HL,NXRW1B  \ LD (sdw_smc_nextrow),HL
		LD DE,ofsAndLUTSetup1bpp_renderer
		;--------------------
		JP ofsAndLUTSetup_collect
ofsAndLUTSetup1bpp_renderer:
	LD (IX-40),HL
	LD (IX+40),HL
	LEA IX,IX+3
	JR ofsAndLUTSetup1bpp_renderer+15

ofsAndLUTSetup2bpp:
	LD D,80  \ MLT DE \ INC DE \ INC DE \ INC DE \ INC DE
	PUSH DE
		XOR A
_:		LD B,4
_:		RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RRCA \ RRCA
		RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RRCA \ RRCA
		RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL
		DJNZ -_
		LD (IX+0),HL
		LEA IX,IX+SCALE_FACTOR
		INC A
		JR NZ,--_
		;ADDITIONAL SMC SETUP
		LD A,80       \ LD (sdw_smc_ymultiplier),A
		LD HL,$1F1F00 \ LD (sdw_smc_wdivider),HL \ LD (sdw_smc_xdivider),HL
		LD HL,NXRW2B  \ LD (sdw_smc_nextrow),HL
		LD DE,ofsAndLUTSetup2bpp_renderer
		;--------------------
		JR ofsAndLUTSetup_collect
ofsAndLUTSetup2bpp_renderer:
	LD (IX-80),HL
	LD (IX+80),HL
	LEA IX,IX+3
	JR ofsAndLUTSetup2bpp_renderer+15

ofsAndLUTSetup4bpp:
	LD D,160 \ MLT DE \ LD A,E \ ADD A,8 \ LD E,A
	PUSH DE
		XOR A
_:		LD B,2
_:		RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RRCA \ RRCA \ RRCA \ RRCA
		RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RRCA \ RRCA \ RRCA \ RRCA
		RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL \ RLCA \ ADC HL,HL
		DJNZ -_
		LD (IX+0),HL
		LEA IX,IX+SCALE_FACTOR
		INC A
		JR NZ,--_
		;ADDITIONAL SMC SETUP
		LD A,160      \ LD (sdw_smc_ymultiplier),A
		LD HL,$1F0000 \ LD (sdw_smc_wdivider),HL \ LD (sdw_smc_xdivider),HL
		LD HL,NXRW4B  \ LD (sdw_smc_nextrow),HL
		;--------------------
		LD DE,ofsAndLUTSetup4bpp_renderer
ofsAndLUTSetup_collect:
	POP HL
	LD (sdw_smc_screenofset),HL
	EX DE,HL
	LD DE,df_hdraw_smc_routine
	LD BC,DRAWFRAME_SMC_BLOCKLEN
	LDIR
	RET
ofsAndLUTSetup4bpp_renderer:
	LEA IX,IX-34     ;3b
	LD (IX-126),HL   ;3b
	LEA IX,IX+68     ;3b
	LD (IX+126),HL   ;3b
	LEA IX,IX-34+3   ;3b - total 15 bytes
	
;===================================================================================
; Standalone utilities


waitOneFrame:
	LD HL,$F20002
_:	BIT 7,(HL)
	JR NZ,-_
	LD L,$30
	XOR A
	LD (HL),A
	LD L,A
	LD DE,(HL)
	PUSH HL
		LD HL,1093
		ADD HL,DE
	POP DE
	EX DE,HL
	LD (HL),DE
	LD L,$30
	LD (HL),3
	RET	
	
waitAnyKey:
	CALL keyWait
_:	CALL getKbd
	OR	A
	JR Z,-_
keyWait:
	CALL getKbd
	OR 	A
	JR	NZ,keyWait
	RET

getKbd:
	PUSH HL
		LD	HL,$F50200	;DI_MODE=$F5XX00
		LD	(HL),H
		XOR	A,A
_:		CP	A,(HL)
		JR	NZ,-_
		LD	L,$12  ;GROUP 1 (top keys)
		LD	A,(HL)
		LD	L,$1E  ;GROUP 7 (dpad)
		XOR	(HL)
		AND	%11110000
		XOR (HL)   ;b0:dwn b1:lft b2:rig b3:up b4:yeq b5:2nd b6:mod b7:del
	POP HL
	RET

resetTimer:
	LD IX,$F20000
	XOR A
	LD (IX+$30),A  ;DISABLE TIMERS
	LEA DE,IX
	LD HL,TIMER_VALUES
	LD BC,TIMER_VALUES_END-TIMER_VALUES
	LDIR           ;LOAD COUNTER AND RESET REGISTERS TO TIMER_VALUES
	LD HL,%000000000000000000000011
	LD (IX+$30),HL ;TIMER CTRL REG ENABLE, SET XTAL TIMER 1, COUNT DOWN, NO INTR
	RET


;===================================================================================
; Video player user controls
	
doControls:
_:	CALL getKbd
	BIT 5,A
	JR	Z,_doctrls_skipPause
	CALL waitAnyKey
	JR	-_
_doctrls_skipPause:
	BIT	6,A
	JR	Z,_doctrls_skipStop
	POP	AF
	POP	IY
	CALL keyWait
	JP MF_STOP_PLAYBACK
_doctrls_skipStop:
	BIT	1,A
	JR	Z,_doctrls_skipRewind
	LD	HL,-3
	JR _doctrls_changepos
_doctrls_skipRewind:
	BIT	2,A
	JR	Z,_doctrls_skipFastFwd
	LD	HL,3
_doctrls_changepos:
	POP	AF  ;rem doctrls to main
	POP IY  ;get saved stack pointer position
	LD	DE,(IY+VSEG_CUR)
	ADD	HL,DE
	EX	DE,HL
	LD	HL,(IY+VSEG_STR)
	OR	A
	SBC HL,DE  ;STARTSEG-NEWSEG. IF ZERO, CONTINUE. THEN IF NC, SKIP WRITEBACK
	JR	Z,+_
	JR	NC,_doctrls_donotchangepos
_:	LD	HL,(IY+VSEG_END)
	OR	A
	DEC HL
	DEC HL
	DEC HL
	SBC HL,DE  ;ENDSEG-NEWSEG. IF C, WENT PAST END: SKIP WRITEBACK
	JP	C,MF_STOP_PLAYBACK
	LD	(IY+VSEG_CUR),DE
	CALL resetTimer
_doctrls_donotchangepos:
	JP	MF_LOAD_NEXT_SEGMENT	
_doctrls_skipFastFwd:
	RET
	
;===================================================================================
; Video frame formatter
	
setupFrameState:
	LD B,(IY+0)
	INC IY
	INC B
	DJNZ sfs_skip_eov
	;End of Video
	POP AF
	POP AF
	POP IY
	JP MF_STOP_PLAYBACK
sfs_skip_eov:
	DJNZ sfs_skip_rawvideo
	;raw video
	LD HL,(256*0)+0
	LD DE,VIDEO_WIDTH
	JP setDrawWindow
sfs_skip_rawvideo:
	DJNZ sfs_skip_partialframe
	;partial frame
	CALL copyPreviousFrame
	;jr $
	LD HL,(IY+0)
	LD E,(IY+2)
	LD C,(IY+3)
	LEA IY,IY+4
	JP setDrawWindow
sfs_skip_partialframe:
	DJNZ sfs_skip_duplicateframe
	;duplicate frame
	CALL copyPreviousFrame
	POP AF
	JP MF_SKIP_FRAME_DRAW
sfs_skip_duplicateframe:
	;DEC B \ JP NZ,sfs_skip_8x8boxes
	DJNZ sfs_skip_8x8boxes
	;render 8x8 box grid
	;Screen width fixed at VIDEO_WIDTH, screen height in C
	CALL copyPreviousFrame
sfs_8x8_vidoffset .EQU $+1
	LD DE,0  ;LOWEST BYTE ALWAYS WRITTEN, NO OTHERS ARE
	LEA HL,IY+0
	ADD IY,DE
	LD E,D
	LD A,8
	LD (sfs_blockheight_smc),A
sfs_8x8_vidloop .EQU $+1
	LD B,0
sfs_8x8_vidheight .EQU $+1
	LD C,0
	;DE = [0,0] , HL = PTR TO BITFIELD, IY = DATA STREAM, B = LOOP COUNTER
	JR +_          ;SKIP OVER INITIAL LOOP TEST IN CASE B%8 WAS ZERO TO START WITH
sfs_df_mainloop:
	LD A,B
	AND %00000111  ;IF ZERO, BIT-BYTE BOUNDS REACHED. INCREMENT HL
	JR NZ,_
	INC HL
_:	RR (HL)
	JR NC,sfs_df_preservebox
	PUSH BC
		PUSH DE
			PUSH HL
				EX DE,HL
				LD E,8
sfs_blockheight_smc .EQU $+1
				LD C,8
				CALL setDrawWindow
				CALL drawFrame
			POP HL
		POP DE
	POP BC
sfs_df_preservebox:
	LD A,E
	ADD A,8
	CP A,VIDEO_WIDTH
	JR C,++_ ;IF NOT REACHED THE RIGHT EDGE OF THE SCREEN, SKIP TO WRITE X BACK
	LD A,D   ;OTHERWISE, MOVE Y DOWNWARD AND ZERO OUT X
	ADD A,8
	LD D,A
	LD A,C   ;ALSO DECREMENT SCREEN HEIGHT BY 8
	SUB A,8  ;AND REDUCE BLOCKHEIGHT IF IT EVER FALLS BELOW 0
	LD C,A   ;BY THE AMOUNT IT WOULD'VE BEEN HAD THE SUBTRACTION NOT TAKEN PLACE
	JR NC,+_
	ADD A,8
	LD (sfs_blockheight_smc),A
_:	XOR A
_:	LD E,A
	DJNZ sfs_df_mainloop
	POP AF   ;REMOVES RETURN ADDRESS. SP LEVEL BACK TO MAIN.
	JP MF_SKIP_FRAME_DRAW
sfs_skip_8x8boxes:
	;Out of bounds video data. Do not process. End video playback.
	JR $		;DEBUG: HALT IF INVALID VIDEO FRAME TYPE
	POP AF
	POP AF
	POP IY
	JP MF_STOP_PLAYBACK
	
;===================================================================================
; Video frame formatter subroutines

;in:  L=Xpos,H=Ypos,E=width
;out: IX=drawpos, C=Loop
setDrawWindow: 
	;Set window offset
	PUSH DE
		LD A,L
		LD L,SCALE_FACTOR
		MLT HL
sdw_smc_ymultiplier .EQU $+1
		LD H,40
		MLT HL
		EX DE,HL
		OR A
sdw_smc_xdivider .EQU $
		RRA
		RRA
		RRA
		AND %00111111
		LD L,A
		LD H,SCALE_FACTOR
		MLT HL
sdw_smc_screenofset .EQU $+2
		LD IX,0
		ADD HL,DE
		EX DE,HL
		ADD IX,DE
		LD DE,(VLCD_CTRL+$10)
		ADD IX,DE
	POP DE
	LD A,E     ;Get img width
	SBC HL,HL  
	EX DE,HL   ;Zero out HL
sdw_smc_wdivider .EQU $+0	;Set frame render loop parameters
	RRA \ RRA \ RRA ;div 8 for 1bpp. RRA RRA NOP for div 4 (2bpp), RRA NOP NOP for div 2 (4bpp)
	AND %00111111
	JR	Z,$			;DEBUG: Halt if width is zero. This causes... problems.
	LD (df_smc_hdraw),A
	LD E,A     ;Set adjusted width in E.
	ADD A,A    ;
	ADD A,E    ;x3 to scale.
	LD E,A
sdw_smc_nextrow .EQU $+1
	LD HL,0
	SBC HL,DE
	LD (df_smc_nextrow),HL
	RET

	
handleDeltaPaletteAndTiming:
	PUSH HL
		PUSH AF
			call writeDeltaPalette
			;LEA IY,IY+2
			LD HL,$E30011
			LD A,(HL)
			XOR BUFSWAPMASK
			LD (HL),A  ;FANCY BUFFER FLIPPING
		POP AF
		PUSH AF
			CALL NZ,waitOneFrame
		POP AF
	POP HL
	RET
	
	
writeDeltaPalette: ;IY handled. IY must point to start of data field.
	LD B,15
	LD HL,$E30202
	LD DE,(IY+0)
	LEA IY,IY+2
_:	SRL D
	RR  E
	JR NC,+_
	LD A,(IY+0)
	LD (HL),A
	INC HL
	LD A,(IY+1)
	LD (HL),A
	DEC HL
	LEA IY,IY+2
_:	INC HL
	INC HL
	DJNZ --_
	RET
	
copyPreviousFrame:
	LD HL,(VLCD_CTRL+$10)  ;Currently active buffer
	LD BC,$009600
	PUSH HL
	POP DE
	LD A,D
	XOR BUFSWAPMASK
	LD D,A
	EX DE,HL
	LDIR
	RET
	
	
	
	
	;jr $
	PUSH HL
		LD A,H
		XOR BUFSWAPMASK
		LD H,A             ;Set HL to inactive buffer (drawing to)
		LD DE,(sdw_smc_screenofset)
		ADD HL,DE          ;Add screen offset to start copying to
		EX (SP),HL         ;Swap adjusted inactive buffer to active buffer
		ADD HL,DE          ;Add screen offset to start copying from.
		PUSH HL
			EX DE,HL       ;The offset is supposed to center the image, so doubling it
			ADD HL,HL      ;should give me the total blank area.
			LD DE,BUFSWAPMASK*256  ;And this is the screen buffer's total size.
			EX DE,HL
			SBC HL,DE      ;screen-blank = Frame area
			INC HL         ;In case of inaccuracies
			PUSH HL
			LD A,C         ;PRESERVE C
			POP BC
		POP HL
	POP DE
	EX DE,HL  ;Figure out why we needed them swapped.
	LDIR
	LD C,A
	RET

;===================================================================================
;Data section

TIMER_VALUES: ;30fps = 32768/30 ~~ 1092.2
.db $45,$04,$80,$00  ;Initial value: 1093+INT_MAX+1 to take advantage of sign flag.
.db $01,$00,$00,$00  ;reset value. Hang on 1.
TIMER_VALUES_END:

bitDepthActionTable:
;1bpp
.db %00100001 \.dl palette1bpp      \.dl ofsAndLUTSetup1bpp
;2bpp
.db %00100011 \.dl palette2bpp      \.dl ofsAndLUTSetup2bpp
;4bpp gs
.db %00100101 \.dl palette4bpp_gs   \.dl ofsAndLUTSetup4bpp
;4bpp col
.db %00100101 \.dl palette4bpp_col  \.dl ofsAndLUTSetup4bpp
;4bpp adaptive
.db %00100101 \.dl nullPalette      \.dl ofsAndLUTSetup4bpp

nullPalette:
.dw 0
palette1bpp:
.dw 0,-1
palette2bpp:
.dw 0,%1011000110001100,%1101101011010110,-1
palette4bpp_gs:
.dw %0000000000000000,%0000100001000010,%0001100011000110,%0001000010000100
.dw %0010100101001010,%0010000100001000,%0011100111001110,%0011000110001100
.dw %0100101001010010,%0100001000010000,%0101101011010110,%0101001010010100
.dw %0110101101011010,%0110001100011000,%0111101111011110,%0111001110011100
palette4bpp_col:
.dw %0000000000000000 ;0,0,0,
.dw %1011000110001100 ;85,85,85,
.dw %1101101011010110 ;170,170,170
.dw %0111111111111111 ;255,255,255
.dw %0011110000000000 ;127,0,0, 
.dw %0000000111100000 ;0,127,0, 
.dw %0000000000001111 ;0,0,127,
.dw %0011110111100000 ;127,127,0, 
.dw %0011110000001111 ;127,0,127, 
.dw %0000000111101111 ;0,127,127, 
.dw %0111110000000000 ;255,0,0, 
.dw %0000001111100000 ;0,255,0, 
.dw %0000000000011111 ;0,0,255,
.dw %0111111111100000 ;255,255,0, 
.dw %0111110000011111 ;255,0,255, 
.dw %0000001111111111 ;0,255,255, 


MF_END:
;===================================================================================
;===================================================================================
;===================================================================================
;===================================================================================
;===================================================================================
;===================================================================================
;===================================================================================
.DW FF_END-FF_START \.DL FAST_FIELD_LOC \.ORG FAST_FIELD_LOC
FF_START:
;===================================================================================
;High speed frame render loop

drawFrame:
;
df_verticaldraw:
;	jr $
df_smc_hdraw .EQU $+1
	LD B,VIDEO_WIDTH/2
	LD DE,FF_END
df_horizontaldraw:
	LD L,(IY+0)
	LD H,SCALE_FACTOR
	MLT HL
	ADD HL,DE
	LD HL,(HL)
	LD (IX+00),HL
df_hdraw_smc_routine:
.block DRAWFRAME_SMC_BLOCKLEN
	INC IY
	DJNZ df_horizontaldraw
df_smc_nextrow .EQU $+1
	LD DE,0
	ADD IX,DE
	DEC C
	JR NZ,df_verticaldraw
	RET
	
	
;===================================================================================
; Dec 2012 by Einar Saukas & Urusergi - "Turbo" version (89 bytes, 25% faster)
; in: HL=src, out: DE=dst, dstr: AF,BC,DE,HL
_dzx7_Turbo:
        ld      a, 128
dzx7t_copy_byte_loop:
        ldi                             ; copy literal byte
dzx7t_main_loop:
        add     a, a                    ; check next bit
        call    z, dzx7t_load_bits      ; no more bits left?
        jr      nc, dzx7t_copy_byte_loop ; next bit indicates either literal or sequence
; determine number of bits used for length (Elias gamma coding)
        push    de
        ld      de, 0
        ld      bc, 1
dzx7t_len_size_loop:
        inc     d
        add     a, a                    ; check next bit
        call    z, dzx7t_load_bits      ; no more bits left?
        jr      nc, dzx7t_len_size_loop
        jp      dzx7t_len_value_start
; determine length
dzx7t_len_value_loop:
        add     a, a                    ; check next bit
        call    z, dzx7t_load_bits      ; no more bits left?
        rl      c
        rl      b
        jr      c, dzx7t_exit           ; check end marker
dzx7t_len_value_start:
        dec     d
        jr      nz, dzx7t_len_value_loop
        inc     bc                      ; adjust length
; determine offset
        ld      e, (hl)                 ; load offset flag (1 bit) + offset value (7 bits)
        inc     hl
        sla e
        inc e
        jr      nc, dzx7t_offset_end    ; if offset flag is set, load 4 extra bits
        add     a, a                    ; check next bit
        call    z, dzx7t_load_bits      ; no more bits left?
        rl      d                       ; insert first bit into D
        add     a, a                    ; check next bit
        call    z, dzx7t_load_bits      ; no more bits left?
        rl      d                       ; insert second bit into D
        add     a, a                    ; check next bit
        call    z, dzx7t_load_bits      ; no more bits left?
        rl      d                       ; insert third bit into D
        add     a, a                    ; check next bit
        call    z, dzx7t_load_bits      ; no more bits left?
        ccf
        jr      c, dzx7t_offset_end
        inc     d                       ; equivalent to adding 128 to DE
dzx7t_offset_end:
        rr      e                       ; insert inverted fourth bit into E
; copy previous sequence
        ex      (sp), hl                ; store source, restore destination
        push    hl                      ; store destination
        sbc     hl, de                  ; HL = destination - offset - 1
        pop     de                      ; DE = destination
        ldir
dzx7t_exit:
        pop     hl                      ; restore source address (compressed data)
        jp      nc, dzx7t_main_loop
dzx7t_load_bits:
        ld      a, (hl)                 ; load another group of 8 bits
        inc     hl
        rla
        ret
	
;#IF ($&$ff)
;	.BLOCK ~$&$ff+1
;#ENDIF

FF_END:
;===================================================================================
;===================================================================================
;===================================================================================
;===================================================================================
;END OF FILE
.ECHO "Assembling decoder M1X3-ZX7"
.ECHO "Main field size: ",MF_END-MF_START,"\n","Fast field size: ",FF_END-FF_START,"\n"
.END
.END
