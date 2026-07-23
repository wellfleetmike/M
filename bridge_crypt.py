#!/usr/bin/env python3
"""bridge_crypt.py -- age encryption helper for the relay bridge.

Uses the `age` binary if present on PATH (preferred; audited implementation),
otherwise falls back to the pure-Python `age` package (pip install age).
Both produce/consume the standard age v1 format, so nodes can mix freely.

Key material:
    Identity file  -- one AGE-SECRET-KEY-1... line (comments/# allowed)
    Recipients file -- one age1... public key per line (comments/# allowed)

Tiers:
    A tier is just a recipients file. relay_bridge/recipients/<tier>.txt
    holds the public keys allowed to read memories in that tier.
    Example:
        recipients/sovereign.txt   -> pos, laptop
        recipients/session.txt     -> pos, laptop, claude-session
    Encrypting to a tier means encrypting to every key listed in its file.
"""

import io
import shutil
import subprocess
import sys
from pathlib import Path

AGE_BIN = shutil.which('age')


# ---------------------------------------------------------------- key parsing

def read_recipients(path):
    """Return list of age1... public key strings from a recipients file."""
    lines = Path(path).read_text().splitlines()
    keys = [ln.strip() for ln in lines
            if ln.strip() and not ln.strip().startswith('#')]
    bad = [k for k in keys if not k.startswith('age1')]
    if bad:
        raise ValueError(f'{path}: not age public keys: {bad}')
    if not keys:
        raise ValueError(f'{path}: no recipients found')
    return keys


def read_identity(path):
    """Return the AGE-SECRET-KEY-1... string from an identity file."""
    for ln in Path(path).read_text().splitlines():
        ln = ln.strip()
        if ln.startswith('AGE-SECRET-KEY-1'):
            return ln
    raise ValueError(f'{path}: no AGE-SECRET-KEY found')


# ---------------------------------------------------------------- age binary

def _encrypt_bin(data, recipients):
    cmd = [AGE_BIN]
    for r in recipients:
        cmd += ['-r', r]
    p = subprocess.run(cmd, input=data, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f'age encrypt failed: {p.stderr.decode()}')
    return p.stdout


def _decrypt_bin(data, identity_path):
    p = subprocess.run([AGE_BIN, '-d', '-i', str(identity_path)],
                       input=data, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f'age decrypt failed: {p.stderr.decode()}')
    return p.stdout


# ---------------------------------------------------------------- pyage

def _pyage():
    try:
        from age.file import Encryptor, Decryptor
        from age.keys.agekey import AgePrivateKey, AgePublicKey
        return Encryptor, Decryptor, AgePrivateKey, AgePublicKey
    except ImportError:
        print('need either the `age` binary on PATH or `pip install age`',
              file=sys.stderr)
        raise


def _encrypt_py(data, recipients):
    Encryptor, _, _, AgePublicKey = _pyage()
    pubs = [AgePublicKey.from_public_string(r) for r in recipients]
    buf = io.BytesIO()
    with Encryptor(pubs, buf) as e:
        e.write(data)
    return buf.getvalue()


def _decrypt_py(data, identity_path):
    _, Decryptor, AgePrivateKey, _ = _pyage()
    key = AgePrivateKey.from_private_string(read_identity(identity_path))
    out = io.BytesIO()
    with Decryptor([key], io.BytesIO(data)) as d:
        out.write(d.read())
    return out.getvalue()


# ---------------------------------------------------------------- public api

def encrypt(data: bytes, recipients: list) -> bytes:
    """Encrypt bytes to a list of age1... recipients."""
    if AGE_BIN:
        return _encrypt_bin(data, recipients)
    return _encrypt_py(data, recipients)


def decrypt(data: bytes, identity_path) -> bytes:
    """Decrypt bytes using the identity file at identity_path."""
    if AGE_BIN:
        return _decrypt_bin(data, identity_path)
    return _decrypt_py(data, identity_path)


def generate_keypair():
    """Return (private_string, public_string). Uses age-keygen or pyage."""
    keygen = shutil.which('age-keygen')
    if keygen:
        p = subprocess.run([keygen], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr)
        priv = next(ln for ln in p.stdout.splitlines()
                    if ln.startswith('AGE-SECRET-KEY-1'))
        pub = next(ln.split(': ', 1)[1] for ln in p.stderr.splitlines()
                   if 'Public key' in ln)
        return priv, pub
    _, _, AgePrivateKey, _ = _pyage()
    k = AgePrivateKey.generate()
    return k.private_string(), k.public_key().public_string()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'keygen':
        priv, pub = generate_keypair()
        print(f'# public key: {pub}\n{priv}')
    else:
        print('usage: bridge_crypt.py keygen   (prints a new identity to stdout)')
