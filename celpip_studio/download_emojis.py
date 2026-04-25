"""
Download Google Noto Emoji PNG files (Apache 2.0 — free for commercial use)
for the engage frame. Run once: python download_emojis.py
"""

import os
import urllib.request

EMOJI_DIR = os.path.join(os.path.dirname(__file__), 'data', 'emojis')
BASE_URL  = 'https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/512/emoji_u{}.png'

# ~120 fun / celebratory emojis — single codepoints, Apache 2.0
EMOJIS = [
    # ── Trophies & medals ──────────────────────────────────────────────────────
    '1f3c6',   # 🏆 trophy
    '1f3c5',   # 🏅 sports medal
    '1f947',   # 🥇 1st place medal
    '1f948',   # 🥈 2nd place medal
    '1f949',   # 🥉 3rd place medal
    '1f396',   # 🎖️ military medal
    '1f3f5',   # 🏵️ rosette
    '1f451',   # 👑 crown

    # ── Celebration ────────────────────────────────────────────────────────────
    '1f389',   # 🎉 party popper
    '1f38a',   # 🎊 confetti ball
    '1f386',   # 🎆 fireworks
    '1f387',   # 🎇 sparkler
    '1f9e8',   # 🧨 firecracker
    '1f388',   # 🎈 balloon
    '1f381',   # 🎁 gift box
    '2728',    # ✨ sparkles
    '1f4ab',   # 💫 dizzy / stars
    '1f31f',   # 🌟 glowing star
    '2b50',    # ⭐ star
    '1f320',   # 🌠 shooting star

    # ── Power & energy ─────────────────────────────────────────────────────────
    '1f525',   # 🔥 fire
    '26a1',    # ⚡ lightning bolt
    '1f4a5',   # 💥 collision
    '1f4aa',   # 💪 flexed biceps
    '1f9e0',   # 🧠 brain
    '1f4af',   # 💯 hundred points
    '1f680',   # 🚀 rocket
    '1f6f8',   # 🛸 flying saucer
    '1f300',   # 🌀 cyclone
    '1f30a',   # 🌊 water wave

    # ── Faces & moods ──────────────────────────────────────────────────────────
    '1f60e',   # 😎 sunglasses face
    '1f929',   # 🤩 star-struck
    '1f973',   # 🥳 partying face
    '1f920',   # 🤠 cowboy hat face
    '1f47e',   # 👾 alien monster
    '1f47d',   # 👽 alien
    '1f47b',   # 👻 ghost
    '1f916',   # 🤖 robot

    # ── Education & knowledge ──────────────────────────────────────────────────
    '1f393',   # 🎓 graduation cap
    '1f4da',   # 📚 books
    '1f4d6',   # 📖 open book
    '1f4ca',   # 📊 bar chart
    '1f4c8',   # 📈 chart increasing
    '1f4a1',   # 💡 light bulb
    '1f52d',   # 🔭 telescope
    '1f52c',   # 🔬 microscope
    '1f9ec',   # 🧬 DNA
    '1f9e9',   # 🧩 puzzle piece
    '1f4dd',   # 📝 memo

    # ── Gems & treasure ────────────────────────────────────────────────────────
    '1f48e',   # 💎 gem stone
    '1f4b0',   # 💰 money bag
    '1f511',   # 🔑 key
    '1f9f2',   # 🧲 magnet
    '1f48d',   # 💍 ring
    '1f3fa',   # 🏺 amphora

    # ── Sports & activity ──────────────────────────────────────────────────────
    '1f3af',   # 🎯 bullseye
    '1f3b1',   # 🎱 pool 8 ball
    '1f3b2',   # 🎲 game die
    '1f3b3',   # 🎳 bowling
    '1f3d3',   # 🏓 ping pong
    '1f3f8',   # 🏸 badminton
    '26bd',    # ⚽ soccer ball
    '1f3c0',   # 🏀 basketball
    '1f3c8',   # 🏈 american football
    '26be',    # ⚾ baseball
    '1f3be',   # 🎾 tennis
    '1f94a',   # 🥊 boxing glove
    '1f94b',   # 🥋 martial arts uniform
    '1f3bf',   # 🎿 skis
    '1f3c2',   # 🏂 snowboarder
    '1f6f9',   # 🛹 skateboard
    '1f93a',   # 🤺 person fencing

    # ── Arts & music ──────────────────────────────────────────────────────────
    '1f3a8',   # 🎨 artist palette
    '1f3ac',   # 🎬 clapper board
    '1f3a4',   # 🎤 microphone
    '1f3a7',   # 🎧 headphones
    '1f3b8',   # 🎸 guitar
    '1f3ba',   # 🎺 trumpet
    '1f3bb',   # 🎻 violin
    '1f941',   # 🥁 drum
    '1f3b5',   # 🎵 musical note
    '1f3b6',   # 🎶 musical notes
    '1f3aa',   # 🎪 circus tent
    '1f3ad',   # 🎭 performing arts
    '1f3a9',   # 🎩 top hat

    # ── Nature ────────────────────────────────────────────────────────────────
    '1f308',   # 🌈 rainbow
    '1f31e',   # 🌞 sun with face
    '1f319',   # 🌙 crescent moon
    '2744',    # ❄️ snowflake
    '1f30c',   # 🌌 milky way
    '1f30b',   # 🌋 volcano
    '1f304',   # 🌄 sunrise over mountains
    '1f305',   # 🌅 sunrise
    '1f303',   # 🌃 night with stars
    '1f33a',   # 🌺 hibiscus
    '1f338',   # 🌸 cherry blossom
    '1f33b',   # 🌻 sunflower
    '1f340',   # 🍀 four-leaf clover
    '1f98b',   # 🦋 butterfly

    # ── Animals ───────────────────────────────────────────────────────────────
    '1f981',   # 🦁 lion
    '1f984',   # 🦄 unicorn
    '1f409',   # 🐉 dragon
    '1f432',   # 🐲 dragon face
    '1f98a',   # 🦊 fox
    '1f985',   # 🦅 eagle
    '1f989',   # 🦉 owl
    '1f99c',   # 🦜 parrot
    '1f99a',   # 🦚 peacock
    '1f9a9',   # 🦩 flamingo
    '1f9a2',   # 🦢 swan
    '1f42c',   # 🐬 dolphin
    '1f988',   # 🦈 shark
    '1f995',   # 🦕 sauropod
    '1f996',   # 🦖 t-rex

    # ── Fantasy ───────────────────────────────────────────────────────────────
    '1f9d9',   # 🧙 mage
    '1f9da',   # 🧚 fairy
    '1f9dc',   # 🧜 merperson
    '1f9de',   # 🧞 genie

    # ── Places & transport ────────────────────────────────────────────────────
    '1f3f0',   # 🏰 castle
    '1f5fd',   # 🗽 statue of liberty
    '1f30d',   # 🌍 globe europe-africa
    '1f30e',   # 🌎 globe americas
    '1f30f',   # 🌏 globe asia-australia
    '1f681',   # 🚁 helicopter
    '1f6f0',   # 🛰️ satellite

    # ── Fun objects ───────────────────────────────────────────────────────────
    '1f52e',   # 🔮 crystal ball
    '1f5ff',   # 🗿 moai
    '1f3a0',   # 🎠 carousel horse
    '1f3a1',   # 🎡 ferris wheel
    '1f3a2',   # 🎢 roller coaster
    '1f4f8',   # 📸 camera with flash
    '1f3a5',   # 🎥 movie camera
]

# Deduplicate while preserving order
EMOJIS = list(dict.fromkeys(EMOJIS))


def main():
    os.makedirs(EMOJI_DIR, exist_ok=True)
    print(f'Saving to: {EMOJI_DIR}')
    print(f'Total to download: {len(EMOJIS)}\n')

    ok = skipped = failed = 0
    for code in EMOJIS:
        url      = BASE_URL.format(code)
        out_path = os.path.join(EMOJI_DIR, f'emoji_u{code}.png')
        if os.path.exists(out_path):
            skipped += 1
            continue
        try:
            urllib.request.urlretrieve(url, out_path)
            print(f'  downloaded: emoji_u{code}.png')
            ok += 1
        except Exception as e:
            print(f'  FAILED    : emoji_u{code}.png — {e}')
            failed += 1

    total = ok + skipped
    print(f'\nDone: {total}/{len(EMOJIS)} ready  '
          f'({ok} new, {skipped} already existed, {failed} failed)')


if __name__ == '__main__':
    main()
