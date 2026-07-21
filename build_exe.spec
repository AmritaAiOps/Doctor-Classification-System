# PyInstaller spec -- build from repo root with:  pyinstaller build_exe.spec
# Produces a single-file desktop app: dist/HospitalReportAutomation.exe -- one
# portable file that can be moved/run from anywhere. Build speed comes from the
# isolated venv + heavy-lib excludes below, not from the packaging mode.
from PyInstaller.utils.hooks import collect_submodules, collect_all

# pywebview ships its GUI backend + the WebView2 .NET assemblies as data/
# binaries that PyInstaller can't infer -- collect_all grabs them all.
wv_datas, wv_binaries, wv_hidden = collect_all("webview")

hiddenimports = collect_submodules("uvicorn") + wv_hidden + [
    "backend.main",
    "openpyxl",
    "rapidfuzz",
    "fastapi",
    "pandas",
    "multipart",            # python-multipart, used by FastAPI upload parsing
    "anyio._backends._asyncio",
    "clr",                  # pythonnet, used by the edgechromium backend
]

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=wv_binaries,
    datas=[
        ("config", "config"),               # read-only defaults + xlsx template
        ("frontend/dist", "dist"),          # built React UI -> served from _MEIPASS/dist
    ] + wv_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Heavy libs the app never uses -- excluded so a stray transitive import
    # (or a global-env install) can't drag them into the bundle. torch alone
    # is ~2GB and was the main cause of slow builds / bloated exe.
    excludes=[
        "tkinter", "matplotlib",
        "torch", "torchvision", "torchaudio",
        "scipy", "sklearn", "transformers", "tensorflow",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

# All binaries + datas folded into EXE (and no COLLECT) => single-file build.
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="HospitalReportAutomation",
    console=False,          # windowed desktop app -- no console
    icon=None,
)
