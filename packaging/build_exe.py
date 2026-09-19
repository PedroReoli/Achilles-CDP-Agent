"""
build_exe.py — Compila o Achilles CDP Agent em um executável standalone para Windows (.exe) via PyInstaller.
"""
import os
import subprocess
import sys


def build():
    print("==================================================")
    print("   ACHILLES CDP AGENT — BUILD EXECUTAVEL (.EXE)   ")
    print("==================================================")
    
    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "achilles.spec"
    ]
    print("Executando:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("\n[OK] Executavel gerado com sucesso em dist/achilles.exe")


if __name__ == "__main__":
    build()
