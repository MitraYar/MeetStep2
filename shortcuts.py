import sys

DEFAULT_BINDINGS=[
    ['pause','VK_20',0,1,'note_on',0],['options','CTRL+VK_BF',0,1,'note_on',0],
    ['left','VK_25',0,1,'note_on',0],['right','VK_27',0,1,'note_on',0],
    ['undo','VK_5A',0,1,'note_on',0],['redo','VK_58',0,1,'note_on',0],
    ['up_page','VK_26',0,1,'note_on',0],['down_page','VK_28',0,1,'note_on',0],
    ['grid_left','VK_4A',0,1,'note_on',0],['grid_down','VK_4B',0,1,'note_on',0],
    ['grid_right','VK_4C',0,1,'note_on',0],['grid_up','VK_49',0,1,'note_on',0],
    ['prev_page','VK_48',0,1,'note_on',0],['next_page','VK_BA',0,1,'note_on',0],
    ['group_left','VK_59',0,1,'note_on',0],['group_right','VK_50',0,1,'note_on',0],
    ['audition','VK_BE',0,1,'note_on',0],['scope_note','VK_41',0,1,'note_on',0],
    ['scope_channel','VK_53',0,1,'note_on',0],['repeat_pages','VK_44',0,1,'note_on',0],
    ['gate_view','VK_47',0,1,'note_on',0],
    ['velocity','',1,1,'control_change',64],['length','',1,1,'control_change',65],
    ['tempo','',1,1,'control_change',67]]

def key_id(event,platform=None):
    code=event.keycode
    if (platform or sys.platform)!='win32':
        # X11 physical keycodes, for development smoke tests only.
        code={65:0x20,61:0xBF,52:0x5A,53:0x58,113:0x25,114:0x27,111:0x26,116:0x28,
              44:0x4A,45:0x4B,46:0x4C,31:0x49,43:0x48,47:0xBA,29:0x59,33:0x50,
              60:0xBE,38:0x41,39:0x53,40:0x44,42:0x47,
              **{10+i:0x31+i for i in range(9)},19:0x30,**{67+i:0x70+i for i in range(7)},64:0x12}.get(code,code)
    # Windows Tk uses 0x20000 for Alt; X11 uses Mod1 (0x8).
    alt=bool(event.state & (0x20000 if (platform or sys.platform)=='win32' else 8))
    return ('CTRL+' if event.state&4 else '')+('ALT+' if alt else '')+('SHIFT+' if event.state&1 else '')+f'VK_{code:02X}'

def migrate_bindings(config):
    if config.get('version',0)>=3:return config.get('bindings',DEFAULT_BINDINGS)
    result=[row.copy() for row in DEFAULT_BINDINGS]
    legacy={'space':'VK_20','Left':'VK_25','Right':'VK_27','z':'VK_5A','x':'VK_58'}
    for row in config.get('bindings',[]):
        action,key,source,ch,kind,num=row
        if action=='play' and (source,ch,kind,num)==(1,10,'note_on',52):continue
        if action=='pause' and key=='space':continue
        if action in ('velocity','length','tempo') and source==1 and ch==6 and kind=='control_change' and num in (48,49,55):continue
        if config.get('version',0)<2:key=legacy.get(key, f'VK_{ord(key.upper()):02X}' if len(key)==1 and key.isascii() else '')
        updated=[action,key,source,ch,kind,num]
        for i,default in enumerate(result):
            if default[0]==action:result[i]=updated;break
        else:result.append(updated)
    return result
