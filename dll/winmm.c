/*
 * Kohan II: Kings of War - drop-in widescreen / native-aspect fix.
 *
 * Build this as winmm.dll and drop it in the game folder. Windows loads it
 * instead of the system winmm.dll (which k2.exe imports for timeGetTime /
 * timeBeginPeriod / timeEndPeriod - the only 3 functions it uses, forwarded
 * below to the real DLL). At startup this DLL waits for Steam's DRM to decrypt
 * the game code, then patches the projection builder IN MEMORY so the 3D world
 * uses your real screen aspect instead of a hardcoded 4:3 - the terrain widens
 * to full width (Hor+, vertical view unchanged). Nothing on disk is modified;
 * k2.exe is never touched.
 *
 * The patch is identical to the standalone frustumpatch.py / Kohan2Widescreen.ps1:
 * a detour at k2.exe+0x49545D that widens the frustum bounds (R-L) about their
 * midpoint by realAspect/(4:3), guarded to perspective + ~4:3 cameras only
 * (leaves ortho/minimap/shadow alone; idempotent).
 */
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#pragma warning(disable:4273)   /* our exports intentionally shadow winmm's declarations */

/* ---- forward the 3 imported winmm functions to the real system DLL ---------- */
static HMODULE g_real;
typedef DWORD    (WINAPI *pTGT)(void);
typedef MMRESULT (WINAPI *pTBP)(UINT);
static pTGT r_timeGetTime;
static pTBP r_timeBeginPeriod, r_timeEndPeriod;

__declspec(dllexport) DWORD WINAPI timeGetTime(void)            { return r_timeGetTime ? r_timeGetTime() : 0; }
__declspec(dllexport) MMRESULT WINAPI timeBeginPeriod(UINT p)   { return r_timeBeginPeriod ? r_timeBeginPeriod(p) : 0; }
__declspec(dllexport) MMRESULT WINAPI timeEndPeriod(UINT p)     { return r_timeEndPeriod ? r_timeEndPeriod(p) : 0; }

/* ---- the patch ------------------------------------------------------------- */
#define PROJ_RVA   0x49545D
#define RESUME_RVA 0x495465
static const uint8_t DISPLACED[8] = {0x8b,0x02,0x8d,0x8e,0x20,0x03,0x00,0x00}; /* mov eax,[edx]; lea ecx,[esi+0x320] */

static void put32(uint8_t *p, uint32_t v) { p[0]=v; p[1]=v>>8; p[2]=v>>16; p[3]=v>>24; }

/* Build the code-cave at absolute address `cave`; returns total length in `*len`.
   Byte-for-byte identical to the reference patchers (verified). */
static void build_cave(uint8_t *buf, int *len, uintptr_t cave, uintptr_t resume, float a, float b)
{
    uint32_t aAddr = (uint32_t)(cave+0), bAddr = (uint32_t)(cave+4);
    uint32_t ftAddr = (uint32_t)(cave+8), epsAddr = (uint32_t)(cave+12);
    uintptr_t code = cave + 16;
    float ft = 4.0f/3.0f, eps = 0.06f;

    /* header floats */
    memcpy(buf+0, &a, 4); memcpy(buf+4, &b, 4);
    memcpy(buf+8, &ft, 4); memcpy(buf+12, &eps, 4);

    uint8_t *c = buf + 16;   /* code start */
    int p = 0;
    int jne_op, jae_op;      /* offsets (within code) of the two rel32 operands */

    /* ---- partA: guards ---- */
    c[p++]=0x80; c[p++]=0x7f; c[p++]=0x18; c[p++]=0x00;         /* cmp byte [edi+0x18],0 */
    c[p++]=0x0f; c[p++]=0x85; jne_op=p; p+=4;                   /* jne SKIP */
    c[p++]=0xd9; c[p++]=0x47; c[p++]=0x04;                      /* fld [edi+4] */
    c[p++]=0xd8; c[p++]=0x27;                                   /* fsub [edi] */
    c[p++]=0xd9; c[p++]=0x47; c[p++]=0x08;                      /* fld [edi+8] */
    c[p++]=0xd8; c[p++]=0x67; c[p++]=0x0c;                      /* fsub [edi+0xc] */
    c[p++]=0xde; c[p++]=0xf9;                                   /* fdivp */
    c[p++]=0xd9; c[p++]=0xe1;                                   /* fabs */
    c[p++]=0xd8; c[p++]=0x25; put32(c+p,ftAddr); p+=4;          /* fsub [4/3] */
    c[p++]=0xd9; c[p++]=0xe1;                                   /* fabs */
    c[p++]=0xd8; c[p++]=0x1d; put32(c+p,epsAddr); p+=4;         /* fcomp [eps] */
    c[p++]=0xdf; c[p++]=0xe0; c[p++]=0x9e;                      /* fnstsw ax; sahf */
    c[p++]=0x0f; c[p++]=0x83; jae_op=p; p+=4;                   /* jae SKIP */

    /* ---- partB: widen L,R about midpoint ---- */
    c[p++]=0xd9; c[p++]=0x07;                                   /* fld [edi] */
    c[p++]=0xd9; c[p++]=0x47; c[p++]=0x04;                      /* fld [edi+4] */
    c[p++]=0xd9; c[p++]=0xc1; c[p++]=0xd8; c[p++]=0x0d; put32(c+p,aAddr); p+=4;  /* fld st1; fmul [a] */
    c[p++]=0xd9; c[p++]=0xc1; c[p++]=0xd8; c[p++]=0x0d; put32(c+p,bAddr); p+=4;  /* fld st1; fmul [b] */
    c[p++]=0xde; c[p++]=0xc1;                                   /* faddp */
    c[p++]=0xd9; c[p++]=0xc2; c[p++]=0xd8; c[p++]=0x0d; put32(c+p,bAddr); p+=4;  /* fld st2; fmul [b] */
    c[p++]=0xd9; c[p++]=0xc2; c[p++]=0xd8; c[p++]=0x0d; put32(c+p,aAddr); p+=4;  /* fld st2; fmul [a] */
    c[p++]=0xde; c[p++]=0xc1;                                   /* faddp */
    c[p++]=0xd9; c[p++]=0x5f; c[p++]=0x04;                      /* fstp [edi+4] */
    c[p++]=0xd9; c[p++]=0x1f;                                   /* fstp [edi] */
    c[p++]=0xdd; c[p++]=0xd8; c[p++]=0xdd; c[p++]=0xd8;         /* fstp st0; fstp st0 */

    int skip = p;                                              /* SKIP target = start of displaced */
    /* ---- partC: displaced original bytes ---- */
    memcpy(c+p, DISPLACED, 8); p += 8;
    /* jmp back to resume */
    c[p++]=0xe9; put32(c+p, (uint32_t)(resume - (code + p + 4))); p += 4;

    /* backpatch the two forward guards to SKIP (rel is code-relative; base cancels) */
    put32(c+jne_op, (uint32_t)(skip - (jne_op + 4)));
    put32(c+jae_op, (uint32_t)(skip - (jae_op + 4)));

    *len = 16 + p;
}

static double window_aspect(void)
{
    HWND best = NULL; RECT r; LONG barea = 0;
    HWND h = GetTopWindow(NULL);
    /* enumerate top-level windows of our process, pick the largest client area */
    for (h = FindWindowExW(NULL, NULL, NULL, NULL); h; h = FindWindowExW(NULL, h, NULL, NULL)) {
        DWORD pid = 0; GetWindowThreadProcessId(h, &pid);
        if (pid == GetCurrentProcessId() && GetClientRect(h, &r)) {
            LONG area = (r.right) * (LONG)(r.bottom);
            if (area > barea) { barea = area; best = h; }
        }
    }
    if (best && GetClientRect(best, &r) && r.bottom > 0)
        return (double)r.right / (double)r.bottom;
    return 0.0;
}

static void suspend_others(HANDLE *out, int *n)
{
    *n = 0;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snap == INVALID_HANDLE_VALUE) return;
    THREADENTRY32 te; te.dwSize = sizeof(te);
    DWORD me = GetCurrentThreadId(), pid = GetCurrentProcessId();
    if (Thread32First(snap, &te)) do {
        if (te.th32OwnerProcessID == pid && te.th32ThreadID != me) {
            HANDLE t = OpenThread(THREAD_SUSPEND_RESUME, FALSE, te.th32ThreadID);
            if (t) { SuspendThread(t); if (*n < 256) out[(*n)++] = t; }
        }
    } while (Thread32Next(snap, &te));
    CloseHandle(snap);
}

static DWORD WINAPI patch_thread(LPVOID unused)
{
    (void)unused;
    uint8_t *base = (uint8_t *)GetModuleHandleW(NULL);   /* k2.exe image base */
    uint8_t *site = base + PROJ_RVA;

    /* wait for SteamStub to decrypt: the site reads back as the exact instructions,
       and a real game window exists (so we can read the aspect). */
    double aspect = 0.0;
    for (int i = 0; i < 900; i++) {   /* up to ~180 s */
        if (memcmp(site, DISPLACED, 8) == 0) {
            aspect = window_aspect();
            if (aspect > 0.1) break;
        }
        Sleep(200);
    }
    if (memcmp(site, DISPLACED, 8) != 0) return 0;        /* never decrypted / wrong build */
    if (aspect <= 0.1) aspect = 16.0/9.0;
    if (site[0] == 0xE9) return 0;                        /* already patched */

    float f = (float)(aspect / (4.0/3.0));
    float a = (1.0f + f) / 2.0f, b = (1.0f - f) / 2.0f;

    /* allocate the cave (RWX) and build it */
    uint8_t *cave = (uint8_t *)VirtualAlloc((LPVOID)0x20010000, 4096,
                        MEM_COMMIT|MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!cave) cave = (uint8_t *)VirtualAlloc(NULL, 4096,
                        MEM_COMMIT|MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!cave) return 0;
    uint8_t blob[256]; int len = 0;
    build_cave(blob, &len, (uintptr_t)cave, (uintptr_t)(base + RESUME_RVA), a, b);
    memcpy(cave, blob, len);

    /* write the 5-byte jmp (+3 nop) at the site, with other threads frozen so we
       never tear an instruction the projection builder is mid-execution on. */
    uint8_t patch[8];
    patch[0] = 0xE9;
    put32(patch+1, (uint32_t)((cave + 16) - (site + 5)));
    patch[5] = patch[6] = patch[7] = 0x90;

    HANDLE held[256]; int nheld = 0;
    suspend_others(held, &nheld);
    DWORD old;
    if (VirtualProtect(site, 8, PAGE_EXECUTE_READWRITE, &old)) {
        memcpy(site, patch, 8);
        VirtualProtect(site, 8, old, &old);
        FlushInstructionCache(GetCurrentProcess(), site, 8);
    }
    for (int i = 0; i < nheld; i++) { ResumeThread(held[i]); CloseHandle(held[i]); }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        wchar_t sys[MAX_PATH];
        GetSystemDirectoryW(sys, MAX_PATH);
        lstrcatW(sys, L"\\winmm.dll");
        g_real = LoadLibraryW(sys);
        if (g_real) {
            r_timeGetTime     = (pTGT)GetProcAddress(g_real, "timeGetTime");
            r_timeBeginPeriod = (pTBP)GetProcAddress(g_real, "timeBeginPeriod");
            r_timeEndPeriod   = (pTBP)GetProcAddress(g_real, "timeEndPeriod");
        }
        CloseHandle(CreateThread(NULL, 0, patch_thread, NULL, 0, NULL));
    }
    return TRUE;
}
