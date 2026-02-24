# FFmpeg Video Transcode

**ID:** `video_transcode`

**Category:** media_processing

**Description:** Video transcoding with one large file dominating processing time

## Workload Purpose & Characteristics

This workload simulates video transcoding operations common in media processing pipelines, content delivery networks, and video streaming platforms. The scenario includes 39 processes transcoding 30-second clips (320x240) and 1 process handling a 70-second HD video (1920x1080), creating both duration and resolution imbalances that significantly impact processing time.

## Key Performance Characteristics

- **CPU-intensive encoding**: Video codec operations dominate CPU usage
- **Memory bandwidth sensitive**: Frame buffer manipulation requires high memory throughput
- **Multi-threaded processing**: FFmpeg utilizes multiple threads for encoding
- **Resolution-dependent load**: HD video requires significantly more processing per frame
- **Sustained CPU usage**: Long-running tasks with consistent resource demands

## Optimization Goals

1. **Minimize total transcoding time**: Reduce completion time for all video processing
2. **Prioritize HD video processing**: Ensure the large video gets continuous CPU access
3. **Optimize multi-threaded performance**: Efficient thread scheduling for encoder threads
4. **Maintain encoding quality**: Consistent CPU allocation to prevent quality degradation
5. **Balance system load**: Prevent system overload while maximizing throughput

## Scheduling Algorithm

The optimal scheduler for video transcoding should implement:

1. **Process identification**: Detect "small_video_transcode" and "large_video_transcode" processes
2. **HD video prioritization**: Assign highest priority to large_video_transcode
3. **Time slice configuration**:
   - Large video: 30ms slices for sustained encoding operations
   - Small videos: 10ms slices for responsive completion
4. **Thread-aware scheduling**: Consider FFmpeg's multi-threaded nature in CPU allocation
5. **NUMA optimization**: Keep video processing threads and memory buffers co-located

## Dependencies

- ffmpeg
- g++

## Small Setup Commands

```bash
mkdir -p clips out
ffmpeg -f lavfi -i testsrc=duration=30:size=320x240:rate=30 -loglevel quiet clips/short.mp4
cp $ORIGINAL_CWD/assets/video_transcode.cpp .
g++ -o small_video_transcode video_transcode.cpp -lavformat -lavcodec -lavutil -lswscale -lpthread -lm -lz
```

## Large Setup Commands

```bash
mkdir -p clips out
ffmpeg -f lavfi -i testsrc=duration=70:size=1920x1080:rate=30 -loglevel quiet clips/long.mp4
cp $ORIGINAL_CWD/assets/video_transcode.cpp .
g++ -o large_video_transcode video_transcode.cpp -lavformat -lavcodec -lavutil -lswscale -lpthread -lm -lz
```

## Small Execution Commands

```bash
./small_video_transcode clips/short.mp4 out/short_out.mp4 640
```

## Large Execution Commands

```bash
./large_video_transcode clips/long.mp4 out/long_out.mp4 640
```

## Cleanup Commands

```bash
rm -rf clips/ out/
rm -f small_video_transcode large_video_transcode video_transcode.cpp
```
