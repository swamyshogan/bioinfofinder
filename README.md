# bioinfoFinder

`jupyter lab`, but for the [Mol*](https://molstar.org) viewer. Run it in any folder and Mol* opens in your browser, with a file browser for everything under that folder.

![bioinfoFinder demo: open a crystal structure, search all seed folders, overlay five models](docs/demo.gif)

```bash
cd ~/my_project/output
bioinfofinder
```

## Install
Needs Python 3.8+ and [pipx](https://pipx.pypa.io):

```bash
pipx install git+https://github.com/swamyshogan/bioinfofinder.git
```

No pipx yet? On macOS run `brew install pipx && pipx ensurepath`; on Linux run `python3 -m pip install --user pipx && python3 -m pipx ensurepath`. Then open a new terminal.

## What you get
- A sidebar file browser (folders, breadcrumbs, filter). New files show up on their own every 3 s.
- **Click** a file to open it. **⊕ or Shift-click** adds it to the current scene. **⌘-click or the checkboxes** select several files at once.
- Tick a **topology/structure + trajectory** (e.g. `.psf` + `.dcd`, `.gro` + `.xtc`) and press *Open* to load an MD run.
- **⤓** searches every subfolder for files Mol* can read. **⚛** hides files Mol* can't open.
- `.gz` files are decompressed on the fly. Supported: PDB/mmCIF/BCIF, PDBQT, GRO, MOL/MOL2/SDF, XYZ, PSF/PRMTOP/TOP, XTC/TRR/DCD/NC/LAMMPS, CCP4/MRC/MAP/DSN6/CUBE/DX, and `.molj`/`.molx`/`.mvsj` sessions.
- You can also drag files from Finder straight into the viewer.

## Options
```
bioinfofinder [folder | file.pdb]   folder to serve (default .), or one file to open right away
  -p, --port 8890                   port to try first (moves up if that one is busy)
  --no-browser                      don't open a tab
  --hidden                          show dotfiles
  --host 0.0.0.0                    share on the network (anyone who can reach the port can read the folder)
```

The server only listens on 127.0.0.1 by default and won't serve paths outside the folder you gave it. It needs only the Python standard library.
The Mol* build (v5.13.1) is downloaded once into `~/.cache/bioinfofinder/` and works offline after that. Set `BIOINFOFINDER_MOLSTAR_VERSION` to use a different version.

## Update / uninstall
```bash
pipx upgrade bioinfofinder
pipx uninstall bioinfofinder
```

## Development
```bash
git clone https://github.com/swamyshogan/bioinfofinder.git
cd bioinfofinder
pipx install -e .    # edits to the code take effect immediately
```

## Citing Mol*
bioinfoFinder is only a launcher; the viewer is [Mol*](https://github.com/molstar/molstar). If you use it in your work, please cite Mol*:

> David Sehnal, Sebastian Bittrich, Mandar Deshpande, Radka Svobodová, Karel Berka, Václav Bazgier, Sameer Velankar, Stephen K Burley, Jaroslav Koča, Alexander S Rose. [Mol* Viewer: modern web app for 3D visualization and analysis of large biomolecular structures](https://doi.org/10.1093/nar/gkab314). *Nucleic Acids Research*, 2021. https://doi.org/10.1093/nar/gkab314

## License
bioinfoFinder is released under the [MIT License](LICENSE). Copyright (c) 2026 Shogan Swamy.

It loads the [Mol*](https://github.com/molstar/molstar) Viewer, which is also MIT-licensed (Copyright (c) Mol* contributors). bioinfoFinder is an independent project, not affiliated with or endorsed by the Mol* team.
