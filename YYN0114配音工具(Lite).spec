# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# 配音脚本：释放到 _MEIPASS/dub_scripts，运行期再由 gui.py 复制到 %APPDATA%\YYNTools\dub_scripts_lite
# 路径一律基于 SPECPATH（本 spec 所在目录），换机器 / 换 clone 位置都能直接打包
import os
_SDIR = os.path.join(SPECPATH, 'scripts')
for _n in ('dub_itts.py', 'dub_gpt.py', 'tts_resident.py', 'sound-askuser.wav'):
    datas.append((os.path.join(_SDIR, _n), 'dub_scripts'))

# 窗口图标：运行期由 gui.py 的 iconbitmap 读取（exe 里的图标资源只管资源管理器）
datas.append((os.path.join(SPECPATH, 'assets', 'icon.ico'), 'assets'))


a = Analysis(
    [os.path.join(SPECPATH, 'gui.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="YYN0114配音工具(Lite)",
    icon=os.path.join(SPECPATH, 'assets', 'icon.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
