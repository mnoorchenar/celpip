"""
Download free/open-source fonts and extract static Regular + Bold instances.
Run once: python setup_fonts.py

All fonts are SIL OFL or Apache 2.0 — fully free for commercial use,
including YouTube monetization.

Requires: fonttools  (pip install fonttools)
"""

import os
import sys
import urllib.request

FONTS_DIR = os.path.join(os.path.dirname(__file__), 'fonts')

# Variable font download: (save_as, license, url)
_VAR_DOWNLOADS = [
    ('_var_inter.ttf',      'SIL OFL',    'https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf'),
    ('_var_lora.ttf',       'SIL OFL',    'https://raw.githubusercontent.com/google/fonts/main/ofl/lora/Lora%5Bwght%5D.ttf'),
    ('_var_roboto.ttf',     'SIL OFL',    'https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf'),
    ('_var_opensans.ttf',   'SIL OFL',    'https://raw.githubusercontent.com/google/fonts/main/ofl/opensans/OpenSans%5Bwdth%2Cwght%5D.ttf'),
    ('_var_nunito.ttf',     'SIL OFL',    'https://raw.githubusercontent.com/google/fonts/main/ofl/nunito/Nunito%5Bwght%5D.ttf'),
    ('_var_robotomono.ttf', 'Apache 2.0', 'https://raw.githubusercontent.com/google/fonts/main/ofl/robotomono/RobotoMono%5Bwght%5D.ttf'),
]

# Static instances to extract: (var_file, output_file, axes)
# wght: 400 = Regular, 700 = Bold
# wdth: 100 = Normal width (for Roboto/OpenSans which have a width axis)
_INSTANCES = [
    ('_var_inter.ttf',      'Inter-Regular.ttf',    {'wght': 400, 'opsz': 14}),
    ('_var_inter.ttf',      'Inter-Bold.ttf',        {'wght': 700, 'opsz': 14}),
    ('_var_lora.ttf',       'Lora-Regular.ttf',      {'wght': 400}),
    ('_var_lora.ttf',       'Lora-Bold.ttf',         {'wght': 700}),
    ('_var_roboto.ttf',     'Roboto-Regular.ttf',    {'wght': 400, 'wdth': 100}),
    ('_var_roboto.ttf',     'Roboto-Bold.ttf',       {'wght': 700, 'wdth': 100}),
    ('_var_opensans.ttf',   'OpenSans-Regular.ttf',  {'wght': 400, 'wdth': 100}),
    ('_var_opensans.ttf',   'OpenSans-Bold.ttf',     {'wght': 700, 'wdth': 100}),
    ('_var_nunito.ttf',     'Nunito-Regular.ttf',    {'wght': 400}),
    ('_var_nunito.ttf',     'Nunito-Bold.ttf',       {'wght': 700}),
    ('_var_robotomono.ttf', 'RobotoMono-Bold.ttf',   {'wght': 700}),
]


def _download(filename, url):
    dest = os.path.join(FONTS_DIR, filename)
    if os.path.exists(dest) and os.path.getsize(dest) > 10_000:
        print(f'  [skip]  {filename}')
        return True
    print(f'  [download]  {filename} ...', end='', flush=True)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(dest, 'wb') as f:
            f.write(data)
        print(f' {len(data) // 1024} KB  OK')
        return True
    except Exception as e:
        print(f' FAILED: {e}')
        return False


def _extract_instance(var_filename, out_filename, axes):
    """Extract a static instance from a variable font using fonttools."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    var_path = os.path.join(FONTS_DIR, var_filename)
    out_path = os.path.join(FONTS_DIR, out_filename)

    if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000:
        print(f'  [skip]  {out_filename}')
        return True

    if not os.path.exists(var_path):
        print(f'  [skip]  {out_filename}  (source not downloaded)')
        return False

    print(f'  [extract]  {out_filename} (wght={axes.get("wght", "?")}) ...', end='', flush=True)
    try:
        font = TTFont(var_path)

        # Filter axes to only those present in this font
        fvar = font.get('fvar')
        available = {a.axisTag for a in fvar.axes} if fvar else set()
        filtered = {k: v for k, v in axes.items() if k in available}

        instancer.instantiateVariableFont(font, filtered, inplace=True, optimize=False)
        font.save(out_path)
        size = os.path.getsize(out_path)
        print(f' {size // 1024} KB  OK')
        return True
    except Exception as e:
        print(f' FAILED: {e}')
        return False


def main():
    os.makedirs(FONTS_DIR, exist_ok=True)

    # Check fonttools
    try:
        import fontTools  # noqa
    except ImportError:
        print('fonttools is required. Installing...')
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'fonttools'])
        print()

    print(f'Font directory: {FONTS_DIR}\n')

    print('-- Downloading variable fonts ----------------------------------')
    for filename, license_name, url in _VAR_DOWNLOADS:
        _download(filename, url)

    print('\n-- Extracting static instances ---------------------------------')
    for var_file, out_file, axes in _INSTANCES:
        _extract_instance(var_file, out_file, axes)

    print('\nDone.')
    print('All fonts are free for commercial use (SIL OFL / Apache 2.0).')

    # Verify
    missing = [out for _, out, _ in _INSTANCES
               if not os.path.exists(os.path.join(FONTS_DIR, out))]
    if missing:
        print(f'\nWARNING: {len(missing)} font(s) failed to generate: {missing}')
    else:
        print(f'All {len(_INSTANCES)} font files ready.')


if __name__ == '__main__':
    main()
