"""
Ambient background music generator using numpy + scipy.
Produces royalty-free calm/gentle/peaceful arpeggios and pads.
"""

import os
import random
import struct
import wave
import math

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from scipy.signal import fftconvolve
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from config import MUSIC_VOLUME, TEMP_DIR

SAMPLE_RATE = 44100


# Note frequencies for MIDI-like notes (middle octave)
def _note_freq(note_name, octave=4):
    """Return frequency for note name + octave."""
    notes = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    semitone = notes[note_name] + (octave - 4) * 12
    return 440.0 * (2.0 ** (semitone / 12.0))


# Scale definitions (major scales in semitones from root)
_MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]

# Chord definitions: root, third, fifth (semitone offsets from scale root)
_CHORDS = {
    'I':   [0, 4, 7],
    'IV':  [5, 9, 12],
    'V':   [7, 11, 14],
    'vi':  [9, 12, 16],
}

_MOODS = ['calm', 'drift', 'mist', 'haze']

_MOOD_PARAMS = {
    'calm': {
        'key': 'C', 'octave': 3, 'bpm': 40,
        'progression': ['I', 'IV', 'I', 'V'],
        'style': 'pad',
    },
    'drift': {
        'key': 'F', 'octave': 3, 'bpm': 38,
        'progression': ['I', 'vi', 'IV', 'I'],
        'style': 'pad',
    },
    'mist': {
        'key': 'G', 'octave': 3, 'bpm': 36,
        'progression': ['I', 'IV', 'I', 'IV'],
        'style': 'pad',
    },
    'haze': {
        'key': 'D', 'octave': 3, 'bpm': 42,
        'progression': ['I', 'V', 'vi', 'IV'],
        'style': 'pad',
    },
}

_KEY_ROOT_FREQ = {
    'C': _note_freq('C', 4),
    'D': _note_freq('D', 4),
    'F': _note_freq('F', 4),
    'G': _note_freq('G', 4),
}

_KEY_SEMITONES = {
    'C': 0,
    'D': 2,
    'F': 5,
    'G': 7,
}


def _sine_wave(freq, duration, sr=SAMPLE_RATE, amplitude=0.5):
    """Generate a pure sine wave."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return amplitude * np.sin(2 * np.pi * freq * t)


def _adsr_envelope(n_samples, sr=SAMPLE_RATE,
                   attack=0.05, decay=0.1, sustain=0.7, release=0.15):
    """
    Build an ADSR envelope of length n_samples.
    Times are fractions of total duration.
    """
    total = n_samples
    a_end = int(attack * total)
    d_end = int((attack + decay) * total)
    r_start = int((1.0 - release) * total)

    env = np.ones(total)
    # Attack: 0 -> 1
    if a_end > 0:
        env[:a_end] = np.linspace(0.0, 1.0, a_end)
    # Decay: 1 -> sustain
    if d_end > a_end:
        env[a_end:d_end] = np.linspace(1.0, sustain, d_end - a_end)
    # Sustain
    env[d_end:r_start] = sustain
    # Release: sustain -> 0
    if r_start < total:
        env[r_start:] = np.linspace(sustain, 0.0, total - r_start)
    return env


def _add_reverb(signal, sr=SAMPLE_RATE, decay=0.3, room_size=0.4):
    """Simple convolution reverb using exponential IR."""
    if not SCIPY_AVAILABLE:
        return signal
    ir_len = int(room_size * sr)
    t = np.linspace(0, room_size, ir_len)
    ir = np.exp(-decay * t / room_size)
    ir /= ir.sum() + 1e-9
    wet = fftconvolve(signal, ir)[:len(signal)]
    return signal * 0.7 + wet * 0.3


def _get_chord_freqs(chord_name, key, base_octave, n_octaves):
    """Return list of frequencies for a chord."""
    root_semitone = _KEY_SEMITONES[key]
    offsets = _CHORDS[chord_name]
    freqs = []
    for oct_shift in range(n_octaves):
        for offset in offsets:
            total_semitones = root_semitone + offset + oct_shift * 12
            # Base frequency: C4 = 261.63 Hz, adjust from there
            freq = 261.63 * (2.0 ** (total_semitones / 12.0))
            if base_octave < 4:
                freq /= (2 ** (4 - base_octave))
            elif base_octave > 4:
                freq *= (2 ** (base_octave - 4))
            freqs.append(freq)
    return freqs


def _render_arpeggio(chord_freqs, beat_duration, sr=SAMPLE_RATE):
    """Render an arpeggiated chord over one beat."""
    note_dur = beat_duration / len(chord_freqs)
    n_note = int(note_dur * sr)
    chunk = np.zeros(int(beat_duration * sr))
    env = _adsr_envelope(n_note, sr, attack=0.02, decay=0.1, sustain=0.6, release=0.3)
    for i, freq in enumerate(chord_freqs):
        wave = _sine_wave(freq, note_dur, sr, amplitude=0.4)
        wave[:len(env)] *= env[:len(wave)]
        start = i * n_note
        end = start + len(wave)
        if end <= len(chunk):
            chunk[start:end] += wave
    return chunk


def _render_pad(chord_freqs, duration, sr=SAMPLE_RATE):
    """Render a very soft sustained chord pad — slow attack, long release."""
    n = int(duration * sr)
    chunk = np.zeros(n)
    env = _adsr_envelope(n, sr, attack=0.35, decay=0.05, sustain=0.65, release=0.45)
    for freq in chord_freqs:
        # Mix sine + slight second harmonic for warmth, keep very quiet
        wave = _sine_wave(freq, duration, sr, amplitude=0.15)
        wave += _sine_wave(freq * 2.0, duration, sr, amplitude=0.04)
        chunk += wave
    chunk *= env
    return chunk


def _write_wav(path, samples, sr=SAMPLE_RATE):
    """Write float32 numpy array as 16-bit WAV."""
    # Clip and convert to int16
    samples = np.clip(samples, -1.0, 1.0)
    int_samples = (samples * 32767).astype(np.int16)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int_samples.tobytes())


def _write_wav_silent(path, duration_sec, sr=SAMPLE_RATE):
    """Write a silent WAV file."""
    n = int(duration_sec * sr)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b'\x00\x00' * n)


def generate_ambient_music(duration_sec, seed=None, job_temp_dir=None):
    """
    Generate ambient background music.
    Returns path to generated WAV file.

    Args:
        duration_sec: length of music in seconds
        seed: random seed for reproducibility
        job_temp_dir: directory for temp files (uses TEMP_DIR if None)
    """
    out_dir = job_temp_dir or TEMP_DIR
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'ambient_music_{seed or "noseed"}.wav')

    if not NUMPY_AVAILABLE:
        # Write silence as fallback
        _write_wav_silent(out_path, duration_sec)
        return out_path

    rng = random.Random(seed)
    mood = rng.choice(_MOODS)
    params = _MOOD_PARAMS[mood]

    key = params['key']
    bpm = params['bpm']
    progression = params['progression']
    style = params['style']
    base_octave = params['octave']
    n_octaves = params['octaves']

    beat_duration = 60.0 / bpm
    # Each chord gets 4 beats
    chord_duration = beat_duration * 4
    sr = SAMPLE_RATE

    total_samples = int(duration_sec * sr)
    output = np.zeros(total_samples)

    pos = 0
    prog_idx = 0
    while pos < total_samples:
        chord_name = progression[prog_idx % len(progression)]
        prog_idx += 1
        chord_freqs = _get_chord_freqs(chord_name, key, base_octave, n_octaves)

        # Always use pad — no arpeggios
        chunk = _render_pad(chord_freqs, chord_duration, sr)
        end = min(pos + len(chunk), total_samples)
        output[pos:end] += chunk[:end - pos]
        pos += len(chunk)

    # Apply reverb
    output = _add_reverb(output, sr)

    # Normalize
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak

    # Apply MUSIC_VOLUME
    output *= MUSIC_VOLUME

    # Fade in / fade out (2 seconds each)
    fade_samples = min(int(2.0 * sr), total_samples // 4)
    fade_in = np.linspace(0.0, 1.0, fade_samples)
    fade_out = np.linspace(1.0, 0.0, fade_samples)
    output[:fade_samples] *= fade_in
    if len(output) > fade_samples:
        output[-fade_samples:] *= fade_out

    _write_wav(out_path, output, sr)
    return out_path
