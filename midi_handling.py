import rtmidi
import math
import threading
import time

class MicrotonalInstrument:
    def __init__(self, port_name='virtual instrument port', channel_count=16, duration=1.):
        self.out_port = rtmidi.RtMidiOut()
        self.out_port.openVirtualPort(port_name)
        self.channel_count = channel_count
        self.last_channel_used = channel_count
        self.duration = duration
        self.active_chords = []
        self.end_notes_thread = threading.Thread(target=self.end_notes, args=())
        self.end_notes_thread.daemon = True
        self.end_notes_thread.start()

    def play_chord(self, chord):
        this_chord = []
        for note in chord:
            channel = (self.last_channel_used + 1) % self.channel_count
            self.last_channel_used = channel
            note = [channel] + note
            this_chord.append(note)

            pitch = math.floor(note[1])
            pitch_bend = 0.5 * (note[1] - pitch) + 0.5

            pb_message = rtmidi.MidiMessage.pitchWheel(channel + 1, int(pitch_bend * 16384))
            note_message = rtmidi.MidiMessage.noteOn(channel + 1, pitch, note[2])
            self.out_port.sendMessage(pb_message)
            self.out_port.sendMessage(note_message)

        self.active_chords.append((this_chord, time.time() + self.duration))

    def end_notes(self):
        while True:
            if len(self.active_chords) == 0:
                time.sleep(0.1)
                continue
            current_time = time.time()
            for i, (chord, end_time) in enumerate(self.active_chords):
                if end_time < current_time:
                    for note in chord:
                        self.out_port.sendMessage(rtmidi.MidiMessage.allNotesOff(note[0] + 1))
                    del self.active_chords[i]
            time.sleep(0.1)

    def end_all_notes(self):
        for channel in range(self.channel_count):
            self.out_port.sendMessage(rtmidi.MidiMessage.allNotesOff(channel + 1))