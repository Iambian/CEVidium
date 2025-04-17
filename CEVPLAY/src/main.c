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
#define T_TEXTXSTART 2
#define T_TEXTYSTART 8

#define CAT(x,y) CAT_(x,y)
#define CAT_(x,y) x ## y

#define T_XPOS(x)  (T_UI_STRTX+x)
#define T_YPOS(ln) (T_UI_STRTY+(T_UI_DHT*ln))
#define T_TPLC(x,y,w) (T_XPOS(x)),(T_YPOS(y)),(T_XPOS(x)+w),(T_YPOS(y)+T_UI_BARHGHT)
#define T_DIALOG(b) T_TPLC(CAT(b,X),CAT(b,LINE),CAT(b,WIDTH))
#define T_TEXTY(ynm) (T_YPOS(ynm)+T_TEXTYSTART)
#define T_VERTDIV(base) (T_XPOS(CAT(base,X))+CAT(base,WIDTH)),(T_YPOS(CAT(base,LINE))),T_UI_DHT
#define T_NGUIE(base) T_XPOS(CAT(base,X)),T_YPOS(CAT(base,LINE)),CAT(base,WIDTH)


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



#define VERSION_INFO "v0.4"
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


typedef void (*content_callback)(void);

/* Put your function prototypes here */
void playvideo(char *vn);
void centerxtext(char* strobj, int y);
void keywait(void);
void waitanykey();
void printline(char *s);
void printerr(char *s);
void get_video_metadata(char *main_file_name);
char *getnextvideo();
void dispsprite(const void *compsprite,int x,int y);


void GUIElem(int x, int y, int w, const void* csprite, content_callback callback);

void GUI_ShowVideoTitle(void);
void GUI_ShowVideoAuthor(void);
void GUI_ShowFilename(void);
void GUI_ShowPlaybackTime(void);
void GUI_ShowDecoder(void);
void GUI_ShowBitDepth(void);
void GUI_ShowFrameSize(void);
void GUI_ShowFrameCount(void);
void GUI_Reserved(void);


/* Put all your globals here */
uint8_t texty;
char codecname[9];     //9 bytes, always alias to video.codec
uint8_t* decoder_start_address;
uint8_t bitdepthsize = 7;
char *bitdepthcode[] = {"1bpp b/w","2bpp gray","4bpp gray","4bpp color","4bpp adp","8bpp color","8bpp adp"};
uint8_t *commondata; //Make it large enough to decompress largest sprite object
char* varname_alias;
char *nonestring = "[N/A]";


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
	char framerate;
} video;

int main(void) {
	//int x,y,i,j;
	kb_key_t k;
	//void *search_pos = NULL;
	//uint8_t* fileptr;
	char *varname;
	//int timevar;
	
	
	gfx_Begin(gfx_8bpp);
	gfx_SetDrawBuffer();
	
	commondata = malloc(LARGEST_SPRITE_SIZE); 

	//Generate list here.
	varname = getnextvideo();
	varname_alias = varname;	//Store to global for callback use
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
			//Background, title, and main box
			gfx_FillScreen(COLOR_SKYBLUE);
			dispsprite((void*)logo_compressed,64,12);
			gfx_SetColor(COLOR_DARKBLUE);
			gfx_Rectangle_NoClip((T_UI_STRTX-1),(T_UI_STRTY-1),(T_UI_WIDTH+1+1+1),(T_UI_DHT*T_NUMLINES)+1);
			//Shows video stats
			GUIElem(T_NGUIE(T_VNAME),videotitle_compressed,&GUI_ShowVideoTitle);
			GUIElem(T_NGUIE(T_VAUTH),videoauthor_compressed,&GUI_ShowVideoAuthor);
			GUIElem(T_NGUIE(T_VTIME),playbacktime_compressed,&GUI_ShowPlaybackTime);
			GUIElem(T_NGUIE(T_FNAME),filename_compressed,&GUI_ShowFilename);
			GUIElem(T_NGUIE(T_DNAME),decodertag_compressed,&GUI_ShowDecoder);
			GUIElem(T_NGUIE(T_BTSPP),bitdepth_compressed,&GUI_ShowBitDepth);
			GUIElem(T_NGUIE(T_VDIMS),framesize_compressed,&GUI_ShowFrameSize);
			GUIElem(T_NGUIE(T_FRMCT),framecount_compressed,&GUI_ShowFrameCount);
			GUIElem(T_NGUIE(T_RESRV),reserved_compressed,&GUI_Reserved);
			
			//Print version information at the bottom right corner of screen
			gfx_SetTextXY(290,230);
			gfx_PrintString(VERSION_INFO);
			gfx_SwapDraw();
		}
	} else {
		gfx_FillScreen(COLOR_SKYBLUE);
		dispsprite(logo_compressed,64,12);
		gfx_SetColor(COLOR_DARKBLUE);
		printline("No files found. File GUI not loaded.");
		printerr("Feed CEVidium files! Files required!");
		waitanykey();
	};
	gfx_End();
	free(commondata);
}

void playvideo(char *vn) {
	char vidname[9];    //max file name length plus null terminator
	char *detname;
	void *search_pos;
	uint8_t **vptr_array, *data_ptr, numfields, status;
	uint16_t field_serial, field_size;
	ti_var_t slot;
	int seg_count;
	void (*runDecoder)(uint8_t**,uint8_t*) = (void*) &decoder_start_address;
	//int i3,j3,k3;
	//uint8_t i1,j1,k1,l1,*decomp_buffer,*decomp_cptr,*draw_ptr,cur_decomp_byte;

	dbg_sprintf(dbgout,"VIDEO ADR 1: %x, AT DATA: %x\n",&video,video.segments);

	get_video_metadata(vn);   //re-retrieve metadata from file
	memcpy(vidname,vn,9);    //create local copy of vn
	
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
	while ((detname = ti_Detect(&search_pos,"8CEVDat"))) {
		/* Make sure that the possible video file is opened successfully */
		if ((slot = ti_Open(detname,"r"))) {
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
	while ((detname = ti_Detect(&search_pos,"8CECPck"))) {
		if ((slot = ti_Open(detname,"r"))) {
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
	
	dbg_sprintf(dbgout,"VIDEO ADR 2: %x, AT DATA: %x\n",&video,video.segments);

	free(vptr_array);
	return;
}


void centerxtext(char* strobj,int y) {
	int w;
	w = gfx_GetStringWidth(strobj);
	if (!w) {
		strobj = nonestring;
		w = gfx_GetStringWidth(strobj);
	}
	gfx_PrintStringXY(strobj,(LCD_WIDTH-w)/2,y);
}

void keywait(void) {
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
	if ((tmpslot = ti_Open(main_file_name,"r")))
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
		//ti_Read(&video.framerate,1,1,tmpslot); //Get video frame rate
		video.framerate = 30;
	} else {
		video.title = video.author = video.codec = "";
	}
	ti_Close(tmpslot);
	return;
}

char *getnextvideo() {
	static char *video_metadata_header = "8CEVDaH";
	static void *search_position = NULL;
	char *variable_name;
	
	if (!(variable_name = ti_Detect(&search_position,video_metadata_header))) {
		search_position = NULL;
		variable_name = ti_Detect(&search_position,video_metadata_header);
	}
	get_video_metadata(variable_name);
	return variable_name;
}

void dispsprite(const void *compsprite,int x,int y) {
	zx7_Decompress(commondata,compsprite);
	gfx_Sprite_NoClip((gfx_sprite_t*)commondata,x,y);
}

void GUIElem(int x, int y, int w, const void* csprite, content_callback callback) {
	//Draw outlines
	gfx_SetColor(COLOR_DARKBLUE);
	gfx_Rectangle_NoClip(x-1,y-1,w+3,(T_UI_DHT+1));
	gfx_HorizLine(x,y+(T_UI_BARHGHT+1),w+1);
	//Draw titlebar background
	gfx_SetColor(COLOR_BLACK);
	gfx_FillRectangle_NoClip(x,y,w+1,(T_UI_BARHGHT+1));
	//Draw titlebar
	dispsprite(csprite,x+2,y);
	//Prep to call the routines that renders UI element contents
	gfx_SetTextXY(x+T_TEXTXSTART,y+T_TEXTYSTART);
	callback();
}

void GUI_ShowFilename(void) {
	gfx_PrintString(varname_alias);
}

void GUI_ShowVideoTitle(void) {
	centerxtext(video.title,gfx_GetTextY());
}
void GUI_ShowVideoAuthor(void) {
	centerxtext(video.author,gfx_GetTextY());
}
void GUI_PrintSpacedChar(char c) {
	int y = gfx_GetTextY();
	gfx_SetTextXY(gfx_GetTextX()+1,y);
	gfx_PrintChar(c);
	gfx_SetTextXY(gfx_GetTextX()+1,y);
}
void GUI_ShowPlaybackTime(void) {
	int time = ( video.segframes * video.segments) / video.framerate;
	
	gfx_PrintUInt(time / 3600   , 2);		//hours
	GUI_PrintSpacedChar(':');
	gfx_PrintUInt(time / 60 % 60, 2);		//minutes
	GUI_PrintSpacedChar(':');
	gfx_PrintUInt(time      % 60, 2);		//seconds
}
void GUI_ShowDecoder(void) {
	gfx_PrintString(video.codec);
}
void GUI_ShowBitDepth(void) {
	char *s;
	if (video.bitdepth > bitdepthsize-1) 
			s = nonestring;
	else 	s = bitdepthcode[video.bitdepth];
	gfx_PrintString(s);
}
void GUI_ShowFrameSize(void) {
	gfx_PrintUInt(video.w,3);
	GUI_PrintSpacedChar('x');
	gfx_PrintUInt(video.h,3);
}
void GUI_ShowFrameCount(void) {
	gfx_PrintUInt(video.segframes*video.segments,1);
}
void GUI_Reserved(void) {
	return;
}

