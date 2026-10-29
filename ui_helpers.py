import tkinter as tk
from tkinter import ttk

class Tooltip:
    def __init__(self,widget,text):
        self.widget=widget;self.text=text;self.window=None;self.timer=None
        widget.bind('<Enter>',self.enter,add='+');widget.bind('<Leave>',self.hide,add='+');widget.bind('<ButtonPress>',self.hide,add='+');widget.bind('<Destroy>',self.hide,add='+')
    def enter(self,event=None):self.timer=self.widget.after(450,self.show)
    def show(self):
        self.timer=None
        if not self.widget.winfo_exists():return
        self.window=tk.Toplevel(self.widget);self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f'+{self.widget.winfo_rootx()+12}+{self.widget.winfo_rooty()+self.widget.winfo_height()+6}')
        tk.Label(self.window,text=self.text,bg='#fff4c8',fg='#20242b',padx=8,pady=5,wraplength=360,justify='left').pack()
    def hide(self,event=None):
        if self.timer:self.widget.after_cancel(self.timer);self.timer=None
        if self.window:self.window.destroy();self.window=None

def theme(root,name):
    style=ttk.Style(root)
    if name=='Legacy light':
        style.theme_use('vista' if 'vista' in style.theme_names() else 'default')
        root.configure(bg='#d9d9d9');return
    style.theme_use('clam')
    dark=name=='Dark';bg='#18212e' if dark else '#f2f5f9';fg='#e6edf5' if dark else '#213047';field='#243247' if dark else '#ffffff'
    root.configure(bg=bg)
    style.configure('.',background=bg,foreground=fg,font=('Segoe UI',9),fieldbackground=field)
    style.configure('TButton',padding=(9,5));style.map('TButton',background=[('active','#34536b' if dark else '#d6e6f2')])
    style.configure('TNotebook.Tab',padding=(12,7));style.map('TNotebook.Tab',background=[('selected',field)])
    style.configure('Treeview',background=field,fieldbackground=field,foreground=fg,rowheight=26)
    style.map('Treeview',background=[('selected','#3b7287')],foreground=[('selected','#ffffff')])
    style.map('TCombobox',fieldbackground=[('readonly',field)],foreground=[('readonly',fg)])
    root.option_add('*TCombobox*Listbox.background',field);root.option_add('*TCombobox*Listbox.foreground',fg)

def tooltips(widget):
    for child in widget.winfo_children():
        if isinstance(child,(ttk.Button,ttk.Checkbutton)) and not getattr(child,'_hint',None):
            text=child.cget('text')
            if text:child._hint=Tooltip(child,text)
        tooltips(child)
def place_dialog(window,parent,width,height):
    """Center inside the current monitor work area, including Windows taskbar."""
    import sys
    left=top=0;right=window.winfo_screenwidth();bottom=window.winfo_screenheight()
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD)]
        api=ctypes.windll.user32;api.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];api.MonitorFromWindow.restype=wintypes.HANDLE
        api.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
        info=MonitorInfo();info.cbSize=ctypes.sizeof(info)
        if api.GetMonitorInfoW(api.MonitorFromWindow(parent.winfo_id(),2),ctypes.byref(info)):
            left,top,right,bottom=info.rcWork.left,info.rcWork.top,info.rcWork.right,info.rcWork.bottom
    width=min(width,right-left-40);height=min(height,bottom-top-70)
    x=max(left+10,min(right-width-10,parent.winfo_rootx()+(parent.winfo_width()-width)//2))
    y=max(top+30,min(bottom-height-40,parent.winfo_rooty()+(parent.winfo_height()-height)//2))
    window.geometry(f'{width}x{height}{x:+d}{y:+d}');window.minsize(min(960,width),min(620,height))
