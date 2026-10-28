"""Packed SMK RGB commands reconstructed from the supplied USB capture."""
import re
def rgb(color):
    if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Color must be #RRGGBB')
    return tuple(int(color[i:i+2],16) for i in (1,3,5))
def blend(a,b,t):return '#'+''.join(f'{round(x+(y-x)*max(0,min(1,t))):02x}' for x,y in zip(rgb(a),rgb(b)))
def packet(index,color):
    if not 0<=index<32:raise ValueError('Pad index must be 0–31')
    raw=list((283+74*index).to_bytes(4,'little'))+[4,0,0]+list(rgb(color))+[255]
    raw.append((250-sum(raw))&255)
    bits=int.from_bytes(bytes(raw),'little')
    return [240,0,50,9,97,0,0,64,2]+[(bits>>(7*i))&127 for i in range(14)]+[247]
def default_theme():
    utility=['#245875']*16
    utility[7]='#e0a629';utility[8]='#26bd70';utility[15]='#cc477d'
    return {'empty_length':1,'empty':['#000000']*7,'grid_tint':8,'low':'#184c40','high':'#67ffcf',
            'pattern':'#477fff','encoder_top':'#ec8f24','encoder_bottom':'#8c4bde',
            'bank2':{str(ch):utility.copy() for ch in (10,11,13)}}
def empty_color(theme,step):
    return theme['empty'][step%theme['empty_length']]

def grid_color(theme,step,cell):
    if cell:return blend(theme['low'],theme['high'],cell[0]/127)
    return blend('#101722',empty_color(theme,step),theme.get('grid_tint',8)/100)

def colors(model,theme,mode):
    if mode==10:
        first=[blend(theme['low'],theme['high'],cell[0]/127) if cell else empty_color(theme,model.page*16+i)
               for i,cell in enumerate(model.notes[model.selected][model.page*16:model.page*16+16])]
    elif mode==11:first=[blend('#000000',theme['pattern'],(1,.65,.35)[i%3]) for i in range(16)]
    else:first=[theme['encoder_top']]*8+[theme['encoder_bottom']]*8
    return first+theme['bank2'][str(mode)].copy()
