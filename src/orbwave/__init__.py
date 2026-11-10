import sys

if len(sys.argv) < 2:
    sys.argv.append("audio-visualizer")

import numpy as np
import soundcard as sc
import pygame
import colorsys
import math
import random
import threading
import queue
import os
import sys
import asyncio
from orbwave.utils.album_cover import media_art_loop

WIDTH, HEIGHT = 1920, 1200
FPS = 144
CHUNK = 1024
initial_BARS = 128
RADIUS = 200
SHAKE_INTENSITY = 5
BASS_BINS = 6
PARTICLE_COUNT = 150
ART_FILE = "current_media_art.png"


def _get_loopback_mic():

    all_mics = sc.all_microphones(include_loopback=True)

    try:
        speaker = sc.default_speaker()
        speaker_name = speaker.name
        print(f"[audio] Default speaker: {speaker_name}")
        for m in all_mics:
            if "monitor" in m.name.lower() and speaker_name.lower() in m.name.lower():
                print(f"[audio] ✓ Using monitor of default speaker: {m.name}")
                return m
    except Exception as e:
        print(f"[audio] Could not get default speaker: {e}")

    for m in all_mics:
        if "monitor" in m.name.lower() or "loopback" in m.name.lower():
            print(f"[audio] Using monitor source: {m.name}")
            return m

    mic = sc.default_microphone()
    print(f"[audio] Falling back to default microphone: {mic.name}")
    return mic


mic = _get_loopback_mic()

audio_queue: queue.Queue = queue.Queue(maxsize=4)


def audio_thread_function():
    """Record audio in a background thread, pushing frames into audio_queue."""
    try:
        with mic.recorder(samplerate=44100, blocksize=CHUNK) as rec:
            while True:
                data = rec.record(numframes=CHUNK)
                if audio_queue.full():
                    try:
                        audio_queue.get_nowait()
                    except queue.Empty:
                        pass
                audio_queue.put_nowait(data)
    except Exception as e:
        print(f"[audio] Recording thread crashed: {e}")


def brighten_color(color, min_brightness=100):
    r, g, b = color
    brightness = (r + g + b) / 3
    if brightness < min_brightness:
        factor = min_brightness / max(1, brightness)
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
    return (r, g, b)


def start_asyncio_thread():
    asyncio.run(media_art_loop())


def _init_pygame_wayland():
    if "WAYLAND_DISPLAY" in os.environ:
        os.environ.setdefault("SDL_VIDEODRIVER", "wayland")

    pygame.init()

    try:
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
    except pygame.error:
        print("[display] Fullscreen failed, trying borderless window")
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)

    pygame.display.set_caption("Audio Visualizer")
    return screen


def run_visualizer():

    media_art_thread = threading.Thread(target=start_asyncio_thread, daemon=True)
    media_art_thread.start()
    print("[visual] Media art loop started in a separate thread.")

    screen = _init_pygame_wayland()
    clock = pygame.time.Clock()
    pygame.mouse.set_visible(False)

    BARS = initial_BARS
    hue = 0
    spectrum_smooth = np.zeros(BARS)
    center_x, center_y = WIDTH // 2, HEIGHT // 2
    rotation_angle = 0
    particles = []
    current_art = None
    last_file_mod_time = 0
    dynamic_radius = 0
    current_bg_brightness = 10
    avg_color = (10, 10, 20)
    palette = [avg_color]
    loaded_image = None

    for _ in range(PARTICLE_COUNT):
        particles.append(
            {
                "x": random.uniform(0, WIDTH),
                "y": random.uniform(0, HEIGHT),
                "size": random.uniform(1, 4),
                "speed": random.uniform(0.2, 1),
            }
        )

    def get_spectrum(audio_data):
        nonlocal spectrum_smooth
        mono = audio_data[:, 0] * np.hanning(len(audio_data))
        fft = np.abs(np.fft.rfft(mono))[:BARS]
        fft = np.log1p(fft)
        spectrum_smooth = 0.7 * spectrum_smooth + 0.3 * fft
        return spectrum_smooth

    audio_thread = threading.Thread(target=audio_thread_function, daemon=True)
    audio_thread.start()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    new_bars = min(BARS * 2, 512)
                    if new_bars != BARS:
                        BARS = new_bars
                        spectrum_smooth = np.zeros(BARS)
                        print(f"BARS increased to: {BARS}")
                elif event.key == pygame.K_DOWN:
                    new_bars = max(BARS // 2, 32)
                    if new_bars != BARS:
                        BARS = new_bars
                        spectrum_smooth = np.zeros(BARS)
                        print(f"BARS decreased to: {BARS}")

        if os.path.exists(ART_FILE):
            mod_time = os.path.getmtime(ART_FILE)
            if mod_time > last_file_mod_time:
                try:
                    loaded_image = pygame.image.load(ART_FILE).convert_alpha()
                    size = int(RADIUS * 1.8)
                    current_art = pygame.transform.scale(loaded_image, (size, size))
                    last_file_mod_time = mod_time

                    arr = pygame.surfarray.array3d(loaded_image)  # (w, h, 3)
                    avg = arr.mean(axis=(0, 1))
                    avg_color = tuple(int(c) for c in avg)

                    pixels = arr.reshape(-1, 3)
                    max_samples = 8000
                    if pixels.shape[0] > max_samples:
                        step = pixels.shape[0] // max_samples
                        pixels = pixels[::step]

                    q = (pixels >> 4).astype(np.int32)
                    keys = (q[:, 0] << 8) + (q[:, 1] << 4) + q[:, 2]
                    unique, counts = np.unique(keys, return_counts=True)

                    k = 6
                    palette = []
                    if unique.size:
                        top_idx = np.argsort(counts)[-k:]
                        top_keys = unique[top_idx][::-1]
                        for key in top_keys:
                            r = (((key >> 8) & 0xF) << 4) + 8
                            g = (((key >> 4) & 0xF) << 4) + 8
                            b = ((key & 0xF) << 4) + 8
                            if (r + g + b) < 40:
                                continue
                            if (r + g + b) > 740:
                                continue
                            palette.append((int(r), int(g), int(b)))

                    if not palette:
                        palette = [avg_color]

                except Exception as e:
                    print(f"[visual] Error loading image / palette extraction: {e}")
                    current_art = None
                    avg_color = (10, 10, 20)
                    palette = [avg_color]
        else:
            current_art = None
            loaded_image = None

        audio_data = None
        while not audio_queue.empty():
            try:
                audio_data = audio_queue.get_nowait()
            except queue.Empty:
                break

        if audio_data is not None:
            spectrum = get_spectrum(audio_data)
        else:
            spectrum = spectrum_smooth

        volume = np.mean(spectrum[:BASS_BINS]) * 0.5
        dynamic_radius = RADIUS + volume * 25
        shake_x = shake_y = 0

        target_bg_brightness = 1.0
        if volume > 1.1:
            shake_x = random.randint(-SHAKE_INTENSITY, SHAKE_INTENSITY)
            shake_y = random.randint(-SHAKE_INTENSITY, SHAKE_INTENSITY)
            target_bg_brightness = 1.0 + volume * 0.5

        current_bg_brightness = current_bg_brightness * 0.9 + target_bg_brightness * 0.1

        darken_factor = 0.35
        base_r = int(avg_color[0] * darken_factor)
        base_g = int(avg_color[1] * darken_factor)
        base_b = int(avg_color[2] * darken_factor)
        # base_r = int(50 * darken_factor)
        # base_g = int(50 * darken_factor)
        # base_b = int(50 * darken_factor)

        r = min(255, int(base_r * current_bg_brightness))
        g = min(255, int(base_g * current_bg_brightness))
        b = min(255, int(base_b * current_bg_brightness))
        screen.fill((r, g, b))

        hue = (hue + 0.002) % 1.0
        color = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1, 1))

        # === Particles ===
        for p in particles:
            p["y"] += p["speed"] * (1 + volume * 2)
            if p["y"] > HEIGHT:
                p["y"] = 0
                p["x"] = random.uniform(0, WIDTH)
            pygame.draw.circle(
                screen,
                (255, 255, 255),
                (int(p["x"] + shake_x * 0.5), int(p["y"] + shake_y * 0.5)),
                int(p["size"]),
            )

        half_bars = BARS // 2
        for i, value in enumerate(spectrum[:half_bars]):
            if len(palette) == 1:
                line_color = palette[0]
            else:
                t = i / max(1, half_bars - 1)
                scaled = t * (len(palette) - 1)
                idx = int(math.floor(scaled))
                frac = scaled - idx
                c1 = palette[idx]
                c2 = palette[min(idx + 1, len(palette) - 1)]
                line_color = (
                    int(c1[0] * (1 - frac) + c2[0] * frac),
                    int(c1[1] * (1 - frac) + c2[1] * frac),
                    int(c1[2] * (1 - frac) + c2[2] * frac),
                )
            line_color = brighten_color(line_color, min_brightness=100)

            angle1 = (2 * math.pi / BARS) * i - math.pi / 2
            bar_start = dynamic_radius
            bar_len = dynamic_radius + value * 75

            x1_1 = center_x + math.cos(angle1) * bar_start + shake_x
            y1_1 = center_y + math.sin(angle1) * bar_start + shake_y
            x2_1 = center_x + math.cos(angle1) * bar_len + shake_x
            y2_1 = center_y + math.sin(angle1) * bar_len + shake_y
            pygame.draw.line(screen, line_color, (x1_1, y1_1), (x2_1, y2_1), 3)

            angle2 = angle1 + math.pi
            x1_2 = center_x + math.cos(angle2) * bar_start + shake_x
            y1_2 = center_y + math.sin(angle2) * bar_start + shake_y
            x2_2 = center_x + math.cos(angle2) * bar_len + shake_x
            y2_2 = center_y + math.sin(angle2) * bar_len + shake_y
            pygame.draw.line(screen, line_color, (x1_2, y1_2), (x2_2, y2_2), 3)

        rotation_angle += 0.005
        if current_art:
            size = int(dynamic_radius * 1.8)
            scaled_art = pygame.transform.scale(current_art, (size, size))
            rotated_art = pygame.transform.rotate(
                scaled_art, -math.degrees(rotation_angle)
            )
            art_rect = rotated_art.get_rect(
                center=(center_x + shake_x, center_y + shake_y)
            )
            screen.blit(rotated_art, art_rect)

        pygame.draw.circle(
            screen,
            color,
            (center_x + shake_x, center_y + shake_y),
            int(dynamic_radius - 10),
            2,
        )

        # === HUD ===
        font = pygame.font.SysFont(None, 36)
        text = font.render(f"BARS: {BARS} (UP/DOWN to change)", True, (255, 255, 255))
        screen.blit(text, (20, 20))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


def main():
    run_visualizer()


if __name__ == "__main__":
    run_visualizer()
