#!/usr/bin/env  python

PROGDESC = """
    attempts to convert a MIDI file into G300 instructions

    MIDI files can be generated with the appropriate hardware
    or tools like musicpy, or found online
"""
from mido import *

# TODO remove this, dirty hack until timing is figured out
NOTE_LEN = 200
BLANK_LEN = 100

# chromatic scale https://en.wikipedia.org/wiki/Chromatic_scale
keys = [
	('C',	(16.35,	32.7,	65.41,	130.81,	261.63,	523.25,		1046.5,		2093,		4186),      ),
	('C#',	(17.32,	34.65,	69.3,	138.59,	277.18,	554.37,		1108.73,	2217.46,	4434.92),      ),
	('D',	(18.35,	36.71,	73.42,	146.83,	293.66,	587.33,		1174.66,	2349.32,	4698.63),      ),
	('D#',	(19.45,	38.89,	77.78,	155.56,	311.13,	622.25,		1244.51,	2489,		4978),      ),
	('E',	(20.6,	41.2,	82.41,	164.81,	329.63,	659.25,		1318.51,	2637,		5274),      ),
	('F',	(21.83,	43.65,	87.31,	174.61,	349.23,	698.46,		1396.91,	2793.83,	5587.65),      ),
	('F#',	(23.12,	46.25,	92.5,	185,	369.99,	739.99,		1479.98,	2959.96,	5919.91),      ),
	('G',	(24.5,	49,		98,		196,	392,	783.99,		1567.98,	3135.96,	6271.93),      ),
	('G#',	(25.96,	51.91,	103.83,	207.65,	415.3,	830.61,		1661.22,	3322.44,	6644.88),      ),
	('A',	(27.5,	55,		110,	220,	440,	880,		1760,		3520,		7040),      ),
	('A#',	(29.14,	58.27,	116.54,	233.08,	466.16,	932.33,		1864.66,	3729.31,	7458.62),      ),
	('B',	(30.87,	61.74,	123.47,	246.94,	493.88,	987.77,		1975.53,	3951,		7902.13),      ),
]

class Note:
    def __init__(self, m):
        self.note = m.note
        self.time = m.time
        # how loud the note is played
        self.velocity = m.velocity
        
    def __str__(self):
        if self.velocity == 0:
            # we need to cheat because Marlin doesn't support loudness -> feature request ;-)
            return f"M300 P{BLANK_LEN} S0"
        else:
            octave, note = divmod(self.note,8)
            note = keys[note-4]
            return f"M300 P{NOTE_LEN} S{note[1][octave-3]:.2f}; [Hz] {note[0]}{octave-3}"

def midi_to_m300(midi_file, track_num = None):

    yield f'; converted from "{midi_file}"'
    z=MidiFile(midi_file, clip=True)

    _key = []
    for n, t in enumerate(z.tracks):
        for m in t:
            if m.type == 'track_name':
                yield f"; {n, m}"
            elif m.type == 'key_signature':
                _key.append(m.key)
            elif m.type == 'set_tempo':
                yield f"; detected tempo:\t{m.tempo}[ms] (TODO: figure out how timing works, see https://sourceforge.net/projects/timidity)"
                tempo = m.tempo

    if track_num is None:
        if len(z.tracks) > 1:
            n = int(input("track # to encode: "))
            t = z.tracks[n]
            raise SystemExit
        else:
            t = z.tracks[0]
    else:
        t = z.tracks[track_num]

    for k in set(_key):
        yield f"; detected key:\t{k} (TODO: enable transpose)"

    for m in t:
        if m.type == 'note_on':
                #print('\n', m)
                N = Note(m)
                N.note = m.note
                N.total_duration = m.velocity
                N.remainder_duration = m.time
                try:
                    yield str(N)
                except Exception as e:
                    raise
                    print(e)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        prog='MIDI_to_M300',
        description=PROGDESC,
    )

    parser.add_argument("-o", help="output file", default = 'tune.gcode', metavar="file")
    parser.add_argument("-i", help="input file", default = None, metavar="file")
    parser.add_argument("-t", "--track", default = None, type=int, help="track # to encode", metavar="int")

    args = parser.parse_args()

    with open(args.o,'w') as output_file:
        for line in midi_to_m300( args.i, args.track ):
            output_file.write( line + '\n' )
