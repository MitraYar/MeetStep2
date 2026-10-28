"""Window-local Windows XBUTTON support (Tk does not expose it consistently)."""
import sys

class SideButtons:
    def __init__(self,canvas,start,move,end):
        self.canvas=canvas;self.active=None;self.old=None
        if sys.platform!='win32':
            for button,attribute in ((8,'velocity'),(9,'length')):
                canvas.bind(f'<Button-{button}>',lambda e,a=attribute:start(e.x,e.y,a))
                canvas.bind(f'<B{button}-Motion>',lambda e:move(e.x,e.y))
                canvas.bind(f'<ButtonRelease-{button}>',lambda e:end())
            return
        import ctypes
        from ctypes import wintypes
        self.ctypes=ctypes;self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.hwnd=canvas.winfo_id();pointer=ctypes.c_ssize_t
        self.user.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,pointer]
        self.user.SetWindowLongPtrW.restype=pointer
        self.user.CallWindowProcW.argtypes=[pointer,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.user.CallWindowProcW.restype=pointer
        self.user.SetCapture.argtypes=[wintypes.HWND];self.user.SetCapture.restype=wintypes.HWND
        self.user.ReleaseCapture.argtypes=[];self.user.ReleaseCapture.restype=wintypes.BOOL
        procedure=ctypes.WINFUNCTYPE(pointer,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
        def dispatch(hwnd,message,wparam,lparam):
            try:
                x=ctypes.c_short(lparam&65535).value;y=ctypes.c_short((lparam>>16)&65535).value
                if message==0x020B:
                    button=(wparam>>16)&65535
                    if button in (1,2):
                        self.active=button;self.user.SetCapture(hwnd);start(x,y,'velocity' if button==1 else 'length');return 1
                if message==0x0200 and self.active:move(x,y)
                if message==0x020C and self.active:
                    self.active=None;self.user.ReleaseCapture();end();return 1
                if message==0x0215 and self.active:self.active=None;end()
            except Exception:
                canvas._root().report_callback_exception(*sys.exc_info())
            return self.user.CallWindowProcW(self.old,hwnd,message,wparam,lparam)
        self.callback=procedure(dispatch)
        ctypes.set_last_error(0)
        self.old=self.user.SetWindowLongPtrW(self.hwnd,-4,ctypes.cast(self.callback,ctypes.c_void_p).value)
        if not self.old:raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.old:
            self.user.SetWindowLongPtrW(self.hwnd,-4,self.old);self.old=None
