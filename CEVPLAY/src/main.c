/*
 *--------------------------------------
 * Program Name: CEVidium
 * Author: Rodger "Iambian" Weisman
 * License: MIT
 * Description: Plays specially-formatted video
 *--------------------------------------
*/

#define T_UI_WIDTH 309
#define T_UI_STRTX 5
#define T_UI_STRTY 65
#define T_UI_BARHGHT 4
#define T_UI_DHT 19
#define T_NUMLINES 4
#define T_TEXTYSTART 8

#define CAT(x,y) CAT_(x,y)
#define CAT_(x,y) x ## y

#define T_XPOS(x)  (T_UI_STRTX+x)
#define T_YPOS(ln) (T_UI_STRTY+(T_UI_DHT*ln))
#define T_TPLC(x,y,w) (T_XPOS(x)),(T_YPOS(y)),(T_XPOS(x)+w),(T_YPOS(y)+T_UI_BARHGHT)
#define T_DIALOG(b) T_TPLC(CAT(b,X),CAT(b,LINE),CAT(b,WIDTH))
#define T_TEXTY(ynm) (T_YPOS(ynm)+T_TEXTYSTART)
#define T_VERTDIV(base) (T_XPOS(CAT(base,X))+CAT(base,WIDTH)),(T_YPOS(CAT(base,LINE))),T_UI_DHT
/* Line 0 */
#define T_VNAMEX 0
#define T_VNAMELINE 0
#define T_VNAMEWIDTH 309
/* Line 1 */

#define T_VAUTHX 0
#define T_VAUTHLINE 1
#define T_VAUTHWIDTH 309
/* Line 2 */
#define T_FNAMEX 0
#define T_FNAMELINE 2
#define T_FNAMEWIDTH 76

#define T_VTIMEX (T_FNAMEWIDTH+2)
#define T_VTIMELINE 2
#define T_VTIMEWIDTH 76

#define T_DNAMEX (T_FNAMEWIDTH+2+T_VTIMEWIDTH+2)
#define T_DNAMELINE 2
#define T_DNAMEWIDTH 76

#define T_BTSPPX (T_FNAMEWIDTH+2+T_VTIMEWIDTH+2+T_DNAMEWIDTH+2)
#define T_BTSPPLINE 2
#define T_BTSPPWIDTH 75
/* Line 3 */

#define T_VDIMSX 0
#define T_VDIMSLINE 3
#define T_VDIMSWIDTH 76

#define T_FRMCTX (T_VDIMSWIDTH+2)
#define T_FRMCTLINE 3
#define T_FRMCTWIDTH 76

#define T_RESRVX (T_VDIMSWIDTH+2+T_FRMCTWIDTH+2)
#define T_RESRVLINE 3
#define T_RESRVWIDTH 76+75+2



#define VERSION_INFO "v0.3"
#define LARGEST_SPRITE_SIZE 6000
#define COLOR_SKYBLUE 0xBF
#define COLOR_DARKBLUE 25
#define COLOR_BLACK 0
#define COLOR_WHITE 255


/* Keep these headers */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <tice.h>

/* Standard headers (recommended) */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* External library headers */
#include <debug.h>
#include <keypadc.h>
#include <graphx.h>
#include <fileioc.h>
#include <compression.h>


#include "gfx/out/sprites_gfx.h"

/* Put your function prototypes here */
void playvideo(char *vn);
void centerxtext(char* strobj,int y);
void keywait();
void waitanykey();
void printline(char *s);
void printerr(char *s);
void get_video_metadata(char *main_file_name);
char *getnextvideo();
void dispsprite(void *compsprite,int x,int y);
void titlebar(void *compsprite, int x1, int y1, int x2, int y2);
void rect(int x1, int y1, int x2, int y2);

/* Put all your globals here */
uint8_t texty;
char codecname[] = {0,0,0,0,0,0,0,0,0};  //9 bytes, always alias to video.codec
uint8_t* decoder_start_address;
uint8_t bitdepthsize = 7;
char *bitdepthcode[] = {"1bpp b/w","2bpp gray","4bpp gray","4bpp color","4bpp adp","8bpp color","8bpp adp"};
uint8_t *commondata; //Make it large enough to decompress largest sprite object


uint8_t grays[] = {0x00,0x6B,0xB5,0xFF};

struct {
	char *codec;  //always alias to codecname
	char *title;
	char *author;
	int segments;
	int w;
	int h;
	int segframes;
	int bitdepth;
} video;

void main(void) {
	int x,y,i,j;
	kb_key_t k;
	uint8_t *search_pos = NULL;
	uint8_t* fileptr;
	char *varname;
	int timevar;
	int framerate;
	
	
	gfx_Begin(gfx_8bpp);
	gfx_SetDrawBuffer();
	ti_CloseAll();
	
	commondata = malloc(LARGEST_SPRITE_SIZE); 

	//Generate list here.
	varname = getnextvideo();
	if (varname != NULL) {
		while (1) {
			kb_Scan();
			k = kb_Data[1];
			if (k&kb_Mode) break;
			if (k&kb_2nd) { playvideo(varname); getnextvideo(); gfx_SetDefaultPalette(gfx_8bpp);}
			k = kb_Data[7];
			if (k) { if (!getnextvideo()) break;}
			keywait();
			/* Render interface */
			framerate = 30;
			//Background, title, and main box
			gfx_FillScreen(COLOR_SKYBLUE);
			dispsprite(logo_compressed,64,12);
			gfx_SetColor(COLOR_DARKBLUE);
			gfx_Rectangle_NoClip((T_UI_STRTX-1),(T_UI_STRTY-1),(T_UI_WIDTH+1+1+1),(T_UI_DHT*T_NUMLINES));
			//Black bar (fill) boxes and borders
			titlebar(videotitle_compressed,     T_DIALOG(T_VNAME));
			titlebar(videoauthor_compressed,    T_DIALOG(T_VAUTH));
			titlebar(filename_compressed,       T_DIALOG(T_FNAME));
			titlebar(playbacktime_compressed,   T_DIALOG(T_VTIME));
			titlebar(decodertag_compressed,     T_DIALOG(T_DNAME));
			titlebar(bitdepth_compressed,       T_DIALOG(T_BTSPP));
			titlebar(framesize_compressed,      T_DIALOG(T_VDIMS));
			titlebar(framecount_compressed,     T_DIALOG(T_FRMCT));
			titlebar(reserved_compressed,       T_DIALOG(T_RESRV));
			//Fill in other divider lines
			gfx_SetColor(COLOR_DARKBLUE);
			
			gfx_VertLine_NoClip(T_VERTDIV(T_FNAME)); //after filename
			gfx_VertLine_NoClip(T_VERTDIV(T_VTIME)); //after playback time
			gfx_VertLine_NoClip(T_VERTDIV(T_DNAME)); //after decoder name
			gfx_VertLine_NoClip(T_VERTDIV(T_VDIMS)); //after frame size
			gfx_VertLine_NoClip(T_VERTDIV(T_FRMCT)); //after frame count
			
			
//gfx_VertLine_NoClip(T_XPOS(T_VDIMSX-1),T_YPOS(2),T_UI_DHT); //btwn decodername and videodimensions
//gfx_VertLine_NoClip(T_XPOS(T_VTIMEX-1),T_YPOS(2),T_UI_DHT); //btwn videodimensions and videolength
//gfx_VertLine_NoClip(T_XPOS(T_BTSPPX-1),T_YPOS(2),T_UI_DHT); //btwn videolength and bitdepth
			//Fill in text for title and author
			gfx_SetTextScale(1,1);
			texty = 80;
			centerxtext(video.title, T_TEXTY(T_VNAMELINE));
			centerxtext(video.author,T_TEXTY(T_VAUTHLINE));
			//Print filename
			gfx_SetTextXY(T_XPOS(T_FNAMEX+2),T_TEXTY(T_FNAMELINE));
			gfx_PrintString(varname);
			
			//Fill in video dimensions text and sprite object
			gfx_SetTextXY(T_XPOS(T_VDIMSX+2),T_TEXTY(T_VDIMSLINE));
			gfx_PrintUInt(video.w,3);
			dispsprite(x_compressed,T_XPOS(T_VDIMSX+2+24),(T_TEXTY(T_VDIMSLINE)+2));
			gfx_SetTextXY(T_XPOS(T_VDIMSX+2+24+7),T_TEXTY(T_VDIMSLINE));
			gfx_PrintUInt(video.h,3);
			//Fill in video time
			//BASE LOCATION 199 (XPOS(T_VTIMEX+1)
			dispsprite(colon_compressed,T_XPOS(T_VTIMEX+18),T_TEXTY(T_VTIMELINE)+1);
			dispsprite(colon_compressed,T_XPOS(T_VTIMEX+38),T_TEXTY(T_VTIMELINE)+1);
			timevar = video.segframes * video.segments;
			
			gfx_SetTextXY(T_XPOS(T_VTIMEX+42),T_TEXTY(T_VTIMELINE));  //SECONDS
			gfx_PrintUInt((int)(timevar/framerate)%60,2);
			gfx_SetTextXY(T_XPOS(T_VTIMEX+22),T_TEXTY(T_VTIMELINE));  //MINUTES
			gfx_PrintUInt((int)(timevar/(60*framerate))%60,2);
			gfx_SetTextXY(T_XPOS(T_VTIMEX+2),T_TEXTY(T_VTIMELINE));   //HOURS
			gfx_PrintUInt((int)(timevar/(60*60*framerate)),2);
			/*
			gfx_PrintStringXY("Frames per segment: ",5,70);
			gfx_PrintUInt(video.segframes,3);
			gfx_PrintStringXY("Segments total: ",5,80);
			gfx_PrintUInt(video.segments,5);
			*/
			//Fill in number of frames total
			gfx_SetTextXY(T_XPOS(T_FRMCTX+2),T_TEXTY(T_FRMCTLINE));
			gfx_PrintUInt(video.segframes*video.segments,1);
			
			//Fill in decoder
			gfx_SetTextXY(T_XPOS(T_DNAMEX+2),T_TEXTY(T_DNAMELINE));
			gfx_PrintString(video.codec);
			
			//Fill in bit depth
			gfx_SetTextXY(T_XPOS(T_BTSPPX+2),T_TEXTY(T_BTSPPLINE));
			if (video.bitdepth>(bitdepthsize-1)) gfx_PrintString("N/A");
			else gfx_PrintString(bitdepthcode[video.bitdepth]);
			
			//Print version information at the bottom right corner of screen
			gfx_SetTextXY(290,230);
			gfx_PrintString(VERSION_INFO);
			gfx_SwapDraw();
		}
	}
	gfx_End();
	free(commondata);
}

void playvideo(char *vn) {
	char vidname[9];    //max file name length plus null terminator
	char *detname;
	uint8_t **vptr_array, *search_pos, *data_ptr, numfields, status, i;
	uint16_t field_serial, field_size;
	ti_var_t slot;
	int seg_count;
	void (*runDecoder)(uint8_t**,uint8_t*) = (void*) &decoder_start_address;
	int i3,j3,k3;
	uint8_t i1,j1,k1,l1,*decomp_buffer,*decomp_cptr,*draw_ptr,cur_decomp_byte;

	dbg_sprintf(dbgout,"VIDEO ADR 1: %x, AT DATA: %x\n",&video,video.segments);

	get_video_metadata(vn);   //re-retrieve metadata from file
	memcpy(vidname,vn,10);    //create local copy of vn
	
	texty = 150;
	printline("Loading video...");
	
	if (!(vptr_array = malloc((video.segments)*sizeof(uint8_t*)))) {
		printline("You must reencode video w/ larger segments.");
		printerr("Video pointer array malloc failed.");
		return;
	}
	search_pos = NULL;
	seg_count = 0;
	/* Check for all files that may contain video data */
	while (detname = ti_Detect(&search_pos,"8CEVDat")) {
		/* Make sure that the possible video file is opened successfully */
		if (slot = ti_Open(detname,"r")) {
			ti_Seek(7,SEEK_SET,slot);
			//sprintf(dbgout,"Checking vid data name %s using slot %i against main %s\n",vidname,vdat_slot,detname);
			/* Make sure that the video file belongs to the one being played */
			if (!strcmp(vidname,ti_GetDataPtr(slot))) {
				//sprintf(dbgout,"Vid data name %s using slot %i referring to main %s\n",vidname,vdat_slot,detname);
				ti_Seek(9,SEEK_CUR,slot);
				/* Iterate across file getting pointers to data segmenets */
				for (ti_Read(&numfields,1,1,slot);numfields;numfields--) {
					ti_Read(&field_serial,2,1,slot);
					ti_Read(&field_size,2,1,slot);
					//sprintf(dbgout,"Got serial %i from segment %i of size %i at offset %x\n",field_serial,segments_found,field_size,ti_Tell(vdat_slot));
					if (field_serial > video.segments) {
						free(vptr_array);
						printerr("Video file corrupted");
						return;
					}
					//sprintf(dbgout,"Field serial %i at address %x\n",field_serial,ti_GetDataPtr(slot));
					vptr_array[field_serial] = (uint8_t*) ti_GetDataPtr(slot);
					ti_Seek(field_size,SEEK_CUR,slot);
					seg_count++;
				}
			}
			ti_Close(slot);
		}
	}
	if (seg_count != video.segments) {
		gfx_PrintStringXY("Segments expected: ",5,texty);
		gfx_PrintUInt(video.segments,4);
		gfx_PrintString(", found: ");
		gfx_PrintUInt(seg_count,4);
		texty+=10;
		free(vptr_array);
		printerr("Video data corrupted/incomplete.");
		return;
	}
	
	printline("Loading video decoder");
	
	search_pos = NULL;
	status = 0;
	while (detname = ti_Detect(&search_pos,"8CECPck")) {
		if (slot = ti_Open(detname,"r")) {
			ti_Seek(7,SEEK_SET,slot);
			//sprintf(dbgout,"Decoder file %s found, ID %s, expected %s \n",detname,ti_GetDataPtr(slot),video.codec);
			if (!(strcmp(ti_GetDataPtr(slot),video.codec))) {
				ti_Seek(9,SEEK_CUR,slot);
				for(ti_Read(&numfields,1,1,slot);numfields;numfields--) {
					ti_Read(&field_size,2,1,slot);
					ti_Read(&data_ptr,3,1,slot);
					memcpy(data_ptr,ti_GetDataPtr(slot),field_size);
					ti_Seek(field_size,SEEK_CUR,slot);
					if (!status) memcpy(&runDecoder,&data_ptr,sizeof(uint8_t*));
					//sprintf(dbgout,"Decoder object location %x of size %x\n",data_ptr,field_size);
					status = 1;  //Correct decoder found
				}
			}
			ti_Close(slot);
		}
	}
	if (!status) {
		free(vptr_array);
		printerr("Video decoder not found");
		return;
	}
	
	printline("Running video decoder...");
	keywait();  //Prevent video decoder from receiving any unwanted keystrokes
	runDecoder(vptr_array, (uint8_t*) &video);


	// if ((decomp_buffer = malloc(50000)) == NULL) {
		// printerr("Cannot mallc decomp buffer.");
		// free(vptr_array);
		// return;
		
	// }
	// j3 = 0;
	// gfx_SetTextFGColor(0xEF);
	// for (i3 = 0;i3<video.segments;i3++) {
		// sprintf(dbgout,"Outputting segment %i\n",i3);
		// dzx7_Turbo(vptr_array[i3],decomp_buffer);
		// decomp_cptr = decomp_buffer;
		// for (i1 = 0;i1<15;i1++) {
			// draw_ptr = (void*) gfx_vbuffer;
			// for(j1 = 0; j1 < video.h ; j1++) {
				// for (k1 = 0; k1<24 ; k1++) {
					// cur_decomp_byte = *decomp_cptr;
					// decomp_cptr++;
					// for(l1 = 0 ; l1 < 4 ; l1 ++){
						// *draw_ptr = grays[cur_decomp_byte&3];
						// cur_decomp_byte >>= 2;
						// draw_ptr++;
					// }
				// }
				// draw_ptr +=224;
			// }
			// gfx_SetTextXY(0,0);
			// gfx_PrintUInt(j3++,4);
			
			// gfx_SwapDraw();
		// }
	// }
	// gfx_SetTextFGColor(0x00);
	
	// for (i3 = 0;i3<video.segments;i3++) {
		// sprintf(dbgout,"Outputting segment %i\n",i3);
		// dzx7_Turbo(vptr_array[i3],decomp_buffer);
		// decomp_cptr = decomp_buffer;
		// for (i1 = 0;i1<30;i1++) {
			// draw_ptr = (void*) gfx_vbuffer;
			// draw_ptr += 320;
			// for(j1 = 0; j1 < video.h ; j1++) {
				// for (k1 = 0; k1<12 ; k1++) {
					// cur_decomp_byte = *decomp_cptr;
					// decomp_cptr++;
					// for(l1 = 0 ; l1 < 8 ; l1 ++){
						// if (cur_decomp_byte&0x80) {
							// draw_ptr[0   ] = 0xFF;
							// draw_ptr[1   ] = 0xFF;
							// draw_ptr[2   ] = 0xFF;
							// draw_ptr[-320] = 0xFF;
							// draw_ptr[-319] = 0xFF;
							// draw_ptr[-318] = 0xFF;
							// draw_ptr[320 ] = 0xFF;
							// draw_ptr[321 ] = 0xFF;
							// draw_ptr[322 ] = 0xFF;
						// } else {
							// draw_ptr[0   ] = 0x00;
							// draw_ptr[1   ] = 0x00;
							// draw_ptr[2   ] = 0x00;
							// draw_ptr[-320] = 0x00;
							// draw_ptr[-319] = 0x00;
							// draw_ptr[-318] = 0x00;
							// draw_ptr[320 ] = 0x00;
							// draw_ptr[321 ] = 0x00;
							// draw_ptr[322 ] = 0x00;
						// }
						// cur_decomp_byte<<=1;
						// draw_ptr+=3;
					// }
				// }
				// draw_ptr +=(32+(320*2));
			// }
			// gfx_SwapDraw();
		// }
	// }
	
	dbg_sprintf(dbgout,"VIDEO ADR 2: %x, AT DATA: %x\n",&video,video.segments);

	
	free(vptr_array);
	//free(decomp_buffer);
	return;
}


char *nonestring = "[N/A]";
void centerxtext(char* strobj,int y) {
	int w;
	w = gfx_GetStringWidth(strobj);
	if (!w) {
		strobj = nonestring;
		w = gfx_GetStringWidth(strobj);
	}
	gfx_PrintStringXY(strobj,(LCD_WIDTH-w)/2,y);
}

void keywait() {
	while (kb_AnyKey());  //wait until all keys are released
}
void waitanykey() {
	keywait();            //wait until all keys are released
	while (!kb_AnyKey()); //wait until a key has been pressed.
	keywait();
}	

void printline(char *s) {
	if (texty>230) return;
	gfx_PrintStringXY(s,5,texty);
	gfx_SwapDraw();
	gfx_PrintStringXY(s,5,texty);
	texty += 10;
}
void printerr(char *s) {
	uint8_t prev_color;
	prev_color = gfx_SetTextFGColor(0xC0); //red
	printline(s);
	gfx_SetTextFGColor(prev_color);
	waitanykey();
}

//This function assumes that the file is actually the metadata file.
//ti_Detect() shouldn't function otherwise
void get_video_metadata(char *main_file_name) {
	ti_var_t tmpslot;
	
	memset(&video,0,sizeof video);
	
	video.codec = codecname;
	if (tmpslot = ti_Open(main_file_name,"r"))
	{
		ti_Seek(7,SEEK_CUR,tmpslot);           //this is where the header would be
		ti_Read(video.codec,9,1,tmpslot);      //fetch codec namespace
		video.title = ti_GetDataPtr(tmpslot);  //set pointer to title string
		while (ti_GetC(tmpslot));                 //move pointer to end of string
		video.author = ti_GetDataPtr(tmpslot); //set pointer to author string
		while (ti_GetC(tmpslot));                 //move pointer to end of string
		video.segments = video.w = video.h = 0; //prevent upper byte from being undefined.
		ti_Read(&video.segments,2,1,tmpslot);  //Get total number of segments in video
		ti_Read(&video.w,2,1,tmpslot);         //Get frame width
		ti_Read(&video.h,2,1,tmpslot);         //Get frame height
		ti_Read(&video.segframes,1,1,tmpslot); //Get number of frames per segment
		ti_Read(&video.bitdepth,1,1,tmpslot);  //Get video bit depth
	} else {
		video.title = video.author = video.codec = "";
	}
	ti_Close(tmpslot);
	return;
}

char *getnextvideo() {
	static char *video_metadata_header = "8CEVDaH";
	static uint8_t *search_position = NULL;
	char *variable_name;
	
	if (!(variable_name = ti_Detect(&search_position,video_metadata_header))) {
		search_position = NULL;
		variable_name = ti_Detect(&search_position,video_metadata_header);
	}
	get_video_metadata(variable_name);
	return variable_name;
}

void dispsprite(void *compsprite,int x,int y) {
	zx7_Decompress(commondata,compsprite);
	gfx_Sprite_NoClip((gfx_sprite_t*)commondata,x,y);
}

void titlebar(void *compsprite,int x1, int y1, int x2, int y2) {
	gfx_SetColor(COLOR_BLACK);
	gfx_FillRectangle_NoClip(x1,y1,x2-x1+1,y2-y1+1);
	gfx_SetColor(COLOR_DARKBLUE);
	rect(x1-1,y1-1,x2+1,y2+1);
	dispsprite(compsprite,x1+1,y1);
}
void rect(int x1, int y1, int x2, int y2) {
	gfx_Rectangle_NoClip(x1,y1,x2-x1+1,y2-y1+1);
}
