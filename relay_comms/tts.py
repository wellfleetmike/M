"""Text-to-speech for relay message notification.

Uses piper-tts (neural, human-sounding) with espeak-ng as fallback."""

import subprocess
import shutil
from pathlib import Path

_PIPER = shutil.which('piper')
_ESPEAK = shutil.which('espeak-ng')
_APLAY = shutil.which('aplay')
_PIPER_MODEL = Path.home() / '.local' / 'share' / 'piper' / 'voices' / 'en_GB-alan-medium.onnx'

SPEED_MAP = {
    'info': 0.8,
    'alert': 0.75,
    'urgent': 0.7,
}


def speak(text, priority='info', blocking=False):
    """Speak text using piper-tts (preferred) or espeak-ng (fallback).

    Non-blocking by default (fire and forget).
    Set blocking=True to wait for speech to complete.
    Fails silently if no TTS is available.
    """
    text = text[:500]

    if _PIPER and _APLAY and _PIPER_MODEL.exists():
        return _speak_piper(text, priority, blocking)
    elif _ESPEAK:
        return _speak_espeak(text, priority, blocking)
    return None


def _speak_piper(text, priority, blocking):
    """Neural TTS via piper -> aplay pipeline."""
    speed = SPEED_MAP.get(priority, 1.0)
    cmd = (
        f'echo {_shell_quote(text)} | '
        f'piper --model {_PIPER_MODEL} --length-scale {1.0/speed:.2f} --output-raw 2>/dev/null | '
        f'aplay -r 22050 -f S16_LE -c 1 2>/dev/null'
    )
    try:
        if blocking:
            subprocess.run(cmd, shell=True, timeout=30)
            return None
        else:
            return subprocess.Popen(cmd, shell=True)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _speak_espeak(text, priority, blocking):
    """Fallback TTS via espeak-ng."""
    profiles = {
        'info':   {'speed': 150, 'pitch': 50},
        'alert':  {'speed': 160, 'pitch': 55},
        'urgent': {'speed': 175, 'pitch': 65},
    }
    profile = profiles.get(priority, profiles['info'])
    cmd = [_ESPEAK, '-v', 'en', '-s', str(profile['speed']), '-p', str(profile['pitch']), text]
    try:
        if blocking:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            return None
        else:
            return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _shell_quote(text):
    """Escape text for shell."""
    return "'" + text.replace("'", "'\"'\"'") + "'"
