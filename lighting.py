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
    first={str(c):['#246780']*16 for c in range(10,17)}
    first['11']=[blend('#000000','#477fff',(1,.65,.35)[i%3]) for i in range(16)]
    for i,color in {8:'#25b9b1',9:'#6699ff',10:'#b677ef',11:'#e7593b',12:'#e99435',15:'#cf4e97'}.items():first['11'][i]=color
    first['12']=['#ed566a']*9+['#172333']*7
    return {'ui':'Dark','empty_length':1,'empty':['#000000']*7,'grid_tint':8,'low':'#184c40','high':'#67ffcf',
            'pattern':'#477fff','encoder_top':'#ec8f24','encoder_bottom':'#8c4bde',
            'bank1':first,'bank2':{str(ch):utility.copy() for ch in range(10,17)}}
def merge_theme(saved):
    result=default_theme()
    for key,value in saved.items():
        if key in ('bank1','bank2'):result[key].update(value)
        else:result[key]=value
    if 'ui' not in saved:result['ui']='Legacy light'
    return result
def empty_color(theme,step):
    return theme['empty'][step%theme['empty_length']]

def grid_color(theme,step,cell):
    if cell:return blend(theme['low'],theme['high'],cell[0]/127)
    return blend('#edf1f6' if theme.get('ui')=='Light' else '#101722',empty_color(theme,step),theme.get('grid_tint',8)/100)

def colors(model,theme,mode):
    if mode==10:
        first=[blend(theme['low'],theme['high'],cell[0]/127) if cell else empty_color(theme,model.page*16+i)
               for i,cell in enumerate(model.notes[model.selected][model.page*16:model.page*16+16])]
    else:
        first=theme['bank1'][str(mode)].copy()
        if mode==12:
            first[:9]=[color if model.muted[i] else blend('#000000',color,.18) for i,color in enumerate(first[:9])]
    return first+theme['bank2'][str(mode)].copy()
