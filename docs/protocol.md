# Captured LED evidence

Source: user attachment `red to white.pcapng` (11048 bytes), USBPcap packets.
64 host-to-device transfers each carry eight USB MIDI event packets, decoded
into 24-byte SysEx. Device-to-host replies decode to `F0 00 32 01 08 00 00 00 00 7F 01 F7`.

First red message:
`F0 00 32 09 61 00 00 40 02 1B 02 00 00 40 00 00 00 7F 01 00 78 4F 1B F7`
First white:
`F0 00 32 09 61 00 00 40 02 1B 02 00 00 40 00 00 00 7F 7F 7F 7F 6F 1B F7`

Address-like bytes 9–10 increment as a 7-bit packed integer by 74 per pad.
Bytes 18–20 and checksum-like bytes 21–22 differ by color. Two samples are
insufficient to validate arbitrary RGB encoding and checksum derivation.
`led_packets.json` holds exact MIDI packets, not USB wrappers.
