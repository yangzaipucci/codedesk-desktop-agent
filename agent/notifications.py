"""Windows system tray balloon: OS acceptance recorded separately from visibility."""
import asyncio
import os
import queue
import threading
import time
import uuid


def _request(title,body):
    if os.name!='nt':
        return {'accepted':False,'reason':'Windows system notification unavailable on this platform'}
    result=queue.Queue(maxsize=1)
    def worker():
        window=None;class_name='CodeDeskNotification'+uuid.uuid4().hex
        try:
            import win32api,win32con,win32gui
            instance=win32api.GetModuleHandle(None)
            wc=win32gui.WNDCLASS();wc.hInstance=instance;wc.lpszClassName=class_name
            wc.lpfnWndProc=win32gui.DefWindowProc
            win32gui.RegisterClass(wc)
            window=win32gui.CreateWindow(class_name,'CodeDesk',0,0,0,0,0,0,0,instance,None)
            icon=win32gui.LoadIcon(0,win32con.IDI_APPLICATION)
            flags=win32gui.NIF_ICON|win32gui.NIF_TIP|win32gui.NIF_MESSAGE
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD,(window,0,flags,win32con.WM_USER+20,icon,'CodeDesk'))
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY,(window,0,win32gui.NIF_INFO,win32con.WM_USER+20,icon,'CodeDesk',body[:255],8000,title[:63],win32gui.NIIF_INFO))
            result.put({'accepted':True,'backend':'Windows Shell_NotifyIcon','visibility':'controlled by Windows notification/focus settings'})
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                win32gui.PumpWaitingMessages();time.sleep(.05)
        except Exception as error:
            if result.empty():result.put({'accepted':False,'reason':type(error).__name__})
        finally:
            if window:
                try:
                    win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE,(window,0));win32gui.DestroyWindow(window);win32gui.UnregisterClass(class_name,None)
                except Exception:
                    pass  # Best effort cleanup after the OS result was recorded.
    threading.Thread(target=worker,name='CodeDesk notification',daemon=True).start()
    try:return result.get(timeout=5)
    except queue.Empty:return {'accepted':False,'reason':'System notification request timed out'}


async def notify_completion(name):
    return await asyncio.to_thread(_request,'CodeDesk · 任务完成',str(name))
