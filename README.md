# orbwave

A fullscreen audio visualizer for Linux built with pygame. It listens to whatever your system is playing and draws a ring of spectrum bars around a spinning album cover.


## Features

- Captures system audio (no microphone needed), via the monitor of your default speaker
- Circular spectrum computed with an FFT; the ring pulses with the bass
- Rotating circular album cover, taken from the currently playing track
- Bar colors and background are generated from the cover's palette
- Bass-reactive screen shake and floating particles

## Requirements

- Linux with PulseAudio or PipeWire (with `pipewire-pulse`)
- Python 3.12+
- A media player that exposes MPRIS (Spotify, Firefox, Chromium, VLC, mpv with an MPRIS plugin, etc.) for album covers. Without it, orbwave still works, just without a cover.

## Install

```bash
pip install orbwave
```

or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install orbwave
```

## Usage

```bash
orbwave
```

Start any music, and the visualizer reacts to it.

| Key | Action |
| --- | --- |
| `Up` | More bars (up to 512) |
| `Down` | Fewer bars (down to 32) |
| `Esc` | Quit |

## How it works

1. A background thread records audio in chunks of 1024 samples.
2. Each chunk gets a Hann window and goes through `numpy.fft.rfft` to get a spectrum.
3. The spectrum is log-scaled and smoothed, then drawn as bars around a circle.
4. The lowest bins are averaged into a "bass" value that drives the pulse, shake and particle speed.
5. Cover art is read from the player over D-Bus (MPRIS), cropped to a circle, and used to pick the color palette.

## Troubleshooting

- **No sound reaction:** check that `pactl list sources short` shows a `.monitor` source and that your default output is the one actually playing.
- **No album cover:** make sure your player shows up in `playerctl -l` and provides cover art in its metadata.

## Platform support

Linux only for now. Windows and macOS are not supported yet.

## License

[MIT](LICENSE)
