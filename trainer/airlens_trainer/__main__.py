"""Titik masuk trainer. Pelatihan dan evaluasi diisi di Fase 3."""

from airlens.config import load_profile

cfg = load_profile()
print(f"trainer siap (profil {cfg['profile']}, device {cfg['training']['device']}); pelatihan tersedia di Fase 3")
