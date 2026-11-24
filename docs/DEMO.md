# Demonstration asset

`media/retrocast_demo.mp4` is a seven-second test card generated for RetroCast from FFmpeg's built-in SMPTE color bars and sine-wave sources. It uses no external footage, artwork, fonts, or recorded sound.

Regenerate it from the repository root with an FFmpeg build that includes libx264:

```sh
ffmpeg -f lavfi -i "smptebars=size=640x480:rate=30000/1001" -f lavfi -i "sine=frequency=440:sample_rate=48000" -t 7 -c:v libx264 -pix_fmt yuv420p -crf 20 -preset medium -c:a aac -b:a 64k -map_metadata -1 -movflags +faststart media/retrocast_demo.mp4
```

The output contains H.264 video and AAC audio in an MP4 container. FFmpeg is needed to regenerate the asset, not to serve it in the browser.
