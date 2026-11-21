from collections import defaultdict

import pretty_midi

from .engines.base import Note


def midi_to_notes(path: str) -> tuple[list[Note], float]:
    pm = pretty_midi.PrettyMIDI(path)
    notes: list[Note] = []
    for inst in pm.instruments:
        for n in inst.notes:
            notes.append(Note(program=inst.program, pitch=n.pitch,
                              start=n.start, end=n.end,
                              velocity=n.velocity, is_drum=inst.is_drum))
    return notes, pm.get_end_time()


def notes_to_midi(notes: list[Note], bpm: int = 120,
                  path: str | None = None) -> pretty_midi.PrettyMIDI:
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    groups: dict[tuple[int, bool], list[Note]] = defaultdict(list)
    for n in notes:
        groups[(n.program, n.is_drum)].append(n)
    for (program, is_drum), g in groups.items():
        inst = pretty_midi.Instrument(program=program, is_drum=is_drum)
        for n in g:
            inst.notes.append(pretty_midi.Note(
                velocity=max(1, min(127, n.velocity)),
                pitch=n.pitch, start=n.start, end=n.end))
        pm.instruments.append(inst)
    if path:
        pm.write(path)
    return pm
