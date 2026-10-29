import sys
from core import PADS,PADS2

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

DEFAULT_BINDINGS += [[action,key,0,1,'note_on',0] for action,key in [
    ('home','VK_24'),('end','VK_23'),('duplicate_selection','CTRL+VK_44'),('fill_end','VK_46'),
    ('follow_keys','VK_51'),('follow_playhead','VK_57'),('paint_velocity','VK_45'),('paint_gate','VK_52'),
    ('offset_up','CTRL+VK_49'),('offset_down','CTRL+VK_4B'),('drone','VK_56'),
    ('legato','VK_42'),('nonlegato','VK_4E'),('pitch_reset','VK_C0'),
    ('hide_bends','VK_BD'),('hide_micro','VK_BB')]]
for i in range(1,9):DEFAULT_BINDINGS.append([f'pitch_{i}',f'VK_{0x30+i:02X}',0,1,'note_on',0])
for i in range(1,11):
    key=f'VK_{0x30+i%10:02X}'
    for prefix,action in [('CTRL+','duplicate'),('CTRL+SHIFT+','duplicate_end'),('CTRL+ALT+','duplicate_left')]:
        DEFAULT_BINDINGS.append([f'{action}_{i}',prefix+key,0,1,'note_on',0])
for c in range(9):
    DEFAULT_BINDINGS += [[f'mute_{c}',f'ALT+VK_{0x61+c:02X}',0,1,'note_on',0],[f'delete_channel_{c}',f'CTRL+VK_{0x61+c:02X}',0,1,'note_on',0]]
for p in range(8):DEFAULT_BINDINGS.append([f'pattern_{p}',f'VK_{0x61+p:02X}',0,1,'note_on',0])
for c in range(9):DEFAULT_BINDINGS.append([f'select_channel_{c}','',0,1,'note_on',0])
for c in range(10,17):DEFAULT_BINDINGS.append([f'pad_layout_{c}','',0,1,'note_on',0])
for i in range(8):
    DEFAULT_BINDINGS += [[f'knob_velocity_{i}','',1,6,'control_change',48+i],[f'knob_gate_{i}','',1,6,'control_change',56+i]]
for action in ('stop','save','load','clear_note','clear_channel','clear_pattern','view_only','panic','reset_knobs','force_velocity','force_gate','pin_faders','export_settings','import_settings','settings_apply','settings_close','set_length'):
    DEFAULT_BINDINGS.append([action,'',0,1,'note_on',0])
for i in range(1,8):DEFAULT_BINDINGS.append([f'length_tens_{i}',f'ALT+VK_{0x6f+i:02X}',0,1,'note_on',0])
for c in range(10,17):
    for i,note in enumerate(PADS+PADS2):DEFAULT_BINDINGS.append([f'pad_{c}_{i}','',1,c,'note_on',note])

LABELS={'pause':'Play / Stop','play':'Play / Stop','length':'Gate fader','velocity':'Velocity fader','tempo':'BPM fader','follow_keys':'Follow MIDI keys','follow_playhead':'Follow playhead','paint_velocity':'Paint existing velocity','paint_gate':'Paint existing gate','fill_end':'Repeat copies to pattern end'}
def pad_label(ch,i):
    if ch==13:return 'Unassigned'
    if ch>=14:return f'Forward pad {i+1} to dedicated output'
    if ch==10 and i<16:return f'Step {i+1}: tap toggles, hold selects'
    if ch==11 and i<8:return f'Pattern {i+1} / modifier target'
    if ch==11 and i<16:return {8:'Hold: view pattern',9:'Hold: copy channel pattern',10:'Hold: copy note',11:'Hold: clear whole pattern',12:'Hold: clear note',15:'Undo / hold 1s Redo'}.get(i,'Unassigned')
    if ch==12 and i<9:return f'Mute instrument {i+1}'
    if i>=16:
        return {24:'Play / Stop',31:'Undo' if ch==10 else 'Undo / hold 1s Redo',23:'Redo' if ch==10 else 'Unassigned',29:'Previous 8 steps' if ch==10 else 'Unassigned',30:'Next 8 steps' if ch==10 else 'Unassigned'}.get(i,'Unassigned')
    return 'Unassigned'
def action_label(action):
    if action.startswith('pad_'):
        if action.startswith('pad_layout_'):return f'Pad layout: channel {action.split("_")[-1]}'
        _,ch,i=action.split('_');return f'Ch {ch} B{int(i)//16+1} P{int(i)%16+1}: '+pad_label(int(ch),int(i))
    for prefix,label in [('mute_','Mute instrument'),('delete_channel_','Clear instrument / double: whole pattern'),('pattern_','Queue pattern / double: immediate'),('select_channel_','Select instrument')]:
        if action.startswith(prefix):return f'{label} {int(action[len(prefix):])+1}'
    return LABELS.get(action,action.replace('_',' ').title())
def action_order(action):
    groups=[('pause','play','stop','tempo','pattern_','view_only','set_length','length_tens_'),
            ('grid_','home','end','prev_page','next_page','left','right','group_','up_page','down_page','offset_','follow_','select_channel_'),
            ('undo','redo','duplicate_','fill_end','scope_','repeat_pages','paint_','gate_view','clear_','delete_channel_'),
            ('audition','mute_','drone','legato','nonlegato','pitch_','hide_'),
            ('velocity','length','knob_','force_','reset_knobs','pin_faders','panic'),
            ('save','load','options','settings_','export_settings','import_settings'),('pad_layout_',),('pad_',)]
    return next((i for i,group in enumerate(groups) if any(action.startswith(x) if x.endswith('_') else action==x for x in group)),len(groups))
def pretty_key(key):
    if not key:return '—'
    parts=key.split('+');code=int(parts[-1][3:],16)
    names={0x20:'Space',0x25:'Left',0x26:'Up',0x27:'Right',0x28:'Down',0x24:'Home',0x23:'End',0xBF:'/',0xBA:';',0xBE:'.',0xC0:'`',0xBD:'-',0xBB:'='}
    text=names.get(code,chr(code) if 0x30<=code<=0x5A else f'F{code-0x6f}' if 0x70<=code<=0x7B else f'Num {code-0x60}' if 0x60<=code<=0x69 else f'VK {code:02X}')
    return ' + '.join([p.title() for p in parts[:-1]]+[text])

def key_id(event,platform=None):
    code=event.keycode
    if (platform or sys.platform)!='win32':
        # X11 physical keycodes, for development smoke tests only.
        code={65:0x20,61:0xBF,52:0x5A,53:0x58,113:0x25,114:0x27,111:0x26,116:0x28,
              44:0x4A,45:0x4B,46:0x4C,31:0x49,43:0x48,47:0xBA,29:0x59,33:0x50,
              60:0xBE,38:0x41,39:0x53,40:0x44,42:0x47,
              9:0x1B,110:0x24,115:0x23,41:0x46,24:0x51,25:0x57,26:0x45,27:0x52,55:0x56,56:0x42,57:0x4E,
              28:0x54,49:0xC0,20:0xBD,21:0xBB,87:0x61,88:0x62,89:0x63,83:0x64,84:0x65,85:0x66,79:0x67,80:0x68,81:0x69,90:0x60,
              **{10+i:0x31+i for i in range(9)},19:0x30,**{67+i:0x70+i for i in range(7)},64:0x12}.get(code,code)
    # Windows Tk uses 0x20000 for Alt; X11 uses Mod1 (0x8).
    alt=bool(event.state & (0x20000 if (platform or sys.platform)=='win32' else 8))
    return ('CTRL+' if event.state&4 else '')+('ALT+' if alt else '')+('SHIFT+' if event.state&1 else '')+f'VK_{code:02X}'

def migrate_bindings(config):
    result=[row.copy() for row in DEFAULT_BINDINGS]
    legacy={'space':'VK_20','Left':'VK_25','Right':'VK_27','z':'VK_5A','x':'VK_58'}
    for row in config.get('bindings',[]):
        action,key,source,ch,kind,num=row[:6]
        if action=='play' and (source,ch,kind,num)==(1,10,'note_on',52):continue
        if action=='pause' and key=='space':continue
        if action in ('velocity','length','tempo') and source==1 and ch==6 and kind=='control_change' and num in (48,49,55):continue
        if config.get('version',0)<2:key=legacy.get(key, f'VK_{ord(key.upper()):02X}' if len(key)==1 and key.isascii() else '')
        updated=[action,key,source,ch,kind,num]
        for i,default in enumerate(result):
            if default[0]==action:result[i]=updated;break
        else:result.append(updated)
    return result
