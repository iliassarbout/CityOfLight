# City of Light (COL)

**A high-performance, Unity-based digital twin of Paris for embodied AI, robotics, and XR research.**

[![COL Trailer](banner.png)](https://www.youtube.com/watch?v=KhIO3J9oGr8)

<p align="center"><a href="https://colab.research.google.com/drive/1Qw0uaRGRiITS5r77zU9NpuRp80KHVduO?usp=sharing" target="_blank" rel="noopener noreferrer"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Colab demo"></a>&nbsp;&nbsp;<a href="https://www.youtube.com/watch?v=KhIO3J9oGr8" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Trailer-YouTube-red?logo=youtube&logoColor=white" alt="Trailer"></a>&nbsp;&nbsp;<a href="LICENSE.md" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Code-Apache%202.0-blue.svg" alt="Code License"></a>&nbsp;&nbsp;<a href="LICENSE_ASSETS.txt" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Assets-CC%20BY--NC%204.0-purple.svg" alt="Assets License"></a></p>

<!-- [![Paper](https://img.shields.io/badge/Paper-arXiv-orange.svg)](https://arxiv.org/abs/XXXX.XXXXX) -->

<div align="center">
<strong>
[ <a href="#-quick-start">Quick Start</a> ·
<a href="#-features">Features</a> ·
<a href="#-releases">Releases</a> ·
<a href="#-licensing">Licensing</a> ·
<a href="#-citation">Citation</a> ·
<a href="#-contributors">Contributors</a> ]
</strong>
</div>

---

<p align="center">
  <img src="docs/images/teaser.gif" alt="COL teaser" width="820">
</p>

**City of Light (COL)** is a geo-anchored, city-scale simulator of Paris (~116 km²) with synchronized multi-sensor streams (**RGB, Depth, Normals, Semantics**) and a zero-copy Python bridge (**TURBO**) that sustains very high throughput (up to ~1300 FPS on a 4090 in our tests).  
COL is designed for **fast scripting, large-scale data collection, RL, sim-to-real and embodied research**.

**This repository contains both the COL build releases and PyCol, a lightweight Python stack that lets you control and interact with COL easily.**

---

## 🧩 Features

- **Geo-faithful Paris digital twin** — per-tile meshes from public GIS.
- **Synchronized multi-sensors** — RGB / Depth / Normals / Semantics per frame.
- **TURBO zero-copy bridge** — shared-memory streaming to NumPy (no gRPC, no per-pixel copies).
- **High throughput** — frame-accurate control & observation at hundreds to thousands of FPS (resolution-scalable).
- **Dynamic runtime** — stochastic pedestrians & vehicles; chunk streaming with a 3×3 tile window.
- **Python-first workflow** — simple APIs to launch Unity, move/rotate the agent, step actions, and read frames.
- **Reproducible I/O** — deterministic stepping and per-frame update index.

---

## 🛠 Quick Start

1) Clone the repo (python package):
```
    git clone https://github.com/Paris-COL/CityOfLight.git
```
2) Download current Unity build:
```
    cd CityOfLight
    curl -fL "https://github.com/Paris-COL/CityOfLight/releases/download/0.1.0/COL_0.1.0_Linux_x86_64_demo.zip" -o COL_0.1.0_Linux_x86_64_demo.zip
    unzip -o COL_0.1.0_Linux_x86_64_demo.zip
    chmod +x ./unix/COL.x86_64
```
3) Launch the demo notebook and start exploring COL

---

## 🚀 Releases

Current public releases contain **108 tiles of 10 000 m²** in the center of Paris.

---

## 📦 Documentation

*Coming soon.*

---

## 📜 Licensing

- **Code**: released under the **Apache 2.0** license. See `LICENSE.md`.
- **Assets (3D meshes, textures, etc.)**: released under **CC BY-NC 4.0**. See `LICENSE_ASSETS.txt`.

---

## ✏️ Citation

If you use **City of Light (COL)** in your research, please cite:

> (Citation to be added soon.)

A ready-to-use BibTeX entry will be provided here as soon as the paper is public.

---

## 👥 Contributors & Contact

City of Light (COL) was developed between **2024 and 2025** by **Ilias Sarbout**.
**Theo Cazenave-Coupet** contributed to COL during his internship (pedestrians system).
**Mehdi Ounissi** contributed to COL through guidance on design system choices.

For questions about COL or collaborations, contact the maintainers at ilias.sarbout [at] gmail [dot] com.

