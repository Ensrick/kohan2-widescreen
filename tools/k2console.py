#!/usr/bin/env python3
"""Type into the running game's built-in console without touching the real cursor.

Kohan II's engine binds the backtick key to "Console" and exposes camera commands
(FOV / ZOOM / PITCH / YAW / CAMERA / LOOKAT ...). Everything here goes through
PostMessage to the game's HWND, so it works while the window is parked off-screen
and never steals focus or moves the user's mouse.

    py -3 k2console.py "FOV 20"
    py -3 k2console.py --toggle          # just press backtick
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

u32 = ctypes.WinDLL("user32", use_last_error=True)

WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
VK_OEM_3, VK_RETURN, VK_BACK = 0xC0, 0x0D, 0x08

EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def windows_of(pid):
    out = []

    def cb(h, _):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            out.append(h)
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return out


def main_hwnd(pid):
    ws = windows_of(pid)
    if not ws:
        raise RuntimeError("no window for pid")
    # the game's real window is the one with a client area
    best, bestarea = None, -1
    for h in ws:
        r = wt.RECT()
        u32.GetClientRect(h, ctypes.byref(r))
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > bestarea:
            best, bestarea = h, area
    return best


k32 = ctypes.WinDLL("kernel32", use_last_error=True)


def grab_focus(h):
    """Give the game keyboard focus without moving the mouse or showing anything.

    The engine reads input through DirectInput, which ignores a window that does not
    hold focus - so posted keys are dropped unless we do this first. The window stays
    parked outside the virtual screen, so nothing becomes visible; only focus moves.
    """
    tid_us = k32.GetCurrentThreadId()
    tid_them = u32.GetWindowThreadProcessId(h, None)
    u32.AttachThreadInput(tid_us, tid_them, True)
    u32.SetForegroundWindow(h)
    u32.SetActiveWindow(h)
    u32.SetFocus(h)
    u32.AttachThreadInput(tid_us, tid_them, False)


def lparam(vk, up=False):
    sc = u32.MapVirtualKeyW(vk, 0)
    v = 1 | (sc << 16)
    if up:
        v |= (1 << 30) | (1 << 31)
    return v


def key(h, vk, delay=0.02):
    u32.PostMessageW(h, WM_KEYDOWN, vk, lparam(vk))
    time.sleep(delay)
    u32.PostMessageW(h, WM_KEYUP, vk, lparam(vk, True))
    time.sleep(delay)


def text(h, s, delay=0.015):
    for ch in s:
        u32.PostMessageW(h, WM_CHAR, ord(ch), 1)
        time.sleep(delay)


WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
MK_LBUTTON = 0x0001


def click(h, x, y, settle=0.6):
    """Click at CLIENT coordinates via posted messages.

    Deliberately avoids SetCursorPos/mouse_event: the window is parked off-screen, so
    moving the real cursor would both fail to land on it and disturb the user's desktop.
    """
    grab_focus(h)
    time.sleep(0.15)
    lp = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    u32.PostMessageW(h, WM_MOUSEMOVE, 0, lp)
    time.sleep(0.12)
    u32.PostMessageW(h, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(0.08)
    u32.PostMessageW(h, WM_LBUTTONUP, 0, lp)
    time.sleep(settle)


def screenshot(h):
    """Ask the engine to dump its own framebuffer (root-context 'screenshot' action)."""
    grab_focus(h)
    time.sleep(0.15)
    key(h, 0x2C)
    time.sleep(1.2)


def toggle_console(h):
    key(h, VK_OEM_3)


def run(h, cmd, open_console=True, close=True):
    grab_focus(h)
    time.sleep(0.2)
    if open_console:
        toggle_console(h)
        time.sleep(0.5)
    grab_focus(h)
    text(h, cmd)
    time.sleep(0.2)
    key(h, VK_RETURN)
    time.sleep(0.4)
    if open_console and close:
        grab_focus(h)
        toggle_console(h)     # backtick again closes it
        time.sleep(0.3)


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("\\", 1)[0])
    import k2mem
    pid = k2mem.find_pid()
    h = main_hwnd(pid)
    print(f"pid={pid} hwnd=0x{h:X}")
    if "--toggle" in sys.argv:
        toggle_console(h)
        print("pressed backtick")
    else:
        cmd = sys.argv[1]
        run(h, cmd)
        print(f"sent: {cmd}")
