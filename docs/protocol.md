# SMK RGB protocol

Source: user attachment `red to white.pcapng`, 64 host-to-device commands.
USB MIDI CIN framing is stripped; each command is 24 MIDI bytes.

Fixed prefix: `F0 00 32 09 61 00 00 40 02`.
The next 14 seven-bit bytes encode a little-endian bit stream containing 12 raw bytes:

| Raw offset | Content |
| --- | --- |
| 0–3 | Little-endian address: 283 + 74 × pad index (0–31) |
| 4–6 | `04 00 00` |
| 7–9 | 8-bit red, green, blue |
| 10 | `FF` (preserved opaque fourth color byte) |
| 11 | `(250 - sum(raw[0:11])) & 255` |

The stream is divided into low-to-high 7-bit chunks, zero-padded to 14 chunks,
then terminated with `F7`. The checksum invariant is `sum(raw) % 256 == 250`
for this fixed command prefix. Do not reuse it for other SMK commands.

`lighting.packet` regenerates all 64 original red/white commands byte-for-byte.
Black and arbitrary colors are generated using the same decoded structure;
their actual LED appearance still needs hardware verification. The user confirmed
the original red/white build works. Pad memory is shared across layouts: the app
repaints all 32 pads when channel 10/11 is observed or selected in the GUI.
A hardware channel switch that sends no MIDI cannot be detected until the next event.

Output is throttled to one changed pad per 20 ms. Device ACK was observed as
`F0 00 32 01 08 00 00 00 00 7F 01 F7`; ACK gating is not implemented.
