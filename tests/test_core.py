import unittest,time,json,pathlib
from core import Model,Clock,PADS
class Tests(unittest.TestCase):
    def test_edit(self):
        m=Model();m.edit(36,0);self.assertEqual(m.notes[36][0],(100,100));m.edit(36,0);self.assertIsNone(m.notes[36][0]);m.select(127);self.assertEqual(m.base,112)
    def test_pads(self):self.assertEqual(len(set(PADS)),16)
    def test_clock_stop(self):
        events=[];m=Model();m.edit(36,0);c=Clock(m,lambda typ,**kw:events.append((typ,kw)));c.toggle();time.sleep(.16);c.close()
        types=[e[0] for e in events];self.assertEqual(types[0],'start');self.assertIn('note_on',types);self.assertIn('note_off',types);self.assertIn('stop',types);self.assertGreaterEqual(types.count('clock'),6)
    def test_capture(self):
        packets=json.loads(pathlib.Path('led_packets.json').read_text());self.assertEqual(len(packets),64)
        for p in packets:self.assertEqual(p[0],240);self.assertEqual(p[-1],247);self.assertTrue(all(x<128 for x in p[1:-1]))

    def test_pause_continues_without_reset(self):
        events=[];m=Model();m.length=300;m.edit(36,0)
        c=Clock(m,lambda typ,**kw:events.append((typ,kw)))
        try:
            c.pause_toggle()
            deadline=time.monotonic()+1
            while not c.active and time.monotonic()<deadline:time.sleep(.001)
            c.pause_toggle()
            tick=c.tick;step=c.step
            self.assertTrue(c.paused);self.assertFalse(c.active)
            time.sleep(.04)
            self.assertEqual(c.tick,tick);self.assertEqual(c.step,step)
            c.pause_toggle()
            self.assertIn('continue',[e[0] for e in events])
            self.assertEqual([e[0] for e in events].count('start'),1)
            c.stop();self.assertEqual(c.tick,0);self.assertEqual(c.step,-1)
        finally:c.close()
