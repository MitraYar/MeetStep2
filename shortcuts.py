import sys

DEFAULT_BINDINGS=[
    ['pause','VK_20',0,1,'note_on',0],['options','CTRL+VK_BF',0,1,'note_on',0],
    ['left','VK_25',0,1,'note_on',0],['right','VK_27',0,1,'note_on',0],
    ['undo','VK_5A',0,1,'note_on',0],['redo','VK_58',0,1,'note_on',0],
    ['velocity','',1,6,'control_change',48],['length','',1,6,'control_change',49],
    ['tempo','',1,6,'control_change',55]]

def key_id(event,platform=None):
    code=event.keycode
    if (platform or sys.platform)!='win32':
        # X11 physical keycodes, for development smoke tests only.
        code={65:0x20,61:0xBF,52:0x5A,53:0x58,113:0x25,114:0x27}.get(code,code)
    return ('CTRL+' if event.state&4 else '')+f'VK_{code:02X}'

def migrate_bindings(config):
    if config.get('version',0)>=2:return config.get('bindings',DEFAULT_BINDINGS)
    result=[row.copy() for row in DEFAULT_BINDINGS]
    legacy={'space':'VK_20','Left':'VK_25','Right':'VK_27','z':'VK_5A','x':'VK_58'}
    for row in config.get('bindings',[]):
        action,key,source,ch,kind,num=row
        if action=='play' and (source,ch,kind,num)==(1,10,'note_on',52):continue
        if action=='pause' and key=='space':continue
        key=legacy.get(key, f'VK_{ord(key.upper()):02X}' if len(key)==1 and key.isascii() else '')
        updated=[action,key,source,ch,kind,num]
        for i,default in enumerate(result):
            if default[0]==action:result[i]=updated;break
        else:result.append(updated)
    return result
