.ASSUME ADL=1
.ORG 0
.DB "8CECPck"
.ORG 7
.DB "4A3X-ZX7",0
.ORG 16
.DB 2
;NOTE: VRAM STARTS AT $D30000
#DEFINE BUFFER1 $D30000  ;GIVE IT 16KB to store 9600 bytes
#DEFINE BUFFER2 $D39600  ;ANOTHER 16KB 

#DEFINE INITIAL_FIELD_LOCATION $D42C00   ;MAIN FIELD LOCATION
#DEFINE MAIN_FIELD_LOCATION $D43000      ;CHANGE LATER TO $E30800 IF SMALL ENOUGH.
#DEFINE DECOMPRESSION_BUFFER $D44000     ;THIS BUFFER IS *JUST* LARGE ENOUGH

#DEFINE ONE_SECOND 32768
#DEFINE COL_ADR_SET $2A    ;X-AXIS (256px wide, start 32, end 288-1)
#DEFINE PAGE_ADR_SET $2B   ;Y-AXIS (144px high, start 48, end 192-1)

;KEEP VARIABLES IN THE SLACK OF THE STACK, POINTED TO BY IY
#DEFINE SEGMENT_ARRAY 3
#DEFINE VIDEO_STRUCT 6
#DEFINE CUR_SEG_PTR  -60
#DEFINE END_SEG_PTR  -63
#DEFINE OLD_BUFFER -69
#DEFINE OLD_LCDMODE -72
#DEFINE FRAME_HEIGHT -78
#DEFINE CUR_FRAME    -77
#DEFINE MAX_FRAMES   -76
#DEFINE SCREEN_ADR_OFFSET -75
;INITIAL FIELD - INITIALIZATION CODE GOES HERE
.DW INITIAL_FIELD_END-INITIAL_FIELD_START
.DL INITIAL_FIELD_LOCATION
.ORG INITIAL_FIELD_LOCATION
INITIAL_FIELD_START:
;Input arguments:
;	arg0 (+3): ptr to data segment array
;	arg1 (+6): ptr to video metadata struct
;		+0 *codec, +3 *title, +6 *author, +9 segments, +12 w, +15 h, +18 segframes
	DI
	LD IY,0
	ADD IY,SP
	PUSH IX
		LD HL,BUFFER1
		LD DE,BUFFER1+1
		LD BC,$012BFF
		LD (HL),$FF
		LDIR
		;SET UP LCD CONTROLLER
		;Note: It's possible you may need to deal with LCDTiming0 and LCDTiming1
		LD IX,$E30000
		LD HL,(IX+$10)
		LD (IY+OLD_BUFFER),HL
		LD A,(IX+$18)
		LD (IY+OLD_LCDMODE),A
		LD HL,BUFFER1
		LD (IX+$10),HL
		LD A,%00100101 ;4BPP MODE
		LD (IX+$18),A
		;SET 2,(IX+$19)           SET BIG-ENDIAN PIXEL ORDER
		OR A
		SBC HL,HL
		LD ($E30200+(15*2)),HL  ;FINAL UNUSED PALETTE ENTRY TO BLACK FOR BORDERS
		;GET ADDRESS FOR VIDEO STRUCT
		LD IX,(IY+VIDEO_STRUCT)  ;GET STRUCT
		;COPY RELEVENT INFORMATION FROM STRUCT TO STACK SLACK
		LD A,(IX+18)
		LD (IY+MAX_FRAMES),A
		LD DE,(IX+9)
		LD HL,(IY+SEGMENT_ARRAY)
		LD (IY+CUR_SEG_PTR),HL
		ADD HL,DE
		ADD HL,DE
		ADD HL,DE
		LD (IY+END_SEG_PTR),HL
		;SET UP LCD HARDWARE GIVEN SETUP
		LD DE,(IX+15) ;HEIGHT
		LD (IY+FRAME_HEIGHT),E  ;STORE FOR CALLED ROUTINE
		LD D,3
		MLT DE
		LD HL,240
		OR A
		SBC HL,DE
		SRL H
		RR  L    ;(MAXHEIGHT-VIDHEIGHT)/2. DIST BETWEEN TOP OF SCREEN AND TOP OF VID
		LD H,160
		MLT HL   ;OFFSET IN BYTES DOWN
		LD DE,8  ;*** PRECALCULATED WIDTH OFFSET
		ADD HL,DE  ;FULL OFFSET
		LD (IY+SCREEN_ADR_OFFSET),HL
		;SET UP TIMER HARDWARE - UNSETS POINTER TO STRUCT
		LD IX,$F20000
		XOR A
		LD (IX+$30),A  ;DISABLE TIMERS
		LEA DE,IX
		LD HL,TIMER_VALUES
		LD BC,TIMER_VALUES_END-TIMER_VALUES
		LDIR           ;LOAD COUNTER AND RESET REGISTERS TO TIMER_VALUES
		LD HL,%0000000000000011
		LD (IX+$30),HL ;TIMER CTRL REG ENABLE, SET XTAL TIMER 1, COUNT DOWN, NO INTR
		;SET UP MAIN LOOP LOOKUP TABLE
		LD IX,MAIN_FIELD_END  ;START SETTING UP LUT
		XOR A
_:		LD B,2
_:		rlca \ adc hl,hl \ rlca \ adc hl,hl \ rlca \ adc hl,hl \ rlca \ adc hl,hl \ rrca \ rrca \ rrca \ rrca
		rlca \ adc hl,hl \ rlca \ adc hl,hl \ rlca \ adc hl,hl \ rlca \ adc hl,hl \ rrca \ rrca \ rrca \ rrca
		rlca \ adc hl,hl \ rlca \ adc hl,hl \ rlca \ adc hl,hl \ rlca \ adc hl,hl
		DJNZ -_  ;BUT DON'T ROTATE BACK SINCE WE'RE FETCHING THE NEXT BIT NEXT ITER
		LD (IX+0),HL
		LEA IX,IX+3
		INC A
		JR NZ,--_
		;SYSTEM SET UP. START THE DECODER.
		;------------------------------------------------------------
		LD HL,(IY+SCREEN_ADR_OFFSET)
		LD (MFWOFST),HL       ;located in MAIN_FIELD
INIFIELD_LOAD_NEXT_SEGMENT:
		LD HL,(IY+CUR_SEG_PTR)
		LD HL,(HL)
		LD DE,DECOMPRESSION_BUFFER
		PUSH DE
			CALL _dzx7_Turbo  ;also located in MAIN_FIELD
			LEA HL,IY+MAX_FRAMES ;-76 MFR
			EX (SP),IY
			LD A,(HL)
			DEC HL     ;-77 CFR
			LD (HL),A  ;SET CUR FRAME
			CALL DRAW_SEGMENT
		POP IY
		LD DE,(IY+CUR_SEG_PTR)
		INC DE
		INC DE
		INC DE
		LD (IY+CUR_SEG_PTR),DE
		LD HL,(IY+END_SEG_PTR)
		OR A
		SBC HL,DE
		JP NC,INIFIELD_LOAD_NEXT_SEGMENT
		;------------------------------------------------------------
		;PUTAWAY - RESET TIMERS AND LCD HARDWARE.
		XOR A
		LD ($F20000),A  ;DISABLE TIMERS
		;RESTORE OLD MODES TO THE VIDEO CONTROLLER
		LD IX,$E30000
		LD HL,(IY+OLD_BUFFER)
		LD (IX+$10),HL
		LD A,(IY+OLD_LCDMODE)
		LD (IX+$18),A
	POP IX
	EI
	RET

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

	
	
TIMER_VALUES: ;30fps = 32768/30 ~~ 1092.2
.db $45,$04,$80,$00  ;Initial value: 1093+INT_MAX+1 to take advantage of sign flag.
.db $01,$00,$00,$00  ;reset value. Hang on 1.
TIMER_VALUES_END:


	
INITIAL_FIELD_END:

;MAIN FIELD - HIGH SPEED / MAIN LOOP CODE GOES HERE
.DW MAIN_FIELD_END-MAIN_FIELD_START
.DL MAIN_FIELD_LOCATION
.ORG MAIN_FIELD_LOCATION
MAIN_FIELD_START:

DRAW_SEGMENT:
	DEC HL     ;-78 FRH
	LD C,(HL)  ;READ FRAME_HEIGHT
	PUSH HL
		LD HL,$E30010
		LD IX,(HL)
		INC HL
		LD A,(HL)
		XOR $96
		LD (HL),A  ;FANCY BUFFER FLIPPING
		LD HL,$E30010
		LD L,$28
		SET 2,(HL)
		LD L,$20
_:		BIT 2,(HL)
		JR Z,-_
		CALL waitOneFrame			
		PUSH BC
			LD DE,$E30200
			LEA HL,IY+0
			LD BC,30
			LDIR
			LEA IY,IY+30
		POP BC
MFWOFST .EQU $+1
		LD DE,0
		ADD IX,DE
		LD DE,MAIN_FIELD_END
MAIN_FIELD_WRITE_FRAME:
		LD B,48
MAIN_FIELD_WRITE_LINE:
		LD L,(IY+0)
		LD H,3
		MLT HL
		ADD HL,DE
		LD HL,(HL)
		LD (IX+00),HL
		LEA IX,IX-34
		LD (IX-126),HL
		LEA IX,IX+68
		LD (IX+126),HL
		LEA IX,IX-34+3
		INC IY
;		LEA IX,IX+3
		DJNZ MAIN_FIELD_WRITE_LINE
		;16 to next line, 160+160 for next set to write. 336 total. brkdn: 122,122,92
		LEA IX,IX+122
		LEA IX,IX+122
		LEA IX,IX+92
		DEC C
		JR NZ,MAIN_FIELD_WRITE_FRAME
	POP HL
	INC HL    ;-77 CFR
	DEC (HL)
	JR NZ,DRAW_SEGMENT
	RET
	
; ===============================================================
; Dec 2012 by Einar Saukas & Urusergi
; "Turbo" version (89 bytes, 25% faster)
; ===============================================================
   ; enter : hl = void *src
   ;         de = void *dst
   ; uses  : af, bc, de, hl
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
MAIN_FIELD_END:



;END OF FILE
.ECHO "Initial field size: ",INITIAL_FIELD_END-INITIAL_FIELD_START,"\n","Main field size: ",MAIN_FIELD_END-MAIN_FIELD_START,"\n"
.END
.END
