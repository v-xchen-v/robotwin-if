#!/usr/bin/env bash
# Extract N evenly-spaced key frames from a video for visual inspection.
#
# Usage: tools/extract_frames.sh <video_path> [num_frames] [out_dir]
#   num_frames : how many frames to sample (default 8, minimum 2)
#   out_dir    : where to write them (default: <video_dir>/frames_<video_stem>/)
#
# Frames are named frame_<order>_n<srcindex>.png so their order and their
# position in the source video are both obvious to a human or a model reading
# them back. Prints the output dir and the frame list on stdout.
set -euo pipefail

VIDEO="${1:?usage: extract_frames.sh <video_path> [num_frames] [out_dir]}"
N="${2:-8}"
OUT="${3:-$(dirname "$VIDEO")/frames_$(basename "${VIDEO%.*}")}"

[ -f "$VIDEO" ] || { echo "error: no such video: $VIDEO" >&2; exit 1; }
command -v ffmpeg  >/dev/null || { echo "error: ffmpeg not found"  >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "error: ffprobe not found" >&2; exit 1; }
[ "$N" -ge 2 ] 2>/dev/null || N=2

mkdir -p "$OUT"
rm -f "$OUT"/frame_*.png

# Decode-accurate frame count (robust even when the container omits nb_frames).
total=$(ffprobe -v error -select_streams v:0 -count_frames \
        -show_entries stream=nb_read_frames -of csv=p=0 "$VIDEO" 2>/dev/null || true)

if [ -n "$total" ] && [ "$total" -gt 1 ] 2>/dev/null; then
  # Evenly spaced source indices across [0, total-1], inclusive of both ends.
  for i in $(seq 0 $((N - 1))); do
    idx=$(( i * (total - 1) / (N - 1) ))
    printf -v out "%s/frame_%02d_n%04d.png" "$OUT" "$i" "$idx"
    ffmpeg -loglevel error -y -i "$VIDEO" -vf "select=eq(n\,$idx)" -vframes 1 "$out"
  done
else
  # Fallback: sample by time when the frame count is unavailable.
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO" 2>/dev/null || echo 0)
  ffmpeg -loglevel error -y -i "$VIDEO" \
    -vf "fps=${N}/${dur:-8}" "$OUT/frame_%02d.png"
fi

echo "extracted $N frames from: $VIDEO"
echo "output dir: $OUT"
ls -1 "$OUT"/frame_*.png
