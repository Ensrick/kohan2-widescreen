/*
 * Kohan II: Kings of War - drop-in widescreen / native-aspect fix.
 *
 * Build as avifil32.dll and drop it in the game folder. k2.exe imports 9 functions
 * from the system avifil32.dll; this proxy forwards them to the real DLL (naked
 * jump thunks - convention-agnostic) and, from DllMain, patches the projection
 * builder in memory so the 3D world uses your real screen aspect (Hor+; nothing on
 * disk is modified). k2.exe is Steam-DRM encrypted, so the patch is applied at
 * runtime once the code decrypts.
 *
 * Why avifil32 and not winmm: Steam's overlay (GameOverlayRenderer.dll) statically
 * imports winmm and loads it from System32 before k2's import binds, so an app-folder
 * winmm.dll is bypassed. The overlay does NOT import avifil32, so our copy wins.
 *
 * The patch itself is byte-for-byte identical to frustumpatch.py / Kohan2Widescreen.ps1:
 * a detour at k2.exe+0x49545D widening the frustum bounds (R-L) to the real aspect,
 * guarded to perspective + ~4:3 cameras (idempotent; leaves ortho/minimap/shadow).
 */
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#include <stdarg.h>

/* ---- forward the 9 imported avifil32 functions to the real system DLL ------- */
static HMODULE g_real;
static FARPROC r_AVIStreamSetFormat, r_AVIMakeCompressedStream, r_AVIFileExit,
               r_AVIFileInit, r_AVIFileOpenW, r_AVIStreamWrite, r_AVIFileRelease,
               r_AVIStreamRelease, r_AVIFileCreateStreamW;

/* naked tail-jumps: preserve the caller's stack/args regardless of calling
   convention, and the real function returns straight to k2's caller. */
__declspec(naked) void AVIStreamSetFormat(void)      { __asm { jmp dword ptr [r_AVIStreamSetFormat] } }
__declspec(naked) void AVIMakeCompressedStream(void) { __asm { jmp dword ptr [r_AVIMakeCompressedStream] } }
__declspec(naked) void AVIFileExit(void)             { __asm { jmp dword ptr [r_AVIFileExit] } }
__declspec(naked) void AVIFileInit(void)             { __asm { jmp dword ptr [r_AVIFileInit] } }
__declspec(naked) void AVIFileOpenW(void)            { __asm { jmp dword ptr [r_AVIFileOpenW] } }
__declspec(naked) void AVIStreamWrite(void)          { __asm { jmp dword ptr [r_AVIStreamWrite] } }
__declspec(naked) void AVIFileRelease(void)          { __asm { jmp dword ptr [r_AVIFileRelease] } }
__declspec(naked) void AVIStreamRelease(void)        { __asm { jmp dword ptr [r_AVIStreamRelease] } }
__declspec(naked) void AVIFileCreateStreamW(void)    { __asm { jmp dword ptr [r_AVIFileCreateStreamW] } }

/* ---- diagnostic log (to %TEMP%\k2ws_dll.log) ------------------------------- */
static void wslog(const char *fmt, ...)
{
    wchar_t dir[MAX_PATH]; DWORD n = GetTempPathW(MAX_PATH, dir);
    if (!n) return;
    lstrcatW(dir, L"k2ws_dll.log");
    HANDLE f = CreateFileW(dir, FILE_APPEND_DATA, FILE_SHARE_READ|FILE_SHARE_WRITE,
                           NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) return;
    SetFilePointer(f, 0, NULL, FILE_END);
    char buf[512]; va_list ap; va_start(ap, fmt);
    int len = wvsprintfA(buf, fmt, ap); va_end(ap);
    if (len > 0 && len < (int)sizeof(buf)-2) { buf[len++]='\r'; buf[len++]='\n'; }
    DWORD wrote; WriteFile(f, buf, len, &wrote, NULL);
    CloseHandle(f);
}

/* ---- the patch ------------------------------------------------------------- */
#define PROJ_RVA   0x49545D
#define RESUME_RVA 0x495465
static const uint8_t DISPLACED[8] = {0x8b,0x02,0x8d,0x8e,0x20,0x03,0x00,0x00};

static void put32(uint8_t *p, uint32_t v) { p[0]=v; p[1]=v>>8; p[2]=v>>16; p[3]=v>>24; }

static void build_cave(uint8_t *buf, int *len, uintptr_t cave, uintptr_t resume, float a, float b)
{
    uint32_t aAddr=(uint32_t)(cave+0), bAddr=(uint32_t)(cave+4), ftAddr=(uint32_t)(cave+8), epsAddr=(uint32_t)(cave+12);
    uintptr_t code = cave + 16;
    float ft = 4.0f/3.0f, eps = 0.06f;
    memcpy(buf+0,&a,4); memcpy(buf+4,&b,4); memcpy(buf+8,&ft,4); memcpy(buf+12,&eps,4);
    uint8_t *c = buf + 16; int p = 0, jne_op, jae_op;

    c[p++]=0x80;c[p++]=0x7f;c[p++]=0x18;c[p++]=0x00;        /* cmp byte [edi+0x18],0 */
    c[p++]=0x0f;c[p++]=0x85; jne_op=p; p+=4;                /* jne SKIP */
    c[p++]=0xd9;c[p++]=0x47;c[p++]=0x04;                    /* fld [edi+4] */
    c[p++]=0xd8;c[p++]=0x27;                                /* fsub [edi] */
    c[p++]=0xd9;c[p++]=0x47;c[p++]=0x08;                    /* fld [edi+8] */
    c[p++]=0xd8;c[p++]=0x67;c[p++]=0x0c;                    /* fsub [edi+0xc] */
    c[p++]=0xde;c[p++]=0xf9;                                /* fdivp */
    c[p++]=0xd9;c[p++]=0xe1;                                /* fabs */
    c[p++]=0xd8;c[p++]=0x25; put32(c+p,ftAddr); p+=4;       /* fsub [4/3] */
    c[p++]=0xd9;c[p++]=0xe1;                                /* fabs */
    c[p++]=0xd8;c[p++]=0x1d; put32(c+p,epsAddr); p+=4;      /* fcomp [eps] */
    c[p++]=0xdf;c[p++]=0xe0;c[p++]=0x9e;                    /* fnstsw ax; sahf */
    c[p++]=0x0f;c[p++]=0x83; jae_op=p; p+=4;                /* jae SKIP */

    c[p++]=0xd9;c[p++]=0x07;                                /* fld [edi] */
    c[p++]=0xd9;c[p++]=0x47;c[p++]=0x04;                    /* fld [edi+4] */
    c[p++]=0xd9;c[p++]=0xc1;c[p++]=0xd8;c[p++]=0x0d; put32(c+p,aAddr); p+=4;
    c[p++]=0xd9;c[p++]=0xc1;c[p++]=0xd8;c[p++]=0x0d; put32(c+p,bAddr); p+=4;
    c[p++]=0xde;c[p++]=0xc1;
    c[p++]=0xd9;c[p++]=0xc2;c[p++]=0xd8;c[p++]=0x0d; put32(c+p,bAddr); p+=4;
    c[p++]=0xd9;c[p++]=0xc2;c[p++]=0xd8;c[p++]=0x0d; put32(c+p,aAddr); p+=4;
    c[p++]=0xde;c[p++]=0xc1;
    c[p++]=0xd9;c[p++]=0x5f;c[p++]=0x04;                    /* fstp [edi+4] */
    c[p++]=0xd9;c[p++]=0x1f;                                /* fstp [edi] */
    c[p++]=0xdd;c[p++]=0xd8;c[p++]=0xdd;c[p++]=0xd8;        /* fstp st0; fstp st0 */

    int skip = p;
    memcpy(c+p, DISPLACED, 8); p += 8;
    c[p++]=0xe9; put32(c+p,(uint32_t)(resume-(code+p+4))); p+=4;

    put32(c+jne_op,(uint32_t)(skip-(jne_op+4)));
    put32(c+jae_op,(uint32_t)(skip-(jae_op+4)));
    *len = 16 + p;
}

static double window_aspect(void)
{
    HWND best=NULL; RECT r; LONG barea=0;
    for (HWND h=FindWindowExW(NULL,NULL,NULL,NULL); h; h=FindWindowExW(NULL,h,NULL,NULL)) {
        DWORD pid=0; GetWindowThreadProcessId(h,&pid);
        if (pid==GetCurrentProcessId() && GetClientRect(h,&r)) {
            LONG area=r.right*(LONG)r.bottom;
            if (area>barea){barea=area;best=h;}
        }
    }
    if (best && GetClientRect(best,&r) && r.bottom>0) return (double)r.right/(double)r.bottom;
    return 0.0;
}

static void suspend_others(HANDLE *out, int *n)
{
    *n=0;
    HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
    if (snap==INVALID_HANDLE_VALUE) return;
    THREADENTRY32 te; te.dwSize=sizeof(te);
    DWORD me=GetCurrentThreadId(), pid=GetCurrentProcessId();
    if (Thread32First(snap,&te)) do {
        if (te.th32OwnerProcessID==pid && te.th32ThreadID!=me) {
            HANDLE t=OpenThread(THREAD_SUSPEND_RESUME,FALSE,te.th32ThreadID);
            if (t){SuspendThread(t); if(*n<256) out[(*n)++]=t;}
        }
    } while (Thread32Next(snap,&te));
    CloseHandle(snap);
}

static DWORD WINAPI patch_thread(LPVOID u)
{
    (void)u;
    uint8_t *base=(uint8_t*)GetModuleHandleW(NULL);
    uint8_t *site=base+PROJ_RVA;
    wslog("patch_thread start; base=%p site=%p", base, site);
    double aspect=0.0; int decrypted=0;
    for (int i=0;i<900;i++){
        int ok=0; __try{ ok=(memcmp(site,DISPLACED,8)==0); }__except(1){ ok=0; }
        if (ok){ if(!decrypted){decrypted=1;wslog("decrypted at iter %d",i);} aspect=window_aspect(); if(aspect>0.1){wslog("aspect=%d/1000",(int)(aspect*1000));break;} }
        Sleep(200);
    }
    if(!decrypted){wslog("ABORT: never decrypted");return 0;}
    if(aspect<=0.1){aspect=16.0/9.0;wslog("no window; assume 16:9");}
    if(site[0]==0xE9){wslog("already patched");return 0;}
    float f=(float)(aspect/(4.0/3.0)), a=(1.0f+f)/2.0f, b=(1.0f-f)/2.0f;
    uint8_t *cave=(uint8_t*)VirtualAlloc((LPVOID)0x20010000,4096,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE);
    if(!cave) cave=(uint8_t*)VirtualAlloc(NULL,4096,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE);
    if(!cave){wslog("ABORT: VirtualAlloc failed");return 0;}
    uint8_t blob[256]; int len=0;
    build_cave(blob,&len,(uintptr_t)cave,(uintptr_t)(base+RESUME_RVA),a,b);
    memcpy(cave,blob,len);
    uint8_t patch[8]; patch[0]=0xE9; put32(patch+1,(uint32_t)((cave+16)-(site+5))); patch[5]=patch[6]=patch[7]=0x90;
    HANDLE held[256]; int nheld=0; suspend_others(held,&nheld);
    DWORD old;
    if(VirtualProtect(site,8,PAGE_EXECUTE_READWRITE,&old)){
        memcpy(site,patch,8);
        VirtualProtect(site,8,old,&old);
        FlushInstructionCache(GetCurrentProcess(),site,8);
    }
    for(int i=0;i<nheld;i++){ResumeThread(held[i]);CloseHandle(held[i]);}
    wslog("PATCHED: cave=%p f=%d/1000 froze %d threads", cave,(int)(f*1000),nheld);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID res)
{
    (void)res;
    if(reason==DLL_PROCESS_ATTACH){
        DisableThreadLibraryCalls(h);
        wslog("=== DllMain attach (our avifil32.dll loaded) ===");
        wchar_t sys[MAX_PATH]; GetSystemDirectoryW(sys,MAX_PATH); lstrcatW(sys,L"\\avifil32.dll");
        g_real=LoadLibraryW(sys);
        if(g_real){
            r_AVIStreamSetFormat      = GetProcAddress(g_real,"AVIStreamSetFormat");
            r_AVIMakeCompressedStream = GetProcAddress(g_real,"AVIMakeCompressedStream");
            r_AVIFileExit             = GetProcAddress(g_real,"AVIFileExit");
            r_AVIFileInit             = GetProcAddress(g_real,"AVIFileInit");
            r_AVIFileOpenW            = GetProcAddress(g_real,"AVIFileOpenW");
            r_AVIStreamWrite          = GetProcAddress(g_real,"AVIStreamWrite");
            r_AVIFileRelease          = GetProcAddress(g_real,"AVIFileRelease");
            r_AVIStreamRelease        = GetProcAddress(g_real,"AVIStreamRelease");
            r_AVIFileCreateStreamW    = GetProcAddress(g_real,"AVIFileCreateStreamW");
        }
        wslog("real avifil32=%p", g_real);
        HANDLE t=CreateThread(NULL,0,patch_thread,NULL,0,NULL);
        wslog("patch thread=%p", t);
        if(t) CloseHandle(t);
    }
    return TRUE;
}
