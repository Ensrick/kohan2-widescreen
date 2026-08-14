# Mute (or unmute) every Windows audio session belonging to k2.exe, per-application,
# without touching global volume or killing the process. Used to keep headless RE runs
# silent. Uses Core Audio COM (ISimpleAudioVolume).
#   .\mute_k2.ps1            # mute all k2 sessions
#   .\mute_k2.ps1 -Unmute

param([switch]$Unmute)

$ErrorActionPreference = 'Stop'

if (-not ('K2Audio.Ctl' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace K2Audio {
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator { }
    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceEnumerator { int EnumAudioEndpoints(int f,int s,out IntPtr d); int GetDefaultAudioEndpoint(int flow,int role,out IMMDevice ep); }
    [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDevice { int Activate(ref Guid iid,int ctx,IntPtr p,[MarshalAs(UnmanagedType.IUnknown)] out object o); }
    [Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionManager2 {
        int GetAudioSessionControl(IntPtr id,int flags,out IntPtr ctl);
        int GetSimpleAudioVolume(IntPtr id,int flags,out IntPtr vol);
        int GetSessionEnumerator(out IAudioSessionEnumerator e);
    }
    [Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionEnumerator { int GetCount(out int c); int GetSession(int i,out IntPtr ctl); }
    [Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionControl2 {
        int GetState(out int s); int GetDisplayName(out IntPtr n); int SetDisplayName(string n,ref Guid c);
        int GetIconPath(out IntPtr p); int SetIconPath(string p,ref Guid c);
        int GetGroupingParam(out Guid g); int SetGroupingParam(ref Guid g,ref Guid c);
        int RegisterAudioSessionNotification(IntPtr n); int UnregisterAudioSessionNotification(IntPtr n);
        int GetSessionIdentifier(out IntPtr id); int GetSessionInstanceIdentifier(out IntPtr id);
        int GetProcessId(out int pid); int IsSystemSoundsSession(); int SetDuckingPreference(bool o);
    }
    [Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ISimpleAudioVolume { int SetMasterVolume(float l,ref Guid c); int GetMasterVolume(out float l); int SetMute(bool m,ref Guid c); int GetMute(out bool m); }

    public class Ctl {
        static Guid IID_ASM2 = new Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F");
        public static int SetMuteForProcess(string procName, bool mute) {
            var en = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
            IMMDevice dev; en.GetDefaultAudioEndpoint(0,1,out dev); // eRender, eMultimedia
            object o; dev.Activate(ref IID_ASM2,1,IntPtr.Zero,out o);
            var mgr=(IAudioSessionManager2)o;
            IAudioSessionEnumerator se; mgr.GetSessionEnumerator(out se);
            int n; se.GetCount(out n); int affected=0;
            var pids=new System.Collections.Generic.HashSet<int>();
            foreach (var p in System.Diagnostics.Process.GetProcessesByName(procName)) pids.Add(p.Id);
            for(int i=0;i<n;i++){
                IntPtr ptr; se.GetSession(i,out ptr);
                var c2=(IAudioSessionControl2)Marshal.GetObjectForIUnknown(ptr);
                int pid; c2.GetProcessId(out pid);
                if(pids.Contains(pid)){
                    var vol=(ISimpleAudioVolume)c2; Guid g=Guid.Empty; vol.SetMute(mute,ref g); affected++;
                }
            }
            return affected;
        }
    }
}
'@
}

$n = [K2Audio.Ctl]::SetMuteForProcess('k2', (-not $Unmute))
"$(if($Unmute){'unmuted'}else{'muted'}) $n k2 audio session(s)"
