# --- START OF FILE acoustic_engine.py ---
# ======================================================================
# MetaForge Engine: Acoustic Forensics (Phase 5)
# Role: CPU-intensive harmonic analysis (BPM, Key, Intensity).
# Build 1.1.0: Fragment-based analysis (20s) for performance optimization.
# Physical Location: \tools\intelli-tagger\engines\acoustic_engine.py
# ======================================================================
import librosa
import numpy as np
import warnings

# Suppress librosa/audioread hardware warnings for cleaner console
warnings.filterwarnings("ignore", category=UserWarning)

def analyze_file(file_path):
    """
    Performs forensic bitstream analysis on the first 20 seconds of audio.
    Returns: Dictionary containing BPM, Key, Intensity, and Duration.
    """
    try:
        # Step 1: Load Fragment (20s offset to bypass intro silence/fade)
        # We load with duration=20 to keep memory footprint low.
        y, sr = librosa.load(str(file_path), duration=20)
        full_duration = librosa.get_duration(y=y, sr=sr)

        # Step 2: BPM Extraction (Tempo)
        # Using beat_track to identify the primary rhythmic pulse
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        # Handle librosa 0.10+ return types (array vs float)
        bpm = int(round(float(tempo[0] if hasattr(tempo, "__len__") else tempo)))

        # Step 3: Key Detection (Harmonic Analysis)
        # Using Chromagram (CQT) to map tonal centers
        key = _calculate_key(y, sr)

        # Step 4: Intensity Calculation (RMS Energy)
        # Maps average energy to a 1-10 scale (MetaForge Standard)
        intensity = _calculate_intensity(y)

        return {
            "bpm": bpm,
            "key": key,
            "intensity": intensity,
            "duration": int(full_duration)
        }

    except Exception as e:
        print(f"DEBUG: Acoustic Analysis Error on {file_path.name}: {e}")
        return {
            "bpm": 0,
            "key": "??",
            "intensity": 1,
            "duration": 0
        }

def _calculate_key(y, sr):
    """
    Internal Logic: Correlation-based key detection.
    Krumhansl-Schmuckler key-finding -- correlates the track's chroma
    profile against BOTH Major and Minor reference profiles (12 rotations
    each, 24 candidates total) and returns whichever correlates highest.

    Real bug, found live 2026-07-17: only the Major profile was ever
    implemented ("Simplified for Major only as per legacy"), so a genuine
    minor-key track could only ever be reported as some Major key -- a
    classic, well-documented confusion in key detection (relative major/
    minor share the same 7 notes, so a Major-only correlation often still
    "wins" even on unambiguously minor material), landing incorrect,
    unflagged data in the database. Completed with the Minor half of the
    same Krumhansl-Kessler (1982) profile pair the Major values already
    came from, rather than guessing at replacement values.
    """
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        maj_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
        min_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

        # Mean chroma values across the 20s fragment
        chroma_mean = np.mean(chroma, axis=1)

        # Calculate correlation for each of the 12 possible keys, against
        # both profiles -- 24 candidates total, not just the 12 Major ones.
        maj_correlations = [np.corrcoef(maj_profile, np.roll(chroma_mean, -i))[0, 1] for i in range(12)]
        min_correlations = [np.corrcoef(min_profile, np.roll(chroma_mean, -i))[0, 1] for i in range(12)]

        best_maj_idx = int(np.argmax(maj_correlations))
        best_min_idx = int(np.argmax(min_correlations))

        if maj_correlations[best_maj_idx] >= min_correlations[best_min_idx]:
            return f"{keys[best_maj_idx]}Maj"
        return f"{keys[best_min_idx]}Min"
    except:
        return "??"

def _calculate_intensity(y):
    """
    Internal Logic: Maps Root Mean Square (RMS) to 1-10 Intensity.
    Protocol: Intensity = (RMS * 50), Clipped 1-10.
    """
    try:
        rms = librosa.feature.rms(y=y)[0]
        avg_rms = np.mean(rms)
        # Scale and clip to MetaForge 1-10 standard
        val = int(np.clip((avg_rms * 50), 1, 10))
        return val
    except:
        return 1

# --- END OF FILE acoustic_engine.py ---